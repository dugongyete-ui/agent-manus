"""Shell Tool - Wrapper untuk interaksi shell."""

import asyncio
import logging
import shlex
from typing import Optional

logger = logging.getLogger(__name__)

BLOCKED_COMMANDS = {"rm -rf /", "shutdown", "reboot", "mkfs", "dd if=/dev/zero"}


class ShellTool:
    def __init__(self, working_dir: str = ".", timeout: int = 120):
        self.working_dir = working_dir
        self.timeout = timeout
        self.command_history: list[dict] = []

    async def execute(self, plan: dict) -> str:
        command = plan.get("command", "")
        if not command:
            intent = plan.get("intent", "")
            input_text = plan.get("analysis", {}).get("input", "")
            return f"Shell siap. Intent: {intent}. Menunggu perintah spesifik."

        return await self.run_command(command)

    async def run_command(self, command: str, timeout: Optional[int] = None) -> str:
        timeout = timeout or self.timeout

        for blocked in BLOCKED_COMMANDS:
            if blocked in command:
                msg = f"Perintah diblokir untuk keamanan: {command}"
                logger.warning(msg)
                return msg

        logger.info(f"Menjalankan perintah: {command}")

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_dir,
            )

            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            stdout_text = stdout.decode("utf-8", errors="replace").strip()
            stderr_text = stderr.decode("utf-8", errors="replace").strip()

            result = {
                "command": command,
                "return_code": process.returncode,
                "stdout": stdout_text,
                "stderr": stderr_text,
            }
            self.command_history.append(result)

            output_parts = []
            if stdout_text:
                output_parts.append(f"Output:\n{stdout_text[:5000]}")
            if stderr_text:
                output_parts.append(f"Error:\n{stderr_text[:2000]}")
            output_parts.append(f"Return code: {process.returncode}")

            return "\n".join(output_parts)

        except asyncio.TimeoutError:
            msg = f"Perintah timeout setelah {timeout} detik: {command}"
            logger.error(msg)
            return msg
        except Exception as e:
            msg = f"Error menjalankan perintah: {e}"
            logger.error(msg)
            return msg

    def get_history(self) -> list[dict]:
        return self.command_history
