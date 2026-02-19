"""Shell Session Manager - Sesi shell persisten dengan WebSocket support."""

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Optional, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class SessionState(Enum):
    ACTIVE = "active"
    IDLE = "idle"
    CLOSED = "closed"
    ERROR = "error"


class ShellSession:
    def __init__(self, session_id: str, working_dir: str = "/home/runner/workspace/user_workspace",
                 shell: str = "/bin/bash", env: Optional[dict] = None):
        self.session_id = session_id
        self.working_dir = working_dir
        self.shell = shell
        self.state = SessionState.IDLE
        self.created_at = time.time()
        self.last_activity = time.time()
        self.command_history: list[dict] = []
        self.current_directory = working_dir
        self.environment = env or {}
        self._process: Optional[asyncio.subprocess.Process] = None
        self._output_buffer: list[str] = []
        self._listeners: list[Callable] = []
        self._max_history = 500

    async def start(self):
        os.makedirs(self.working_dir, exist_ok=True)
        self.state = SessionState.ACTIVE
        logger.info(f"Shell session started: {self.session_id}")

    async def execute(self, command: str, timeout: int = 120) -> dict:
        if self.state == SessionState.CLOSED:
            return {"success": False, "error": "Sesi sudah ditutup"}

        self.state = SessionState.ACTIVE
        self.last_activity = time.time()
        start_time = time.time()

        try:
            env = os.environ.copy()
            env.update(self.environment)
            env["LC_ALL"] = "C.UTF-8"
            env["TERM"] = "xterm-256color"
            env["SESSION_ID"] = self.session_id

            full_command = f"cd {self.current_directory} 2>/dev/null; {command}; echo '::CWD::'; pwd"

            process = await asyncio.create_subprocess_shell(
                full_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_dir,
                env=env,
            )
            self._process = process

            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            duration = time.time() - start_time

            stdout_text = stdout.decode("utf-8", errors="replace").strip()
            stderr_text = stderr.decode("utf-8", errors="replace").strip()

            if "::CWD::" in stdout_text:
                parts = stdout_text.rsplit("::CWD::", 1)
                stdout_text = parts[0].strip()
                new_cwd = parts[1].strip()
                if new_cwd and os.path.isdir(new_cwd):
                    self.current_directory = new_cwd

            if len(stdout_text) > 100000:
                stdout_text = stdout_text[:100000] + "\n... (output terpotong)"

            result = {
                "success": process.returncode == 0,
                "command": command,
                "stdout": stdout_text,
                "stderr": stderr_text,
                "return_code": process.returncode or 0,
                "duration": round(duration, 3),
                "cwd": self.current_directory,
                "timestamp": time.time(),
            }

            self.command_history.append(result)
            if len(self.command_history) > self._max_history:
                self.command_history = self.command_history[-self._max_history:]

            for output_line in stdout_text.split("\n"):
                self._output_buffer.append(output_line)
            if len(self._output_buffer) > 2000:
                self._output_buffer = self._output_buffer[-1000:]

            for listener in self._listeners:
                try:
                    await listener({"type": "output", "data": result})
                except Exception:
                    pass

            self.state = SessionState.IDLE
            return result

        except asyncio.TimeoutError:
            duration = time.time() - start_time
            if self._process:
                try:
                    self._process.kill()
                except Exception:
                    pass
            result = {
                "success": False,
                "command": command,
                "stdout": "",
                "stderr": f"Timeout setelah {timeout}s",
                "return_code": -1,
                "duration": round(duration, 3),
                "cwd": self.current_directory,
                "timestamp": time.time(),
            }
            self.command_history.append(result)
            self.state = SessionState.IDLE
            return result

        except Exception as e:
            result = {
                "success": False,
                "command": command,
                "stdout": "",
                "stderr": str(e),
                "return_code": -1,
                "duration": 0,
                "cwd": self.current_directory,
                "timestamp": time.time(),
            }
            self.command_history.append(result)
            self.state = SessionState.ERROR
            return result
        finally:
            self._process = None

    async def execute_script(self, code: str, runtime: str = "bash", timeout: int = 120) -> dict:
        import tempfile
        ext_map = {"python3": ".py", "python": ".py", "nodejs": ".js", "bash": ".sh", "ruby": ".rb"}
        cmd_map = {"python3": "python3", "python": "python3", "nodejs": "node", "bash": "bash", "ruby": "ruby"}

        ext = ext_map.get(runtime, ".sh")
        cmd = cmd_map.get(runtime, "bash")

        with tempfile.NamedTemporaryFile(mode="w", suffix=ext, dir=self.current_directory, delete=False) as f:
            f.write(code)
            tmp_path = f.name

        try:
            return await self.execute(f"{cmd} {tmp_path}", timeout=timeout)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def add_listener(self, callback: Callable):
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable):
        if callback in self._listeners:
            self._listeners.remove(callback)

    async def close(self):
        self.state = SessionState.CLOSED
        if self._process:
            try:
                self._process.kill()
            except Exception:
                pass
        self._listeners.clear()
        logger.info(f"Shell session closed: {self.session_id}")

    def get_history(self, limit: int = 50) -> list[dict]:
        return self.command_history[-limit:]

    def get_output_buffer(self, limit: int = 200) -> list[str]:
        return self._output_buffer[-limit:]

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "state": self.state.value,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "current_directory": self.current_directory,
            "command_count": len(self.command_history),
            "shell": self.shell,
        }


class ShellSessionManager:
    def __init__(self, max_sessions: int = 20, session_timeout: int = 3600):
        self.max_sessions = max_sessions
        self.session_timeout = session_timeout
        self.sessions: dict[str, ShellSession] = {}
        self._default_working_dir = "/home/runner/workspace/user_workspace"

    async def create_session(self, working_dir: Optional[str] = None,
                             env: Optional[dict] = None,
                             session_id: Optional[str] = None) -> dict:
        if len(self.sessions) >= self.max_sessions:
            await self._cleanup_idle()
            if len(self.sessions) >= self.max_sessions:
                return {"success": False, "error": f"Batas sesi tercapai ({self.max_sessions})"}

        sid = session_id or f"shell_{uuid.uuid4().hex[:8]}"
        wd = working_dir or self._default_working_dir
        session = ShellSession(session_id=sid, working_dir=wd, env=env)
        await session.start()
        self.sessions[sid] = session
        logger.info(f"Shell session dibuat: {sid}")
        return {"success": True, "session_id": sid, "session": session.to_dict()}

    async def execute_in_session(self, session_id: str, command: str, timeout: int = 120) -> dict:
        session = self.sessions.get(session_id)
        if not session:
            return {"success": False, "error": f"Sesi tidak ditemukan: {session_id}"}
        if session.state == SessionState.CLOSED:
            return {"success": False, "error": "Sesi sudah ditutup"}
        return await session.execute(command, timeout=timeout)

    async def execute_script_in_session(self, session_id: str, code: str, runtime: str = "bash", timeout: int = 120) -> dict:
        session = self.sessions.get(session_id)
        if not session:
            return {"success": False, "error": f"Sesi tidak ditemukan: {session_id}"}
        return await session.execute_script(code, runtime=runtime, timeout=timeout)

    async def close_session(self, session_id: str) -> dict:
        session = self.sessions.get(session_id)
        if not session:
            return {"success": False, "error": f"Sesi tidak ditemukan: {session_id}"}
        await session.close()
        del self.sessions[session_id]
        return {"success": True, "message": f"Sesi {session_id} ditutup"}

    def get_session(self, session_id: str) -> Optional[dict]:
        session = self.sessions.get(session_id)
        return session.to_dict() if session else None

    def get_session_history(self, session_id: str, limit: int = 50) -> dict:
        session = self.sessions.get(session_id)
        if not session:
            return {"success": False, "error": f"Sesi tidak ditemukan: {session_id}"}
        return {"success": True, "history": session.get_history(limit)}

    def list_sessions(self) -> list[dict]:
        return [s.to_dict() for s in self.sessions.values()]

    async def _cleanup_idle(self):
        now = time.time()
        to_remove = []
        for sid, session in self.sessions.items():
            if (now - session.last_activity) > self.session_timeout:
                to_remove.append(sid)
        for sid in to_remove:
            await self.close_session(sid)

    async def cleanup_all(self):
        for sid in list(self.sessions.keys()):
            await self.close_session(sid)

    def get_stats(self) -> dict:
        states = {}
        for session in self.sessions.values():
            s = session.state.value
            states[s] = states.get(s, 0) + 1
        return {
            "total_sessions": len(self.sessions),
            "max_sessions": self.max_sessions,
            "states": states,
        }
