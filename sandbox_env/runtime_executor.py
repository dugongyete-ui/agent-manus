"""Runtime Executor - Menjalankan kode di berbagai runtime."""

import asyncio
import logging
import os
import tempfile
import time
from typing import Optional

logger = logging.getLogger(__name__)


class ExecutionResult:
    def __init__(self, runtime: str, code: str, stdout: str, stderr: str, return_code: int, duration: float):
        self.runtime = runtime
        self.code = code
        self.stdout = stdout
        self.stderr = stderr
        self.return_code = return_code
        self.duration = duration
        self.success = return_code == 0
        self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            "runtime": self.runtime,
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "return_code": self.return_code,
            "duration": self.duration,
        }


class RuntimeExecutor:
    RUNTIME_COMMANDS = {
        "python3": {"command": "python3", "extension": ".py"},
        "nodejs": {"command": "node", "extension": ".js"},
        "bash": {"command": "bash", "extension": ".sh"},
        "ruby": {"command": "ruby", "extension": ".rb"},
        "php": {"command": "php", "extension": ".php"},
    }

    def __init__(self, working_dir: str = ".", max_execution_time: int = 120, allowed_runtimes: Optional[list] = None):
        self.working_dir = working_dir
        self.max_execution_time = max_execution_time
        self.allowed_runtimes = allowed_runtimes or list(self.RUNTIME_COMMANDS.keys())
        self.execution_history: list[ExecutionResult] = []

    async def execute_code(self, code: str, runtime: str = "python3", timeout: Optional[int] = None) -> ExecutionResult:
        if runtime not in self.allowed_runtimes:
            return ExecutionResult(
                runtime=runtime, code=code,
                stdout="", stderr=f"Runtime tidak diizinkan: {runtime}. Gunakan: {self.allowed_runtimes}",
                return_code=-1, duration=0,
            )

        if runtime not in self.RUNTIME_COMMANDS:
            return ExecutionResult(
                runtime=runtime, code=code,
                stdout="", stderr=f"Runtime tidak dikenal: {runtime}",
                return_code=-1, duration=0,
            )

        timeout = timeout or self.max_execution_time
        rt_config = self.RUNTIME_COMMANDS[runtime]

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=rt_config["extension"],
            dir=self.working_dir, delete=False
        ) as tmp_file:
            tmp_file.write(code)
            tmp_path = tmp_file.name

        try:
            start_time = time.time()
            cmd = f"{rt_config['command']} {tmp_path}"

            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_dir,
            )

            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            duration = time.time() - start_time

            result = ExecutionResult(
                runtime=runtime,
                code=code,
                stdout=stdout.decode("utf-8", errors="replace").strip(),
                stderr=stderr.decode("utf-8", errors="replace").strip(),
                return_code=process.returncode,
                duration=duration,
            )

            self.execution_history.append(result)
            logger.info(f"Kode {runtime} dieksekusi ({duration:.2f}s), return code: {process.returncode}")
            return result

        except asyncio.TimeoutError:
            duration = time.time() - start_time
            result = ExecutionResult(
                runtime=runtime, code=code,
                stdout="", stderr=f"Eksekusi timeout setelah {timeout}s",
                return_code=-1, duration=duration,
            )
            self.execution_history.append(result)
            return result

        except Exception as e:
            result = ExecutionResult(
                runtime=runtime, code=code,
                stdout="", stderr=str(e),
                return_code=-1, duration=0,
            )
            self.execution_history.append(result)
            return result

        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    async def execute_file(self, file_path: str, runtime: Optional[str] = None, timeout: Optional[int] = None) -> ExecutionResult:
        if not os.path.exists(file_path):
            return ExecutionResult(
                runtime=runtime or "unknown", code="",
                stdout="", stderr=f"File tidak ditemukan: {file_path}",
                return_code=-1, duration=0,
            )

        if not runtime:
            ext = os.path.splitext(file_path)[1]
            ext_to_runtime = {v["extension"]: k for k, v in self.RUNTIME_COMMANDS.items()}
            runtime = ext_to_runtime.get(ext)
            if not runtime:
                return ExecutionResult(
                    runtime="unknown", code="",
                    stdout="", stderr=f"Tidak dapat mendeteksi runtime untuk ekstensi: {ext}",
                    return_code=-1, duration=0,
                )

        with open(file_path, "r") as f:
            code = f.read()

        return await self.execute_code(code, runtime, timeout)

    def get_supported_runtimes(self) -> list[str]:
        return self.allowed_runtimes

    def get_execution_history(self, limit: int = 20) -> list[dict]:
        return [r.to_dict() for r in self.execution_history[-limit:]]

    def clear_history(self):
        self.execution_history.clear()
        logger.info("Riwayat eksekusi dibersihkan")
