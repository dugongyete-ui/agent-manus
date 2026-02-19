"""VM Manager - Mengelola siklus hidup VM (start, stop, snapshot)."""

import logging
import os
import time
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class VMState(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    ERROR = "error"


class VMSnapshot:
    def __init__(self, snapshot_id: str, name: str, vm_id: str):
        self.snapshot_id = snapshot_id
        self.name = name
        self.vm_id = vm_id
        self.created_at = time.time()
        self.size_mb = 0

    def to_dict(self) -> dict:
        return {
            "snapshot_id": self.snapshot_id,
            "name": self.name,
            "vm_id": self.vm_id,
            "created_at": self.created_at,
            "size_mb": self.size_mb,
        }


class VirtualMachine:
    def __init__(self, vm_id: str, name: str, runtime: str = "python3"):
        self.vm_id = vm_id
        self.name = name
        self.runtime = runtime
        self.state = VMState.STOPPED
        self.created_at = time.time()
        self.started_at: Optional[float] = None
        self.resource_usage = {"cpu_percent": 0.0, "memory_mb": 0, "disk_mb": 0}
        self.environment: dict[str, str] = {}
        self.snapshots: list[VMSnapshot] = []

    def to_dict(self) -> dict:
        return {
            "vm_id": self.vm_id,
            "name": self.name,
            "runtime": self.runtime,
            "state": self.state.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "resource_usage": self.resource_usage,
            "snapshots": [s.to_dict() for s in self.snapshots],
        }


class VMManager:
    def __init__(self, max_vms: int = 5, resource_limits: Optional[dict] = None):
        self.max_vms = max_vms
        self.resource_limits = resource_limits or {"max_memory_mb": 2048, "max_cpu_percent": 80}
        self.vms: dict[str, VirtualMachine] = {}
        self._vm_counter = 0

    def create_vm(self, name: str, runtime: str = "python3") -> dict:
        if len(self.vms) >= self.max_vms:
            return {"success": False, "error": f"Batas VM tercapai ({self.max_vms})"}

        self._vm_counter += 1
        vm_id = f"vm_{self._vm_counter}"
        vm = VirtualMachine(vm_id=vm_id, name=name, runtime=runtime)
        self.vms[vm_id] = vm
        logger.info(f"VM dibuat: {name} ({vm_id}), runtime: {runtime}")

        return {"success": True, "vm_id": vm_id, "vm": vm.to_dict()}

    def start_vm(self, vm_id: str) -> dict:
        vm = self.vms.get(vm_id)
        if not vm:
            return {"success": False, "error": f"VM tidak ditemukan: {vm_id}"}
        if vm.state == VMState.RUNNING:
            return {"success": False, "error": "VM sudah berjalan"}

        vm.state = VMState.STARTING
        vm.started_at = time.time()
        vm.state = VMState.RUNNING
        logger.info(f"VM dimulai: {vm.name} ({vm_id})")

        return {"success": True, "vm_id": vm_id, "state": vm.state.value}

    def stop_vm(self, vm_id: str) -> dict:
        vm = self.vms.get(vm_id)
        if not vm:
            return {"success": False, "error": f"VM tidak ditemukan: {vm_id}"}
        if vm.state == VMState.STOPPED:
            return {"success": False, "error": "VM sudah berhenti"}

        vm.state = VMState.STOPPING
        vm.state = VMState.STOPPED
        vm.started_at = None
        logger.info(f"VM dihentikan: {vm.name} ({vm_id})")

        return {"success": True, "vm_id": vm_id, "state": vm.state.value}

    def pause_vm(self, vm_id: str) -> dict:
        vm = self.vms.get(vm_id)
        if not vm:
            return {"success": False, "error": f"VM tidak ditemukan: {vm_id}"}
        if vm.state != VMState.RUNNING:
            return {"success": False, "error": "VM tidak dalam keadaan berjalan"}

        vm.state = VMState.PAUSED
        logger.info(f"VM dijeda: {vm.name} ({vm_id})")
        return {"success": True, "vm_id": vm_id, "state": vm.state.value}

    def resume_vm(self, vm_id: str) -> dict:
        vm = self.vms.get(vm_id)
        if not vm:
            return {"success": False, "error": f"VM tidak ditemukan: {vm_id}"}
        if vm.state != VMState.PAUSED:
            return {"success": False, "error": "VM tidak dalam keadaan dijeda"}

        vm.state = VMState.RUNNING
        logger.info(f"VM dilanjutkan: {vm.name} ({vm_id})")
        return {"success": True, "vm_id": vm_id, "state": vm.state.value}

    def create_snapshot(self, vm_id: str, name: str) -> dict:
        vm = self.vms.get(vm_id)
        if not vm:
            return {"success": False, "error": f"VM tidak ditemukan: {vm_id}"}

        snapshot_id = f"snap_{vm_id}_{len(vm.snapshots) + 1}"
        snapshot = VMSnapshot(snapshot_id=snapshot_id, name=name, vm_id=vm_id)
        vm.snapshots.append(snapshot)
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

        logger.info(f"Snapshot dipulihkan: {snapshot.name} untuk VM {vm.name}")
        return {"success": True, "message": f"VM dipulihkan ke snapshot '{snapshot.name}'"}

    def destroy_vm(self, vm_id: str) -> dict:
        vm = self.vms.get(vm_id)
        if not vm:
            return {"success": False, "error": f"VM tidak ditemukan: {vm_id}"}
        if vm.state == VMState.RUNNING:
            self.stop_vm(vm_id)
        del self.vms[vm_id]
        logger.info(f"VM dihancurkan: {vm.name} ({vm_id})")
        return {"success": True, "message": f"VM '{vm.name}' dihancurkan"}

    def list_vms(self) -> list[dict]:
        return [vm.to_dict() for vm in self.vms.values()]

    def get_vm(self, vm_id: str) -> Optional[dict]:
        vm = self.vms.get(vm_id)
        return vm.to_dict() if vm else None
