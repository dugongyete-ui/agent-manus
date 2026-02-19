"""Shell Tool - Eksekusi perintah shell dengan keamanan dan isolasi."""

import asyncio
import logging
import os
import re
import shlex
from typing import Optional

logger = logging.getLogger(__name__)

BLOCKED_COMMANDS = {
    "rm -rf /", "rm -rf /*", "shutdown", "reboot", "halt", "poweroff",
    "mkfs", "dd if=/dev/zero", "dd if=/dev/random",
    ":(){:|:&};:", "fork bomb",
}

BLOCKED_PATTERNS = [
    r"rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?/\s*$",
    r"rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?/\*",
    r">\s*/dev/sd[a-z]",
    r"mkfs\.",
    r"dd\s+if=/dev/(zero|random|urandom)\s+of=/dev/sd",
    r"chmod\s+(-[a-zA-Z]+\s+)?777\s+/",
    r"chown\s+.*\s+/",
    r"wget.*\|\s*(ba)?sh",
    r"curl.*\|\s*(ba)?sh",
]

DANGEROUS_ENV_PATTERNS = [
    r"export\s+PATH\s*=\s*$",
    r"unset\s+PATH",
    r"export\s+LD_PRELOAD",
]

MAX_OUTPUT_SIZE = 100000


class ShellTool:
    def __init__(self, working_dir: str = "/home/runner/workspace/user_workspace", timeout: int = 120, max_concurrent: int = 5):
        self.working_dir = os.path.abspath(working_dir)
        os.makedirs(self.working_dir, exist_ok=True)
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self.command_history: list[dict] = []
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._running_processes: list[asyncio.subprocess.Process] = []

    async def execute(self, plan: dict) -> str:
        command = plan.get("command", "")
        if not command:
            intent = plan.get("intent", "")
            input_text = plan.get("analysis", {}).get("input", "")
            return f"Shell siap. Intent: {intent}. Menunggu perintah spesifik."
        return await self.run_command(command)

    def _check_safety(self, command: str) -> Optional[str]:
        cmd_lower = command.lower().strip()

        for blocked in BLOCKED_COMMANDS:
            if blocked in cmd_lower:
                return f"Perintah diblokir untuk keamanan: mengandung '{blocked}'"

        for pattern in BLOCKED_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return f"Perintah diblokir: cocok dengan pola berbahaya"

        for pattern in DANGEROUS_ENV_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return f"Perintah diblokir: manipulasi environment berbahaya"

        return None

    async def run_command(self, command: str, timeout: Optional[int] = None, working_dir: Optional[str] = None) -> str:
        timeout = timeout or self.timeout
        cwd = working_dir or self.working_dir

        safety_msg = self._check_safety(command)
        if safety_msg:
            logger.warning(f"{safety_msg}: {command}")
            self.command_history.append({
                "command": command, "return_code": -1,
                "stdout": "", "stderr": safety_msg, "blocked": True,
            })
            return safety_msg

        logger.info(f"Menjalankan perintah: {command}")

        async with self._semaphore:
            process = None
            try:
                env = os.environ.copy()
                env["LC_ALL"] = "C.UTF-8"

                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    env=env,
                )
                self._running_processes.append(process)

                try:
                    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
                finally:
                    if process in self._running_processes:
                        self._running_processes.remove(process)

                stdout_text = stdout.decode("utf-8", errors="replace").strip()
                stderr_text = stderr.decode("utf-8", errors="replace").strip()

                if len(stdout_text) > MAX_OUTPUT_SIZE:
                    stdout_text = stdout_text[:MAX_OUTPUT_SIZE] + f"\n... (output terpotong, total {len(stdout.decode('utf-8', errors='replace'))} karakter)"
                if len(stderr_text) > MAX_OUTPUT_SIZE:
                    stderr_text = stderr_text[:MAX_OUTPUT_SIZE] + "\n... (error output terpotong)"

                result = {
                    "command": command,
                    "return_code": process.returncode or 0,
                    "stdout": stdout_text,
                    "stderr": stderr_text,
                    "blocked": False,
                }
                self.command_history.append(result)

                output_parts = []
                if stdout_text:
                    output_parts.append(f"Output:\n{stdout_text}")
                if stderr_text:
                    output_parts.append(f"Stderr:\n{stderr_text}")
                output_parts.append(f"Return code: {process.returncode}")

                return "\n".join(output_parts)

            except asyncio.TimeoutError:
                try:
                    if process:
                        process.kill()
                        await process.wait()
                except Exception:
                    pass
                msg = f"Perintah timeout setelah {timeout} detik: {command}"
                logger.error(msg)
                self.command_history.append({
                    "command": command, "return_code": -1,
                    "stdout": "", "stderr": msg, "blocked": False, "timeout": True,
                })
                return msg
            except Exception as e:
                msg = f"Error menjalankan perintah: {e}"
                logger.error(msg)
                self.command_history.append({
                    "command": command, "return_code": -1,
                    "stdout": "", "stderr": msg, "blocked": False,
                })
                return msg

    async def run_code(self, code: str, runtime: str = "python3", timeout: Optional[int] = None) -> str:
        import tempfile
        ext_map = {
            "python3": ".py", "python": ".py",
            "node": ".js", "nodejs": ".js",
            "bash": ".sh", "sh": ".sh",
            "ruby": ".rb",
            "php": ".php",
        }
        cmd_map = {
            "python3": "python3", "python": "python3",
            "node": "node", "nodejs": "node",
            "bash": "bash", "sh": "sh",
            "ruby": "ruby",
            "php": "php",
        }

        ext = ext_map.get(runtime, ".txt")
        cmd = cmd_map.get(runtime)
        if not cmd:
            return f"Runtime tidak didukung: {runtime}. Gunakan: {list(cmd_map.keys())}"

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=ext, dir=self.working_dir, delete=False
        ) as f:
            f.write(code)
            tmp_path = f.name

        try:
            result = await self.run_command(f"{cmd} {tmp_path}", timeout=timeout)
            return result
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    async def run_background(self, command: str) -> dict:
        safety_msg = self._check_safety(command)
        if safety_msg:
            return {"success": False, "error": safety_msg}

        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.working_dir,
        )
        self._running_processes.append(process)
        return {"success": True, "pid": process.pid, "message": f"Proses dimulai di background (PID: {process.pid})"}

    async def kill_process(self, pid: int) -> dict:
        for proc in self._running_processes:
            if proc.pid == pid:
                try:
                    proc.kill()
                    await proc.wait()
                    self._running_processes.remove(proc)
                    return {"success": True, "message": f"Proses {pid} dihentikan"}
                except Exception as e:
                    return {"success": False, "error": str(e)}
        return {"success": False, "error": f"Proses {pid} tidak ditemukan"}

    def get_history(self, limit: int = 20) -> list[dict]:
        return self.command_history[-limit:]

    def clear_history(self):
        self.command_history.clear()

    async def cleanup(self):
        for proc in self._running_processes:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
        self._running_processes.clear()
