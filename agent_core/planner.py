"""Planner - Modul untuk membuat dan memperbarui rencana tugas."""

import logging
import time
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Task:
    def __init__(self, task_id: str, description: str, priority: int = 5):
        self.task_id = task_id
        self.description = description
        self.priority = priority
        self.status = TaskStatus.PENDING
        self.subtasks: list["Task"] = []
        self.result: Optional[str] = None
        self.created_at = time.time()
        self.updated_at = time.time()
        self.metadata: dict = {}

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "priority": self.priority,
            "status": self.status.value,
            "subtasks": [st.to_dict() for st in self.subtasks],
            "result": self.result,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class Planner:
    def __init__(self):
        self.tasks: list[Task] = []
        self._task_counter = 0

    def create_plan(self, goal: str, steps: list[str]) -> list[Task]:
        self.tasks.clear()
        self._task_counter = 0
        for step in steps:
            self._task_counter += 1
            task = Task(
                task_id=f"task_{self._task_counter}",
                description=step,
                priority=self._task_counter,
            )
            self.tasks.append(task)
        logger.info(f"Rencana dibuat untuk '{goal}' dengan {len(steps)} langkah.")
        return self.tasks

    def add_task(self, description: str, priority: int = 5) -> Task:
        self._task_counter += 1
        task = Task(
            task_id=f"task_{self._task_counter}",
            description=description,
            priority=priority,
        )
        self.tasks.append(task)
        self.tasks.sort(key=lambda t: t.priority)
        logger.info(f"Tugas ditambahkan: {description}")
        return task

    def add_subtask(self, parent_id: str, description: str) -> Optional[Task]:
        parent = self.get_task(parent_id)
        if not parent:
            logger.warning(f"Tugas induk '{parent_id}' tidak ditemukan.")
            return None
        self._task_counter += 1
        subtask = Task(
            task_id=f"task_{self._task_counter}",
            description=description,
        )
        parent.subtasks.append(subtask)
        return subtask

    def get_task(self, task_id: str) -> Optional[Task]:
        for task in self.tasks:
            if task.task_id == task_id:
                return task
            for sub in task.subtasks:
                if sub.task_id == task_id:
                    return sub
        return None

    def update_task_status(self, task_id: str, status: TaskStatus, result: Optional[str] = None):
        task = self.get_task(task_id)
        if task:
            task.status = status
            task.result = result
            task.updated_at = time.time()
            logger.info(f"Tugas '{task_id}' diperbarui ke {status.value}")

    def get_next_task(self) -> Optional[Task]:
        for task in self.tasks:
            if task.status == TaskStatus.PENDING:
                return task
            for sub in task.subtasks:
                if sub.status == TaskStatus.PENDING:
                    return sub
        return None

    def get_progress(self) -> dict:
        total = 0
        completed = 0
        for task in self.tasks:
            total += 1
            if task.status == TaskStatus.COMPLETED:
                completed += 1
            for sub in task.subtasks:
                total += 1
                if sub.status == TaskStatus.COMPLETED:
                    completed += 1
        return {
            "total": total,
            "completed": completed,
            "percentage": (completed / total * 100) if total > 0 else 0,
        }

    def get_plan_summary(self) -> str:
        lines = ["=== Rencana Tugas ==="]
        for task in self.tasks:
            status_icon = {"pending": "⏳", "in_progress": "🔄", "completed": "✅", "failed": "❌", "cancelled": "🚫"}
            icon = status_icon.get(task.status.value, "❓")
            lines.append(f"  {icon} [{task.task_id}] {task.description} ({task.status.value})")
            for sub in task.subtasks:
                sub_icon = status_icon.get(sub.status.value, "❓")
                lines.append(f"    {sub_icon} [{sub.task_id}] {sub.description} ({sub.status.value})")
        progress = self.get_progress()
        lines.append(f"\nProgres: {progress['completed']}/{progress['total']} ({progress['percentage']:.0f}%)")
        return "\n".join(lines)
