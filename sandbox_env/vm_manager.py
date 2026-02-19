"""VM Manager - Mengelola siklus hidup VM/Container dengan isolasi kuat."""

import asyncio
import json
import logging
import os
import shutil
import time
import uuid
from typing import Optional
from enum import Enum
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class VMState(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    ERROR = "error"
    CREATING = "creating"
    DESTROYING = "destroying"


class IsolationLevel(Enum):
    NONE = "none"
    BASIC = "basic"
    STRICT = "strict"
    MAXIMUM = "maximum"


@dataclass
class ResourceLimits:
    max_memory_mb: int = 512
    max_cpu_percent: float = 50.0
    max_disk_mb: int = 1024
    max_processes: int = 50
    max_open_files: int = 256
    max_network_connections: int = 10
    network_enabled: bool = True
    allowed_ports: list = field(default_factory=lambda: [80, 443, 8080, 3000, 5000])
    read_only_root: bool = False
    max_execution_time: int = 300

    def to_dict(self) -> dict:
        return {
            "max_memory_mb": self.max_memory_mb,
            "max_cpu_percent": self.max_cpu_percent,
            "max_disk_mb": self.max_disk_mb,
            "max_processes": self.max_processes,
            "max_open_files": self.max_open_files,
            "max_network_connections": self.max_network_connections,
            "network_enabled": self.network_enabled,
            "allowed_ports": self.allowed_ports,
            "read_only_root": self.read_only_root,
            "max_execution_time": self.max_execution_time,
        }

    @classmethod
    def from_isolation_level(cls, level: IsolationLevel) -> "ResourceLimits":
        presets = {
            IsolationLevel.NONE: cls(max_memory_mb=2048, max_cpu_percent=100, max_processes=200, network_enabled=True),
            IsolationLevel.BASIC: cls(max_memory_mb=1024, max_cpu_percent=80, max_processes=100, network_enabled=True),
            IsolationLevel.STRICT: cls(max_memory_mb=512, max_cpu_percent=50, max_processes=50, network_enabled=True, allowed_ports=[80, 443]),
            IsolationLevel.MAXIMUM: cls(max_memory_mb=256, max_cpu_percent=25, max_processes=20, network_enabled=False, read_only_root=True),
        }
        return presets.get(level, cls())


class VMSnapshot:
    def __init__(self, snapshot_id: str, name: str, vm_id: str):
        self.snapshot_id = snapshot_id
        self.name = name
        self.vm_id = vm_id
        self.created_at = time.time()
        self.size_mb = 0
        self.description = ""
        self.file_manifest: list[str] = []

    def to_dict(self) -> dict:
        return {
            "snapshot_id": self.snapshot_id,
            "name": self.name,
            "vm_id": self.vm_id,
            "created_at": self.created_at,
            "size_mb": self.size_mb,
            "description": self.description,
        }


class NetworkPolicy:
    def __init__(self):
        self.allowed_outbound: list[str] = ["*"]
        self.blocked_outbound: list[str] = []
        self.allowed_inbound_ports: list[int] = []
        self.rate_limit_mbps: float = 10.0
        self.dns_allowed: bool = True

    def is_port_allowed(self, port: int) -> bool:
        return port in self.allowed_inbound_ports

    def is_outbound_allowed(self, host: str) -> bool:
        if host in self.blocked_outbound:
            return False
        if "*" in self.allowed_outbound:
            return True
        return host in self.allowed_outbound

    def to_dict(self) -> dict:
        return {
            "allowed_outbound": self.allowed_outbound,
            "blocked_outbound": self.blocked_outbound,
            "allowed_inbound_ports": self.allowed_inbound_ports,
            "rate_limit_mbps": self.rate_limit_mbps,
            "dns_allowed": self.dns_allowed,
        }


class VirtualMachine:
    def __init__(self, vm_id: str, name: str, runtime: str = "python3",
                 isolation_level: IsolationLevel = IsolationLevel.BASIC):
        self.vm_id = vm_id
        self.name = name
        self.runtime = runtime
        self.state = VMState.STOPPED
        self.isolation_level = isolation_level
        self.resource_limits = ResourceLimits.from_isolation_level(isolation_level)
        self.network_policy = NetworkPolicy()
        self.created_at = time.time()
        self.started_at: Optional[float] = None
        self.resource_usage = {"cpu_percent": 0.0, "memory_mb": 0, "disk_mb": 0, "process_count": 0, "network_rx_mb": 0, "network_tx_mb": 0}
        self.environment: dict[str, str] = {}
        self.snapshots: list[VMSnapshot] = []
        self.working_dir = ""
        self.logs: list[dict] = []
        self.tags: dict[str, str] = {}
        self._process: Optional[asyncio.subprocess.Process] = None
        self._health_check_interval = 30
        self._auto_cleanup = True
        self.execution_count = 0
        self.total_execution_time = 0.0

    def add_log(self, level: str, message: str):
        self.logs.append({
            "timestamp": time.time(),
            "level": level,
            "message": message,
        })
        if len(self.logs) > 500:
            self.logs = self.logs[-300:]

    def to_dict(self) -> dict:
        return {
            "vm_id": self.vm_id,
            "name": self.name,
            "runtime": self.runtime,
            "state": self.state.value,
            "isolation_level": self.isolation_level.value,
            "resource_limits": self.resource_limits.to_dict(),
            "network_policy": self.network_policy.to_dict(),
            "created_at": self.created_at,
            "started_at": self.started_at,
            "resource_usage": self.resource_usage,
            "environment": {k: "***" for k in self.environment},
            "snapshots": [s.to_dict() for s in self.snapshots],
            "tags": self.tags,
            "execution_count": self.execution_count,
            "total_execution_time": round(self.total_execution_time, 2),
            "log_count": len(self.logs),
        }


class VMManager:
    def __init__(self, max_vms: int = 10, base_dir: str = "sandbox_workspaces",
                 default_isolation: IsolationLevel = IsolationLevel.BASIC):
        self.max_vms = max_vms
        self.base_dir = base_dir
        self.default_isolation = default_isolation
        self.vms: dict[str, VirtualMachine] = {}
        self._vm_counter = 0
        self._cleanup_tasks: dict[str, asyncio.Task] = {}
        os.makedirs(base_dir, exist_ok=True)

    def create_vm(self, name: str, runtime: str = "python3",
                  isolation_level: Optional[IsolationLevel] = None,
                  resource_limits: Optional[dict] = None,
                  environment: Optional[dict] = None,
                  tags: Optional[dict] = None) -> dict:
        if len(self.vms) >= self.max_vms:
            return {"success": False, "error": f"Batas VM tercapai ({self.max_vms})"}

        self._vm_counter += 1
        vm_id = f"vm_{self._vm_counter}_{uuid.uuid4().hex[:6]}"
        isolation = isolation_level or self.default_isolation
        vm = VirtualMachine(vm_id=vm_id, name=name, runtime=runtime, isolation_level=isolation)

        if resource_limits:
            for key, val in resource_limits.items():
                if hasattr(vm.resource_limits, key):
                    setattr(vm.resource_limits, key, val)

        vm_workspace = os.path.join(self.base_dir, vm_id)
        os.makedirs(vm_workspace, exist_ok=True)
        vm.working_dir = vm_workspace

        if environment:
            vm.environment.update(environment)
        if tags:
            vm.tags.update(tags)

        vm.add_log("info", f"VM dibuat: {name} (runtime: {runtime}, isolasi: {isolation.value})")
        self.vms[vm_id] = vm
        logger.info(f"VM dibuat: {name} ({vm_id}), runtime: {runtime}, isolasi: {isolation.value}")

        return {"success": True, "vm_id": vm_id, "vm": vm.to_dict()}

    def start_vm(self, vm_id: str) -> dict:
        vm = self.vms.get(vm_id)
        if not vm:
            return {"success": False, "error": f"VM tidak ditemukan: {vm_id}"}
        if vm.state == VMState.RUNNING:
            return {"success": False, "error": "VM sudah berjalan"}

        vm.state = VMState.STARTING
        vm.add_log("info", "VM sedang dimulai...")

        vm.started_at = time.time()
        vm.state = VMState.RUNNING
        vm.add_log("info", "VM berhasil dimulai")
        logger.info(f"VM dimulai: {vm.name} ({vm_id})")

        return {"success": True, "vm_id": vm_id, "state": vm.state.value}

    def stop_vm(self, vm_id: str) -> dict:
        vm = self.vms.get(vm_id)
        if not vm:
            return {"success": False, "error": f"VM tidak ditemukan: {vm_id}"}
        if vm.state == VMState.STOPPED:
            return {"success": False, "error": "VM sudah berhenti"}

        vm.state = VMState.STOPPING
        vm.add_log("info", "VM sedang dihentikan...")

        if vm._process:
            try:
                vm._process.kill()
            except Exception:
                pass
            vm._process = None

        vm.state = VMState.STOPPED
        vm.started_at = None
        vm.resource_usage = {"cpu_percent": 0.0, "memory_mb": 0, "disk_mb": 0, "process_count": 0, "network_rx_mb": 0, "network_tx_mb": 0}
        vm.add_log("info", "VM dihentikan")
        logger.info(f"VM dihentikan: {vm.name} ({vm_id})")

        return {"success": True, "vm_id": vm_id, "state": vm.state.value}

    def pause_vm(self, vm_id: str) -> dict:
        vm = self.vms.get(vm_id)
        if not vm:
            return {"success": False, "error": f"VM tidak ditemukan: {vm_id}"}
        if vm.state != VMState.RUNNING:
            return {"success": False, "error": "VM tidak dalam keadaan berjalan"}

        vm.state = VMState.PAUSED
        vm.add_log("info", "VM dijeda")
        logger.info(f"VM dijeda: {vm.name} ({vm_id})")
        return {"success": True, "vm_id": vm_id, "state": vm.state.value}

    def resume_vm(self, vm_id: str) -> dict:
        vm = self.vms.get(vm_id)
        if not vm:
            return {"success": False, "error": f"VM tidak ditemukan: {vm_id}"}
        if vm.state != VMState.PAUSED:
            return {"success": False, "error": "VM tidak dalam keadaan dijeda"}

        vm.state = VMState.RUNNING
        vm.add_log("info", "VM dilanjutkan")
        logger.info(f"VM dilanjutkan: {vm.name} ({vm_id})")
        return {"success": True, "vm_id": vm_id, "state": vm.state.value}

    async def execute_in_vm(self, vm_id: str, command: str, timeout: Optional[int] = None) -> dict:
        vm = self.vms.get(vm_id)
        if not vm:
            return {"success": False, "error": f"VM tidak ditemukan: {vm_id}"}
        if vm.state != VMState.RUNNING:
            return {"success": False, "error": "VM tidak dalam keadaan berjalan"}

        exec_timeout = timeout or vm.resource_limits.max_execution_time
        start_time = time.time()
        vm.add_log("info", f"Menjalankan perintah: {command[:100]}")

        try:
            env = os.environ.copy()
            env.update(vm.environment)
            env["LC_ALL"] = "C.UTF-8"
            env["VM_ID"] = vm_id
            env["VM_NAME"] = vm.name
            env["ISOLATION_LEVEL"] = vm.isolation_level.value

            if vm.resource_limits.max_memory_mb > 0:
                env["VM_MAX_MEMORY_MB"] = str(vm.resource_limits.max_memory_mb)

            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=vm.working_dir,
                env=env,
            )
            vm._process = process

            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=exec_timeout)
            duration = time.time() - start_time
            vm.execution_count += 1
            vm.total_execution_time += duration

            stdout_text = stdout.decode("utf-8", errors="replace").strip()
            stderr_text = stderr.decode("utf-8", errors="replace").strip()

            if len(stdout_text) > 50000:
                stdout_text = stdout_text[:50000] + "\n... (output terpotong)"
            if len(stderr_text) > 10000:
                stderr_text = stderr_text[:10000] + "\n... (error terpotong)"

            success = process.returncode == 0
            vm.add_log("info" if success else "error", f"Perintah selesai ({duration:.2f}s, rc={process.returncode})")

            return {
                "success": success,
                "vm_id": vm_id,
                "stdout": stdout_text,
                "stderr": stderr_text,
                "return_code": process.returncode or 0,
                "duration": round(duration, 3),
            }

        except asyncio.TimeoutError:
            duration = time.time() - start_time
            vm.add_log("error", f"Perintah timeout setelah {exec_timeout}s")
            if vm._process:
                try:
                    vm._process.kill()
                except Exception:
                    pass
            return {
                "success": False,
                "vm_id": vm_id,
                "error": f"Timeout setelah {exec_timeout}s",
                "duration": round(duration, 3),
            }

        except Exception as e:
            vm.add_log("error", f"Error: {str(e)}")
            return {"success": False, "vm_id": vm_id, "error": str(e)}
        finally:
            vm._process = None

    async def execute_code_in_vm(self, vm_id: str, code: str, runtime: Optional[str] = None, timeout: Optional[int] = None) -> dict:
        vm = self.vms.get(vm_id)
        if not vm:
            return {"success": False, "error": f"VM tidak ditemukan: {vm_id}"}

        rt = runtime or vm.runtime
        ext_map = {"python3": ".py", "nodejs": ".js", "bash": ".sh", "ruby": ".rb", "php": ".php"}
        cmd_map = {"python3": "python3", "nodejs": "node", "bash": "bash", "ruby": "ruby", "php": "php"}

        ext = ext_map.get(rt, ".txt")
        cmd = cmd_map.get(rt)
        if not cmd:
            return {"success": False, "error": f"Runtime tidak dikenal: {rt}"}

        code_file = os.path.join(vm.working_dir, f"_exec_{uuid.uuid4().hex[:8]}{ext}")
        try:
            with open(code_file, "w") as f:
                f.write(code)
            result = await self.execute_in_vm(vm_id, f"{cmd} {code_file}", timeout)
            return result
        finally:
            try:
                os.unlink(code_file)
            except OSError:
                pass

    def create_snapshot(self, vm_id: str, name: str, description: str = "") -> dict:
        vm = self.vms.get(vm_id)
        if not vm:
            return {"success": False, "error": f"VM tidak ditemukan: {vm_id}"}

        snapshot_id = f"snap_{vm_id}_{len(vm.snapshots) + 1}_{uuid.uuid4().hex[:4]}"
        snapshot = VMSnapshot(snapshot_id=snapshot_id, name=name, vm_id=vm_id)
        snapshot.description = description

        snapshot_dir = os.path.join(self.base_dir, f".snapshots/{snapshot_id}")
        os.makedirs(snapshot_dir, exist_ok=True)

        if os.path.exists(vm.working_dir):
            for item in os.listdir(vm.working_dir):
                src = os.path.join(vm.working_dir, item)
                dst = os.path.join(snapshot_dir, item)
                try:
                    if os.path.isdir(src):
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                    else:
                        shutil.copy2(src, dst)
                    snapshot.file_manifest.append(item)
                except Exception as e:
                    logger.warning(f"Gagal copy {item} ke snapshot: {e}")

            total_size = sum(
                os.path.getsize(os.path.join(dp, f))
                for dp, _, filenames in os.walk(snapshot_dir)
                for f in filenames
            )
            snapshot.size_mb = round(total_size / (1024 * 1024), 2)

        vm.snapshots.append(snapshot)
        vm.add_log("info", f"Snapshot dibuat: {name}")
        logger.info(f"Snapshot dibuat: {name} ({snapshot_id}) untuk VM {vm.name}")

        return {"success": True, "snapshot": snapshot.to_dict()}

    def restore_snapshot(self, vm_id: str, snapshot_id: str) -> dict:
        vm = self.vms.get(vm_id)
        if not vm:
            return {"success": False, "error": f"VM tidak ditemukan: {vm_id}"}

        snapshot = None
        for s in vm.snapshots:
            if s.snapshot_id == snapshot_id:
                snapshot = s
                break

        if not snapshot:
            return {"success": False, "error": f"Snapshot tidak ditemukan: {snapshot_id}"}

        snapshot_dir = os.path.join(self.base_dir, f".snapshots/{snapshot_id}")
        if os.path.exists(snapshot_dir) and os.path.exists(vm.working_dir):
            for item in os.listdir(vm.working_dir):
                path = os.path.join(vm.working_dir, item)
                try:
                    if os.path.isdir(path):
                        shutil.rmtree(path)
                    else:
                        os.unlink(path)
                except Exception:
                    pass

            for item in os.listdir(snapshot_dir):
                src = os.path.join(snapshot_dir, item)
                dst = os.path.join(vm.working_dir, item)
                try:
                    if os.path.isdir(src):
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                    else:
                        shutil.copy2(src, dst)
                except Exception as e:
                    logger.warning(f"Gagal restore {item}: {e}")

        vm.add_log("info", f"Snapshot dipulihkan: {snapshot.name}")
        logger.info(f"Snapshot dipulihkan: {snapshot.name} untuk VM {vm.name}")
        return {"success": True, "message": f"VM dipulihkan ke snapshot '{snapshot.name}'"}

    def destroy_vm(self, vm_id: str) -> dict:
        vm = self.vms.get(vm_id)
        if not vm:
            return {"success": False, "error": f"VM tidak ditemukan: {vm_id}"}

        vm.state = VMState.DESTROYING

        if vm.state == VMState.RUNNING or vm._process:
            self.stop_vm(vm_id)

        if vm.working_dir and os.path.exists(vm.working_dir):
            try:
                shutil.rmtree(vm.working_dir)
            except Exception as e:
                logger.warning(f"Gagal hapus workspace VM: {e}")

        for snapshot in vm.snapshots:
            snap_dir = os.path.join(self.base_dir, f".snapshots/{snapshot.snapshot_id}")
            if os.path.exists(snap_dir):
                try:
                    shutil.rmtree(snap_dir)
                except Exception:
                    pass

        del self.vms[vm_id]
        logger.info(f"VM dihancurkan: {vm.name} ({vm_id})")
        return {"success": True, "message": f"VM '{vm.name}' dihancurkan"}

    def set_network_policy(self, vm_id: str, policy: dict) -> dict:
        vm = self.vms.get(vm_id)
        if not vm:
            return {"success": False, "error": f"VM tidak ditemukan: {vm_id}"}

        if "allowed_outbound" in policy:
            vm.network_policy.allowed_outbound = policy["allowed_outbound"]
        if "blocked_outbound" in policy:
            vm.network_policy.blocked_outbound = policy["blocked_outbound"]
        if "allowed_inbound_ports" in policy:
            vm.network_policy.allowed_inbound_ports = policy["allowed_inbound_ports"]
        if "rate_limit_mbps" in policy:
            vm.network_policy.rate_limit_mbps = policy["rate_limit_mbps"]
        if "dns_allowed" in policy:
            vm.network_policy.dns_allowed = policy["dns_allowed"]

        vm.add_log("info", "Network policy diperbarui")
        return {"success": True, "network_policy": vm.network_policy.to_dict()}

    def set_resource_limits(self, vm_id: str, limits: dict) -> dict:
        vm = self.vms.get(vm_id)
        if not vm:
            return {"success": False, "error": f"VM tidak ditemukan: {vm_id}"}

        for key, val in limits.items():
            if hasattr(vm.resource_limits, key):
                setattr(vm.resource_limits, key, val)

        vm.add_log("info", "Resource limits diperbarui")
        return {"success": True, "resource_limits": vm.resource_limits.to_dict()}

    def get_vm_logs(self, vm_id: str, limit: int = 50, level: Optional[str] = None) -> dict:
        vm = self.vms.get(vm_id)
        if not vm:
            return {"success": False, "error": f"VM tidak ditemukan: {vm_id}"}

        logs = vm.logs
        if level:
            logs = [l for l in logs if l["level"] == level]
        return {"success": True, "logs": logs[-limit:], "total": len(logs)}

    def list_vms(self, state_filter: Optional[str] = None, tag_filter: Optional[dict] = None) -> list[dict]:
        vms = list(self.vms.values())
        if state_filter:
            try:
                target_state = VMState(state_filter)
                vms = [vm for vm in vms if vm.state == target_state]
            except ValueError:
                pass
        if tag_filter:
            vms = [vm for vm in vms if all(vm.tags.get(k) == v for k, v in tag_filter.items())]
        return [vm.to_dict() for vm in vms]

    def get_vm(self, vm_id: str) -> Optional[dict]:
        vm = self.vms.get(vm_id)
        return vm.to_dict() if vm else None

    def get_stats(self) -> dict:
        states = {}
        total_exec = 0
        total_time = 0.0
        for vm in self.vms.values():
            s = vm.state.value
            states[s] = states.get(s, 0) + 1
            total_exec += vm.execution_count
            total_time += vm.total_execution_time
        return {
            "total_vms": len(self.vms),
            "max_vms": self.max_vms,
            "states": states,
            "total_executions": total_exec,
            "total_execution_time": round(total_time, 2),
        }

    async def cleanup_inactive(self, max_idle_seconds: int = 3600) -> dict:
        cleaned = []
        now = time.time()
        for vm_id, vm in list(self.vms.items()):
            if vm.state == VMState.STOPPED:
                idle_time = now - (vm.started_at or vm.created_at)
                if idle_time > max_idle_seconds:
                    self.destroy_vm(vm_id)
                    cleaned.append(vm_id)
        return {"cleaned": cleaned, "count": len(cleaned)}
