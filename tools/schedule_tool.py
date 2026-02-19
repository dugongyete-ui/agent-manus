"""Schedule Tool - Penjadwalan & Otomatisasi Tugas dengan cron, interval, one-time."""

import asyncio
import json
import logging
import os
import time
import re
from datetime import datetime, timedelta
from typing import Callable, Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    INTERVAL = "interval"
    CRON = "cron"
    ONCE = "once"


class TaskStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CronParser:
    @staticmethod
    def parse(expression: str) -> dict:
        parts = expression.strip().split()
        if len(parts) != 5:
            raise ValueError(f"Cron expression harus 5 bagian (menit jam hari bulan hari_minggu), dapat: {expression}")

        fields = ["minute", "hour", "day", "month", "weekday"]
        result = {}
        ranges = {
            "minute": (0, 59),
            "hour": (0, 23),
            "day": (1, 31),
            "month": (1, 12),
            "weekday": (0, 6),
        }

        for i, (field, part) in enumerate(zip(fields, parts)):
            result[field] = CronParser._parse_field(part, ranges[field])
        return result

    @staticmethod
    def _parse_field(field: str, value_range: tuple) -> list[int]:
        min_val, max_val = value_range

        if field == "*":
            return list(range(min_val, max_val + 1))

        if "/" in field:
            base, step = field.split("/", 1)
            step = int(step)
            if base == "*":
                return list(range(min_val, max_val + 1, step))
            start = int(base)
            return list(range(start, max_val + 1, step))

        if "-" in field:
            start, end = field.split("-", 1)
            return list(range(int(start), int(end) + 1))

        if "," in field:
            return [int(v) for v in field.split(",")]

        return [int(field)]

    @staticmethod
    def matches(cron_fields: dict, dt: datetime) -> bool:
        return (
            dt.minute in cron_fields["minute"]
            and dt.hour in cron_fields["hour"]
            and dt.day in cron_fields["day"]
            and dt.month in cron_fields["month"]
            and dt.weekday() in cron_fields["weekday"]
        )

    @staticmethod
    def next_run(cron_fields: dict, from_dt: datetime = None) -> datetime:
        dt = from_dt or datetime.now()
        dt = dt.replace(second=0, microsecond=0) + timedelta(minutes=1)

        for _ in range(525600):
            if CronParser.matches(cron_fields, dt):
                return dt
            dt += timedelta(minutes=1)
        return dt


class ScheduledTask:
    def __init__(
        self,
        task_id: str,
        name: str,
        task_type: TaskType,
        callback_name: str,
        interval: int = 0,
        cron_expression: str = "",
        run_at: float = 0,
        description: str = "",
        max_runs: int = 0,
        notify_on_complete: bool = True,
        notify_on_error: bool = True,
        enabled: bool = True,
    ):
        self.task_id = task_id
        self.name = name
        self.task_type = task_type
        self.callback_name = callback_name
        self.interval = interval
        self.cron_expression = cron_expression
        self.cron_fields = None
        self.run_at = run_at
        self.description = description
        self.max_runs = max_runs
        self.notify_on_complete = notify_on_complete
        self.notify_on_error = notify_on_error
        self.enabled = enabled
        self.status = TaskStatus.ACTIVE
        self.last_run: Optional[float] = None
        self.next_run: float = 0
        self.run_count = 0
        self.error_count = 0
        self.last_error: str = ""
        self.last_result: str = ""
        self.created_at = time.time()
        self.history: list[dict] = []

        if task_type == TaskType.CRON and cron_expression:
            self.cron_fields = CronParser.parse(cron_expression)
            self.next_run = CronParser.next_run(self.cron_fields).timestamp()
        elif task_type == TaskType.INTERVAL:
            self.next_run = time.time() + interval
        elif task_type == TaskType.ONCE:
            self.next_run = run_at if run_at > 0 else time.time()

    def should_run(self, now: float) -> bool:
        if not self.enabled or self.status != TaskStatus.ACTIVE:
            return False
        if self.max_runs > 0 and self.run_count >= self.max_runs:
            return False
        return now >= self.next_run

    def record_execution(self, success: bool, result: str = "", error: str = "", duration_ms: int = 0):
        self.run_count += 1
        self.last_run = time.time()

        entry = {
            "run_number": self.run_count,
            "timestamp": self.last_run,
            "success": success,
            "duration_ms": duration_ms,
        }

        if success:
            self.last_result = result[:500]
            entry["result"] = result[:200]
        else:
            self.error_count += 1
            self.last_error = error[:500]
            entry["error"] = error[:200]

        self.history.append(entry)
        if len(self.history) > 50:
            self.history = self.history[-50:]

        if self.task_type == TaskType.INTERVAL:
            self.next_run = time.time() + self.interval
        elif self.task_type == TaskType.CRON and self.cron_fields:
            self.next_run = CronParser.next_run(self.cron_fields).timestamp()
        elif self.task_type == TaskType.ONCE:
            self.status = TaskStatus.COMPLETED

        if self.max_runs > 0 and self.run_count >= self.max_runs:
            self.status = TaskStatus.COMPLETED

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "type": self.task_type.value,
            "callback": self.callback_name,
            "interval": self.interval,
            "cron_expression": self.cron_expression,
            "run_at": self.run_at,
            "description": self.description,
            "max_runs": self.max_runs,
            "enabled": self.enabled,
            "status": self.status.value,
            "last_run": self.last_run,
            "next_run": self.next_run,
            "run_count": self.run_count,
            "error_count": self.error_count,
            "last_result": self.last_result,
            "last_error": self.last_error,
            "created_at": self.created_at,
            "notify_on_complete": self.notify_on_complete,
            "notify_on_error": self.notify_on_error,
            "history_count": len(self.history),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ScheduledTask":
        task = cls(
            task_id=data["task_id"],
            name=data["name"],
            task_type=TaskType(data.get("type", "interval")),
            callback_name=data.get("callback", "default"),
            interval=data.get("interval", 0),
            cron_expression=data.get("cron_expression", ""),
            run_at=data.get("run_at", 0),
            description=data.get("description", ""),
            max_runs=data.get("max_runs", 0),
            notify_on_complete=data.get("notify_on_complete", True),
            notify_on_error=data.get("notify_on_error", True),
            enabled=data.get("enabled", True),
        )
        task.status = TaskStatus(data.get("status", "active"))
        task.last_run = data.get("last_run")
        task.next_run = data.get("next_run", task.next_run)
        task.run_count = data.get("run_count", 0)
        task.error_count = data.get("error_count", 0)
        task.last_result = data.get("last_result", "")
        task.last_error = data.get("last_error", "")
        task.created_at = data.get("created_at", time.time())
        task.history = data.get("history", [])
        return task


class ScheduleTool:
    def __init__(self, max_tasks: int = 100, min_interval: int = 10, persist_path: str = "data/scheduled_tasks.json"):
        self.max_tasks = max_tasks
        self.min_interval = min_interval
        self.persist_path = persist_path
        self.tasks: dict[str, ScheduledTask] = {}
        self._task_counter = 0
        self._running = False
        self._scheduler_task: Optional[asyncio.Task] = None
        self._callbacks: dict[str, Callable] = {}
        self._notification_callback: Optional[Callable] = None
        self._load_tasks()

        self.register_callback("log", self._default_log_callback)
        self.register_callback("default", self._default_log_callback)

    async def execute(self, plan: dict) -> str:
        action = plan.get("action", plan.get("intent", ""))
        params = plan.get("params", plan)

        if action in ("create", "create_task", "add", "schedule"):
            return json.dumps(self._handle_create(params), ensure_ascii=False)
        elif action in ("create_cron", "cron"):
            return json.dumps(self._handle_create_cron(params), ensure_ascii=False)
        elif action in ("create_once", "once", "schedule_once"):
            return json.dumps(self._handle_create_once(params), ensure_ascii=False)
        elif action in ("cancel", "cancel_task", "delete", "remove"):
            task_id = params.get("task_id", "")
            return json.dumps(self.cancel_task(task_id), ensure_ascii=False)
        elif action in ("pause", "pause_task"):
            task_id = params.get("task_id", "")
            return json.dumps(self.pause_task(task_id), ensure_ascii=False)
        elif action in ("resume", "resume_task"):
            task_id = params.get("task_id", "")
            return json.dumps(self.resume_task(task_id), ensure_ascii=False)
        elif action in ("list", "list_tasks"):
            return json.dumps({"tasks": self.list_tasks()}, ensure_ascii=False)
        elif action in ("status", "get_status"):
            task_id = params.get("task_id", "")
            return json.dumps(self.get_task_status(task_id), ensure_ascii=False)
        elif action in ("history", "get_history"):
            task_id = params.get("task_id", "")
            return json.dumps(self.get_task_history(task_id), ensure_ascii=False)
        elif action in ("stats", "statistics"):
            return json.dumps(self.get_stats(), ensure_ascii=False)
        else:
            return json.dumps({
                "info": "Schedule Tool - Penjadwalan & Otomatisasi Tugas",
                "active_tasks": len([t for t in self.tasks.values() if t.status == TaskStatus.ACTIVE]),
                "total_tasks": len(self.tasks),
                "actions": [
                    "create - Buat tugas interval (name, interval, callback)",
                    "create_cron - Buat tugas cron (name, cron_expression, callback)",
                    "create_once - Buat tugas sekali jalan (name, delay_seconds/run_at, callback)",
                    "cancel - Batalkan tugas (task_id)",
                    "pause - Jeda tugas (task_id)",
                    "resume - Lanjutkan tugas (task_id)",
                    "list - Daftar semua tugas",
                    "status - Status tugas (task_id)",
                    "history - Riwayat eksekusi tugas (task_id)",
                    "stats - Statistik scheduler",
                ],
            }, ensure_ascii=False)

    def _handle_create(self, params: dict) -> dict:
        name = params.get("name", "Tugas Baru")
        interval = params.get("interval", 60)
        callback_name = params.get("callback", "default")
        description = params.get("description", "")
        max_runs = params.get("max_runs", 0)
        notify = params.get("notify", True)
        return self.create_task(name, interval, callback_name, description, max_runs, notify)

    def _handle_create_cron(self, params: dict) -> dict:
        name = params.get("name", "Tugas Cron")
        cron_expr = params.get("cron_expression", params.get("cron", ""))
        callback_name = params.get("callback", "default")
        description = params.get("description", "")
        max_runs = params.get("max_runs", 0)
        notify = params.get("notify", True)
        return self.create_cron_task(name, cron_expr, callback_name, description, max_runs, notify)

    def _handle_create_once(self, params: dict) -> dict:
        name = params.get("name", "Tugas Sekali")
        delay = params.get("delay_seconds", params.get("delay", 0))
        run_at = params.get("run_at", 0)
        callback_name = params.get("callback", "default")
        description = params.get("description", "")
        notify = params.get("notify", True)

        if delay > 0:
            run_at = time.time() + delay

        return self.create_once_task(name, run_at, callback_name, description, notify)

    def set_notification_callback(self, callback: Callable):
        self._notification_callback = callback

    def register_callback(self, name: str, callback: Callable):
        self._callbacks[name] = callback
        logger.info(f"Callback terdaftar: {name}")

    def _default_log_callback(self):
        return "Task executed (default callback)"

    async def _notify(self, title: str, body: str, level: str = "info"):
        if self._notification_callback:
            try:
                result = self._notification_callback(title, body, level)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Notifikasi gagal: {e}")

    def create_task(self, name: str, interval: int, callback_name: str = "default",
                    description: str = "", max_runs: int = 0, notify: bool = True) -> dict:
        if len(self.tasks) >= self.max_tasks:
            return {"success": False, "error": f"Batas tugas tercapai ({self.max_tasks})"}
        if interval < self.min_interval:
            return {"success": False, "error": f"Interval minimum: {self.min_interval} detik"}

        self._task_counter += 1
        task_id = f"sched_{self._task_counter}"
        task = ScheduledTask(
            task_id=task_id, name=name, task_type=TaskType.INTERVAL,
            callback_name=callback_name, interval=interval,
            description=description, max_runs=max_runs,
            notify_on_complete=notify, notify_on_error=notify,
        )
        self.tasks[task_id] = task
        self._save_tasks()
        logger.info(f"Tugas interval dibuat: {name} (setiap {interval}s)")
        return {"success": True, "task_id": task_id, "task": task.to_dict()}

    def create_cron_task(self, name: str, cron_expression: str, callback_name: str = "default",
                         description: str = "", max_runs: int = 0, notify: bool = True) -> dict:
        if len(self.tasks) >= self.max_tasks:
            return {"success": False, "error": f"Batas tugas tercapai ({self.max_tasks})"}

        try:
            CronParser.parse(cron_expression)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        self._task_counter += 1
        task_id = f"cron_{self._task_counter}"
        task = ScheduledTask(
            task_id=task_id, name=name, task_type=TaskType.CRON,
            callback_name=callback_name, cron_expression=cron_expression,
            description=description, max_runs=max_runs,
            notify_on_complete=notify, notify_on_error=notify,
        )
        self.tasks[task_id] = task
        self._save_tasks()
        next_dt = datetime.fromtimestamp(task.next_run).strftime("%Y-%m-%d %H:%M")
        logger.info(f"Tugas cron dibuat: {name} ({cron_expression}), berikutnya: {next_dt}")
        return {"success": True, "task_id": task_id, "next_run": next_dt, "task": task.to_dict()}

    def create_once_task(self, name: str, run_at: float, callback_name: str = "default",
                         description: str = "", notify: bool = True) -> dict:
        if len(self.tasks) >= self.max_tasks:
            return {"success": False, "error": f"Batas tugas tercapai ({self.max_tasks})"}

        if run_at <= 0:
            run_at = time.time() + 60

        self._task_counter += 1
        task_id = f"once_{self._task_counter}"
        task = ScheduledTask(
            task_id=task_id, name=name, task_type=TaskType.ONCE,
            callback_name=callback_name, run_at=run_at,
            description=description, max_runs=1,
            notify_on_complete=notify, notify_on_error=notify,
        )
        self.tasks[task_id] = task
        self._save_tasks()
        run_dt = datetime.fromtimestamp(run_at).strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"Tugas sekali dibuat: {name}, dijadwalkan: {run_dt}")
        return {"success": True, "task_id": task_id, "run_at": run_dt, "task": task.to_dict()}

    def cancel_task(self, task_id: str) -> dict:
        if task_id not in self.tasks:
            return {"success": False, "error": f"Tugas tidak ditemukan: {task_id}"}
        task = self.tasks[task_id]
        task.status = TaskStatus.CANCELLED
        task.enabled = False
        self._save_tasks()
        logger.info(f"Tugas dibatalkan: {task.name}")
        return {"success": True, "message": f"Tugas '{task.name}' dibatalkan"}

    def remove_task(self, task_id: str) -> dict:
        if task_id not in self.tasks:
            return {"success": False, "error": f"Tugas tidak ditemukan: {task_id}"}
        task = self.tasks.pop(task_id)
        self._save_tasks()
        return {"success": True, "message": f"Tugas '{task.name}' dihapus"}

    def pause_task(self, task_id: str) -> dict:
        if task_id not in self.tasks:
            return {"success": False, "error": f"Tugas tidak ditemukan: {task_id}"}
        self.tasks[task_id].enabled = False
        self.tasks[task_id].status = TaskStatus.PAUSED
        self._save_tasks()
        return {"success": True, "message": f"Tugas '{self.tasks[task_id].name}' dijeda"}

    def resume_task(self, task_id: str) -> dict:
        if task_id not in self.tasks:
            return {"success": False, "error": f"Tugas tidak ditemukan: {task_id}"}
        task = self.tasks[task_id]
        task.enabled = True
        task.status = TaskStatus.ACTIVE
        if task.task_type == TaskType.INTERVAL:
            task.next_run = time.time() + task.interval
        elif task.task_type == TaskType.CRON and task.cron_fields:
            task.next_run = CronParser.next_run(task.cron_fields).timestamp()
        self._save_tasks()
        return {"success": True, "message": f"Tugas '{task.name}' dilanjutkan"}

    def get_task_status(self, task_id: str) -> dict:
        if task_id not in self.tasks:
            return {"success": False, "error": f"Tugas tidak ditemukan: {task_id}"}
        return {"success": True, "task": self.tasks[task_id].to_dict()}

    def get_task_history(self, task_id: str) -> dict:
        if task_id not in self.tasks:
            return {"success": False, "error": f"Tugas tidak ditemukan: {task_id}"}
        task = self.tasks[task_id]
        return {"success": True, "task_id": task_id, "name": task.name, "history": task.history}

    def list_tasks(self) -> list[dict]:
        return [task.to_dict() for task in self.tasks.values()]

    def get_stats(self) -> dict:
        active = sum(1 for t in self.tasks.values() if t.status == TaskStatus.ACTIVE)
        paused = sum(1 for t in self.tasks.values() if t.status == TaskStatus.PAUSED)
        completed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.COMPLETED)
        total_runs = sum(t.run_count for t in self.tasks.values())
        total_errors = sum(t.error_count for t in self.tasks.values())

        by_type = {}
        for t in self.tasks.values():
            by_type[t.task_type.value] = by_type.get(t.task_type.value, 0) + 1

        return {
            "total_tasks": len(self.tasks),
            "active": active,
            "paused": paused,
            "completed": completed,
            "total_runs": total_runs,
            "total_errors": total_errors,
            "by_type": by_type,
            "scheduler_running": self._running,
            "registered_callbacks": list(self._callbacks.keys()),
        }

    async def start_scheduler(self):
        if self._running:
            return
        self._running = True
        logger.info("Scheduler dimulai")
        while self._running:
            now = time.time()
            for task in list(self.tasks.values()):
                if task.should_run(now):
                    await self._run_task(task)
            await asyncio.sleep(1)

    async def _run_task(self, task: ScheduledTask):
        callback = self._callbacks.get(task.callback_name)
        start_time = time.time()

        if not callback:
            task.record_execution(False, error=f"Callback '{task.callback_name}' tidak ditemukan")
            logger.warning(f"Callback tidak ditemukan untuk tugas '{task.name}': {task.callback_name}")
            if task.notify_on_error:
                await self._notify(
                    f"Tugas Gagal: {task.name}",
                    f"Callback '{task.callback_name}' tidak terdaftar.",
                    "error"
                )
            self._save_tasks()
            return

        try:
            if asyncio.iscoroutinefunction(callback):
                result = await callback()
            else:
                result = callback()
            result_str = str(result) if result else "OK"
            duration_ms = int((time.time() - start_time) * 1000)
            task.record_execution(True, result=result_str, duration_ms=duration_ms)
            logger.info(f"Tugas '{task.name}' berhasil dijalankan ({duration_ms}ms)")

            if task.notify_on_complete:
                await self._notify(
                    f"Tugas Selesai: {task.name}",
                    f"Eksekusi ke-{task.run_count} selesai. Hasil: {result_str[:100]}",
                    "success"
                )
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            task.record_execution(False, error=str(e), duration_ms=duration_ms)
            logger.error(f"Error menjalankan tugas '{task.name}': {e}")

            if task.notify_on_error:
                await self._notify(
                    f"Tugas Error: {task.name}",
                    f"Error pada eksekusi ke-{task.run_count}: {str(e)[:200]}",
                    "error"
                )

        self._save_tasks()

    def start_scheduler_background(self):
        if self._scheduler_task is None or self._scheduler_task.done():
            loop = asyncio.get_event_loop()
            self._scheduler_task = loop.create_task(self.start_scheduler())
            logger.info("Scheduler dimulai di background")

    def stop_scheduler(self):
        self._running = False
        if self._scheduler_task and not self._scheduler_task.done():
            self._scheduler_task.cancel()
        logger.info("Scheduler dihentikan")

    def _save_tasks(self):
        try:
            os.makedirs(os.path.dirname(self.persist_path), exist_ok=True)
            data = {
                "counter": self._task_counter,
                "tasks": {}
            }
            for tid, task in self.tasks.items():
                task_data = task.to_dict()
                task_data["history"] = task.history
                data["tasks"][tid] = task_data
            with open(self.persist_path, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Gagal menyimpan tugas: {e}")

    def _load_tasks(self):
        if not os.path.exists(self.persist_path):
            return
        try:
            with open(self.persist_path, "r") as f:
                data = json.load(f)
            self._task_counter = data.get("counter", 0)
            for tid, task_data in data.get("tasks", {}).items():
                task_data["task_id"] = tid
                self.tasks[tid] = ScheduledTask.from_dict(task_data)
            logger.info(f"Dimuat {len(self.tasks)} tugas terjadwal dari penyimpanan")
        except Exception as e:
            logger.error(f"Gagal memuat tugas: {e}")
