"""Package Manager - Mengelola instalasi paket (pip, npm)."""

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class InstalledPackage:
    def __init__(self, name: str, version: str, manager: str):
        self.name = name
        self.version = version
        self.manager = manager

    def to_dict(self) -> dict:
        return {"name": self.name, "version": self.version, "manager": self.manager}


class PackageManager:
    SUPPORTED_MANAGERS = {"pip", "npm", "yarn"}

    def __init__(self, working_dir: str = "."):
        self.working_dir = working_dir
        self.installed_packages: dict[str, InstalledPackage] = {}
        self.install_history: list[dict] = []

    async def install(self, packages: list[str], manager: str = "pip", global_install: bool = False) -> dict:
        if manager not in self.SUPPORTED_MANAGERS:
            return {"success": False, "error": f"Manager tidak didukung: {manager}. Gunakan: {self.SUPPORTED_MANAGERS}"}

        if not packages:
            return {"success": False, "error": "Tidak ada paket untuk diinstal"}

        cmd = self._build_install_command(packages, manager, global_install)
        logger.info(f"Menginstal paket [{manager}]: {', '.join(packages)}")

        try:
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_dir,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")

            success = process.returncode == 0

            if success:
                for pkg in packages:
                    pkg_name = pkg.split("==")[0].split(">=")[0].split("<=")[0]
                    version = pkg.split("==")[1] if "==" in pkg else "latest"
                    self.installed_packages[pkg_name] = InstalledPackage(pkg_name, version, manager)

            result = {
                "success": success,
                "packages": packages,
                "manager": manager,
                "output": stdout_text[:3000],
                "errors": stderr_text[:1000] if stderr_text else None,
            }
            self.install_history.append(result)
            return result

        except asyncio.TimeoutError:
            return {"success": False, "error": "Instalasi timeout (300s)"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def uninstall(self, packages: list[str], manager: str = "pip") -> dict:
        if manager not in self.SUPPORTED_MANAGERS:
            return {"success": False, "error": f"Manager tidak didukung: {manager}"}

        cmd = self._build_uninstall_command(packages, manager)
        logger.info(f"Menghapus paket [{manager}]: {', '.join(packages)}")

        try:
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_dir,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)

            success = process.returncode == 0
            if success:
                for pkg in packages:
                    pkg_name = pkg.split("==")[0]
                    self.installed_packages.pop(pkg_name, None)

            return {
                "success": success,
                "packages": packages,
                "output": stdout.decode("utf-8", errors="replace")[:2000],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def list_installed(self, manager: str = "pip") -> dict:
        commands = {
            "pip": "pip list --format=json",
            "npm": "npm list --json --depth=0",
            "yarn": "yarn list --json --depth=0",
        }
        cmd = commands.get(manager)
        if not cmd:
            return {"success": False, "error": f"Manager tidak didukung: {manager}"}

        try:
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_dir,
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=30)
            return {
                "success": True,
                "manager": manager,
                "output": stdout.decode("utf-8", errors="replace")[:5000],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _build_install_command(self, packages: list[str], manager: str, global_install: bool) -> str:
        pkg_str = " ".join(packages)
        if manager == "pip":
            return f"pip install {pkg_str}"
        elif manager == "npm":
            flag = "-g" if global_install else ""
            return f"npm install {flag} {pkg_str}".strip()
        elif manager == "yarn":
            flag = "global" if global_install else ""
            return f"yarn {flag} add {pkg_str}".strip()
        return ""

    def _build_uninstall_command(self, packages: list[str], manager: str) -> str:
        pkg_str = " ".join(packages)
        if manager == "pip":
            return f"pip uninstall -y {pkg_str}"
        elif manager == "npm":
            return f"npm uninstall {pkg_str}"
        elif manager == "yarn":
            return f"yarn remove {pkg_str}"
        return ""

    def get_install_history(self) -> list[dict]:
        return self.install_history
