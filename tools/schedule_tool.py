"""Schedule Tool - Logika untuk penjadwalan tugas."""

import asyncio
import logging
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class ScheduledTask:
    def __init__(self, task_id: str, name: str, interval: int, callback_name: str, enabled: bool = True):
        self.task_id = task_id
        self.name = name
        self.interval = interval
        self.callback_name = callback_name
        self.enabled = enabled
        self.last_run: Optional[float] = None
        self.next_run: float = time.time() + interval
        self.run_count = 0
        self.created_at = time.time()

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "interval": self.interval,
            "callback": self.callback_name,
            "enabled": self.enabled,
            "last_run": self.last_run,
            "next_run": self.next_run,
            "run_count": self.run_count,
        }


class ScheduleTool:
    def __init__(self, max_tasks: int = 100, min_interval: int = 60):
        self.max_tasks = max_tasks
        self.min_interval = min_interval
        self.tasks: dict[str, ScheduledTask] = {}
        self._task_counter = 0
        self._running = False
        self._callbacks: dict[str, Callable] = {}

    async def execute(self, plan: dict) -> str:
        intent = plan.get("intent", "")
        return (
            f"Schedule tool siap. Intent: {intent}. "
            f"Tugas terjadwal aktif: {len(self.tasks)}. "
            f"Operasi: create_task, cancel_task, list_tasks."
        )

    def register_callback(self, name: str, callback: Callable):
        self._callbacks[name] = callback
        logger.info(f"Callback terdaftar: {name}")

    def create_task(self, name: str, interval: int, callback_name: str) -> dict:
        if len(self.tasks) >= self.max_tasks:
            return {"success": False, "error": f"Batas tugas tercapai ({self.max_tasks})"}

        if interval < self.min_interval:
            return {"success": False, "error": f"Interval minimum: {self.min_interval} detik"}

        self._task_counter += 1
        task_id = f"sched_{self._task_counter}"
        task = ScheduledTask(
            task_id=task_id,
            name=name,
            interval=interval,
            callback_name=callback_name,
        )
        self.tasks[task_id] = task
        logger.info(f"Tugas terjadwal dibuat: {name} (setiap {interval}s)")

        return {"success": True, "task_id": task_id, "task": task.to_dict()}

    def cancel_task(self, task_id: str) -> dict:
        if task_id not in self.tasks:
            return {"success": False, "error": f"Tugas tidak ditemukan: {task_id}"}
        task = self.tasks.pop(task_id)
        logger.info(f"Tugas dibatalkan: {task.name}")
        return {"success": True, "message": f"Tugas '{task.name}' dibatalkan"}

    def pause_task(self, task_id: str) -> dict:
        if task_id not in self.tasks:
            return {"success": False, "error": f"Tugas tidak ditemukan: {task_id}"}
        self.tasks[task_id].enabled = False
        return {"success": True, "message": "Tugas dijeda"}

    def resume_task(self, task_id: str) -> dict:
        if task_id not in self.tasks:
            return {"success": False, "error": f"Tugas tidak ditemukan: {task_id}"}
        self.tasks[task_id].enabled = True
        self.tasks[task_id].next_run = time.time() + self.tasks[task_id].interval
        return {"success": True, "message": "Tugas dilanjutkan"}

    def list_tasks(self) -> list[dict]:
        return [task.to_dict() for task in self.tasks.values()]

    async def start_scheduler(self):
        self._running = True
        logger.info("Scheduler dimulai")
        while self._running:
            now = time.time()
            for task in self.tasks.values():
                if task.enabled and now >= task.next_run:
                    callback = self._callbacks.get(task.callback_name)
                    if callback:
                        try:
                            if asyncio.iscoroutinefunction(callback):
                                await callback()
                            else:
                                callback()
                            task.run_count += 1
                            task.last_run = now
                        except Exception as e:
                            logger.error(f"Error menjalankan tugas '{task.name}': {e}")
                    task.next_run = now + task.interval
            await asyncio.sleep(1)

    def stop_scheduler(self):
        self._running = False
        logger.info("Scheduler dihentikan")
