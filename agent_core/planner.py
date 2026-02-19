"""Planner - Modul untuk membuat dan memperbarui rencana tugas dengan optimasi meta-learning."""

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
        self.tools_used: list[str] = []
        self.duration_ms: int = 0

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
            "tools_used": self.tools_used,
            "duration_ms": self.duration_ms,
        }


class Planner:
    def __init__(self, meta_learner=None):
        self.tasks: list[Task] = []
        self._task_counter = 0
        self.meta_learner = meta_learner

    def set_meta_learner(self, meta_learner):
        self.meta_learner = meta_learner

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

    def create_optimized_plan(self, goal: str, steps: list[str]) -> dict:
        tasks = self.create_plan(goal, steps)
        strategy = None
        if self.meta_learner:
            strategy = self.meta_learner.get_strategy_for_task(goal)
            if strategy.get("has_strategy"):
                for task in tasks:
                    task.metadata["strategy"] = strategy
                logger.info(f"Strategi meta-learning diterapkan: {strategy.get('task_type')}")

        return {
            "tasks": [t.to_dict() for t in tasks],
            "strategy": strategy,
            "optimized": strategy is not None and strategy.get("has_strategy", False),
        }

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
            if status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                task.duration_ms = int((task.updated_at - task.created_at) * 1000)
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
        failed = 0
        for task in self.tasks:
            total += 1
            if task.status == TaskStatus.COMPLETED:
                completed += 1
            elif task.status == TaskStatus.FAILED:
                failed += 1
            for sub in task.subtasks:
                total += 1
                if sub.status == TaskStatus.COMPLETED:
                    completed += 1
                elif sub.status == TaskStatus.FAILED:
                    failed += 1
        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "percentage": (completed / total * 100) if total > 0 else 0,
        }

    def get_execution_stats(self) -> dict:
        all_tools = []
        total_duration = 0
        for task in self.tasks:
            all_tools.extend(task.tools_used)
            total_duration += task.duration_ms
            for sub in task.subtasks:
                all_tools.extend(sub.tools_used)
                total_duration += sub.duration_ms

        tool_counts = {}
        for tool in all_tools:
            tool_counts[tool] = tool_counts.get(tool, 0) + 1

        progress = self.get_progress()
        return {
            **progress,
            "tools_used": tool_counts,
            "total_duration_ms": total_duration,
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
