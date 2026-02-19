"""Playbook Manager - Definisi, penyimpanan, dan eksekusi urutan aksi alat."""

import json
import logging
import os
import time
import uuid
from typing import Optional, Callable, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PlaybookStep:
    tool: str
    action: str
    params: dict = field(default_factory=dict)
    description: str = ""
    condition: Optional[str] = None
    on_error: str = "stop"
    timeout: int = 120
    retry_count: int = 0

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "action": self.action,
            "params": self.params,
            "description": self.description,
            "condition": self.condition,
            "on_error": self.on_error,
            "timeout": self.timeout,
            "retry_count": self.retry_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PlaybookStep":
        return cls(
            tool=data.get("tool", ""),
            action=data.get("action", ""),
            params=data.get("params", {}),
            description=data.get("description", ""),
            condition=data.get("condition"),
            on_error=data.get("on_error", "stop"),
            timeout=data.get("timeout", 120),
            retry_count=data.get("retry_count", 0),
        )


@dataclass
class PlaybookExecution:
    execution_id: str
    playbook_id: str
    started_at: float
    completed_at: Optional[float] = None
    status: str = "running"
    step_results: list = field(default_factory=list)
    total_duration: float = 0.0
    error: Optional[str] = None
    context: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "execution_id": self.execution_id,
            "playbook_id": self.playbook_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "step_results": self.step_results,
            "total_duration": round(self.total_duration, 3),
            "error": self.error,
        }


class Playbook:
    def __init__(self, playbook_id: str, name: str, description: str = "",
                 category: str = "general", tags: Optional[list] = None):
        self.playbook_id = playbook_id
        self.name = name
        self.description = description
        self.category = category
        self.tags = tags or []
        self.steps: list[PlaybookStep] = []
        self.variables: dict[str, str] = {}
        self.created_at = time.time()
        self.updated_at = time.time()
        self.execution_count = 0
        self.success_count = 0
        self.avg_duration: float = 0.0
        self.author = "agent"
        self.version = "1.0.0"
        self.enabled = True

    def add_step(self, tool: str, action: str, params: dict = None,
                 description: str = "", on_error: str = "stop") -> PlaybookStep:
        step = PlaybookStep(
            tool=tool,
            action=action,
            params=params or {},
            description=description,
            on_error=on_error,
        )
        self.steps.append(step)
        self.updated_at = time.time()
        return step

    def remove_step(self, index: int) -> bool:
        if 0 <= index < len(self.steps):
            self.steps.pop(index)
            self.updated_at = time.time()
            return True
        return False

    def reorder_steps(self, new_order: list[int]) -> bool:
        if sorted(new_order) != list(range(len(self.steps))):
            return False
        self.steps = [self.steps[i] for i in new_order]
        self.updated_at = time.time()
        return True

    def record_execution(self, success: bool, duration: float):
        self.execution_count += 1
        if success:
            self.success_count += 1
        total_time = self.avg_duration * (self.execution_count - 1) + duration
        self.avg_duration = total_time / self.execution_count

    @property
    def success_rate(self) -> float:
        if self.execution_count == 0:
            return 0.0
        return round(self.success_count / self.execution_count * 100, 1)

    def to_dict(self) -> dict:
        return {
            "playbook_id": self.playbook_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "tags": self.tags,
            "steps": [s.to_dict() for s in self.steps],
            "variables": self.variables,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "execution_count": self.execution_count,
            "success_count": self.success_count,
            "success_rate": self.success_rate,
            "avg_duration": round(self.avg_duration, 3),
            "author": self.author,
            "version": self.version,
            "enabled": self.enabled,
            "step_count": len(self.steps),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Playbook":
        pb = cls(
            playbook_id=data.get("playbook_id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            category=data.get("category", "general"),
            tags=data.get("tags", []),
        )
        pb.variables = data.get("variables", {})
        pb.created_at = data.get("created_at", time.time())
        pb.updated_at = data.get("updated_at", time.time())
        pb.execution_count = data.get("execution_count", 0)
        pb.success_count = data.get("success_count", 0)
        pb.avg_duration = data.get("avg_duration", 0.0)
        pb.author = data.get("author", "agent")
        pb.version = data.get("version", "1.0.0")
        pb.enabled = data.get("enabled", True)
        pb.steps = [PlaybookStep.from_dict(s) for s in data.get("steps", [])]
        return pb


class PlaybookManager:
    def __init__(self, storage_dir: str = "data/playbooks", tool_executor: Optional[Callable] = None):
        self.storage_dir = storage_dir
        self.tool_executor = tool_executor
        self.playbooks: dict[str, Playbook] = {}
        self.execution_history: list[PlaybookExecution] = []
        self._pattern_buffer: list[dict] = []
        self._max_pattern_buffer = 200
        os.makedirs(storage_dir, exist_ok=True)
        self._load_playbooks()

    def _load_playbooks(self):
        pb_file = os.path.join(self.storage_dir, "playbooks.json")
        if os.path.exists(pb_file):
            try:
                with open(pb_file, "r") as f:
                    data = json.load(f)
                for pb_data in data.get("playbooks", []):
                    pb = Playbook.from_dict(pb_data)
                    self.playbooks[pb.playbook_id] = pb
                logger.info(f"Loaded {len(self.playbooks)} playbooks")
            except Exception as e:
                logger.error(f"Error loading playbooks: {e}")

    def _save_playbooks(self):
        pb_file = os.path.join(self.storage_dir, "playbooks.json")
        try:
            data = {"playbooks": [pb.to_dict() for pb in self.playbooks.values()]}
            with open(pb_file, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving playbooks: {e}")

    def create_playbook(self, name: str, description: str = "",
                        category: str = "general", tags: Optional[list] = None,
                        steps: Optional[list[dict]] = None,
                        variables: Optional[dict] = None) -> dict:
        playbook_id = f"pb_{uuid.uuid4().hex[:8]}"
        pb = Playbook(
            playbook_id=playbook_id,
            name=name,
            description=description,
            category=category,
            tags=tags,
        )

        if variables:
            pb.variables = variables

        if steps:
            for step_data in steps:
                pb.add_step(
                    tool=step_data.get("tool", ""),
                    action=step_data.get("action", ""),
                    params=step_data.get("params", {}),
                    description=step_data.get("description", ""),
                    on_error=step_data.get("on_error", "stop"),
                )

        self.playbooks[playbook_id] = pb
        self._save_playbooks()
        logger.info(f"Playbook dibuat: {name} ({playbook_id})")

        return {"success": True, "playbook": pb.to_dict()}

    def update_playbook(self, playbook_id: str, updates: dict) -> dict:
        pb = self.playbooks.get(playbook_id)
        if not pb:
            return {"success": False, "error": f"Playbook tidak ditemukan: {playbook_id}"}

        for key in ["name", "description", "category", "tags", "variables", "enabled", "version"]:
            if key in updates:
                setattr(pb, key, updates[key])

        if "steps" in updates:
            pb.steps = [PlaybookStep.from_dict(s) for s in updates["steps"]]

        pb.updated_at = time.time()
        self._save_playbooks()
        return {"success": True, "playbook": pb.to_dict()}

    def delete_playbook(self, playbook_id: str) -> dict:
        if playbook_id not in self.playbooks:
            return {"success": False, "error": f"Playbook tidak ditemukan: {playbook_id}"}
        name = self.playbooks[playbook_id].name
        del self.playbooks[playbook_id]
        self._save_playbooks()
        return {"success": True, "message": f"Playbook '{name}' dihapus"}

    def get_playbook(self, playbook_id: str) -> Optional[dict]:
        pb = self.playbooks.get(playbook_id)
        return pb.to_dict() if pb else None

    def list_playbooks(self, category: Optional[str] = None,
                       tag: Optional[str] = None,
                       enabled_only: bool = False) -> list[dict]:
        pbs = list(self.playbooks.values())
        if category:
            pbs = [pb for pb in pbs if pb.category == category]
        if tag:
            pbs = [pb for pb in pbs if tag in pb.tags]
        if enabled_only:
            pbs = [pb for pb in pbs if pb.enabled]
        return [pb.to_dict() for pb in pbs]

    async def execute_playbook(self, playbook_id: str, variables: Optional[dict] = None,
                               dry_run: bool = False) -> dict:
        pb = self.playbooks.get(playbook_id)
        if not pb:
            return {"success": False, "error": f"Playbook tidak ditemukan: {playbook_id}"}

        if not pb.enabled:
            return {"success": False, "error": "Playbook dinonaktifkan"}

        if not pb.steps:
            return {"success": False, "error": "Playbook tidak memiliki langkah"}

        exec_id = f"exec_{uuid.uuid4().hex[:8]}"
        execution = PlaybookExecution(
            execution_id=exec_id,
            playbook_id=playbook_id,
            started_at=time.time(),
        )

        merged_vars = {**pb.variables}
        if variables:
            merged_vars.update(variables)

        execution.context = merged_vars

        if dry_run:
            preview_steps = []
            for i, step in enumerate(pb.steps):
                resolved_params = self._resolve_variables(step.params, merged_vars)
                preview_steps.append({
                    "step": i + 1,
                    "tool": step.tool,
                    "action": step.action,
                    "params": resolved_params,
                    "description": step.description,
                })
            return {
                "success": True,
                "dry_run": True,
                "playbook": pb.name,
                "steps": preview_steps,
                "variables": merged_vars,
            }

        all_success = True
        for i, step in enumerate(pb.steps):
            step_start = time.time()
            resolved_params = self._resolve_variables(step.params, merged_vars)

            step_result = {
                "step": i + 1,
                "tool": step.tool,
                "action": step.action,
                "description": step.description,
                "status": "running",
                "started_at": step_start,
            }

            try:
                if self.tool_executor:
                    result = await self.tool_executor(step.tool, {
                        "action": step.action,
                        **resolved_params,
                    })
                    step_result["result"] = str(result)[:3000] if result else ""
                    step_result["status"] = "success"
                else:
                    step_result["result"] = "No tool executor configured (simulation mode)"
                    step_result["status"] = "simulated"

            except Exception as e:
                step_result["status"] = "error"
                step_result["error"] = str(e)
                all_success = False

                if step.on_error == "stop":
                    execution.error = f"Step {i + 1} failed: {str(e)}"
                    step_result["duration"] = round(time.time() - step_start, 3)
                    execution.step_results.append(step_result)
                    break
                elif step.on_error == "skip":
                    pass

            step_result["duration"] = round(time.time() - step_start, 3)
            execution.step_results.append(step_result)

            if step_result.get("result"):
                merged_vars[f"step_{i+1}_result"] = step_result["result"][:1000]

        execution.completed_at = time.time()
        execution.total_duration = execution.completed_at - execution.started_at
        execution.status = "success" if all_success else "failed"

        pb.record_execution(all_success, execution.total_duration)
        self.execution_history.append(execution)
        if len(self.execution_history) > 100:
            self.execution_history = self.execution_history[-100:]

        self._save_playbooks()

        return {
            "success": all_success,
            "execution": execution.to_dict(),
        }

    def _resolve_variables(self, params: dict, variables: dict) -> dict:
        resolved = {}
        for key, val in params.items():
            if isinstance(val, str):
                for var_name, var_val in variables.items():
                    val = val.replace(f"${{{var_name}}}", str(var_val))
                    val = val.replace(f"${var_name}", str(var_val))
                resolved[key] = val
            elif isinstance(val, dict):
                resolved[key] = self._resolve_variables(val, variables)
            else:
                resolved[key] = val
        return resolved

    def record_tool_execution(self, tool_name: str, params: dict, result: str,
                              success: bool, duration: float):
        self._pattern_buffer.append({
            "tool": tool_name,
            "params": params,
            "result": result[:500],
            "success": success,
            "duration": duration,
            "timestamp": time.time(),
        })
        if len(self._pattern_buffer) > self._max_pattern_buffer:
            self._pattern_buffer = self._pattern_buffer[-self._max_pattern_buffer:]

    def detect_patterns(self, min_occurrences: int = 3, min_sequence_length: int = 2) -> list[dict]:
        if len(self._pattern_buffer) < min_sequence_length * min_occurrences:
            return []

        sequences: dict[str, dict] = {}
        successful = [e for e in self._pattern_buffer if e["success"]]

        for seq_len in range(min_sequence_length, min(6, len(successful) + 1)):
            for i in range(len(successful) - seq_len + 1):
                seq = successful[i:i + seq_len]
                key = "|".join(f"{s['tool']}:{sorted(s['params'].keys())}" for s in seq)

                if key not in sequences:
                    sequences[key] = {
                        "pattern": key,
                        "steps": [{
                            "tool": s["tool"],
                            "params": s["params"],
                        } for s in seq],
                        "count": 0,
                        "avg_duration": 0.0,
                        "total_duration": 0.0,
                    }
                sequences[key]["count"] += 1
                total_dur = sum(s["duration"] for s in seq)
                sequences[key]["total_duration"] += total_dur
                sequences[key]["avg_duration"] = sequences[key]["total_duration"] / sequences[key]["count"]

        patterns = [
            {
                "pattern": v["pattern"],
                "steps": v["steps"],
                "occurrences": v["count"],
                "avg_duration": round(v["avg_duration"], 3),
                "suggested_name": f"auto_{v['steps'][0]['tool']}_{len(v['steps'])}steps",
            }
            for v in sequences.values()
            if v["count"] >= min_occurrences
        ]

        patterns.sort(key=lambda p: p["occurrences"], reverse=True)
        return patterns[:10]

    def create_from_pattern(self, pattern: dict, name: Optional[str] = None) -> dict:
        pb_name = name or pattern.get("suggested_name", f"auto_playbook_{int(time.time())}")
        steps = [
            {
                "tool": s["tool"],
                "action": list(s["params"].values())[0] if s["params"] else "execute",
                "params": s["params"],
                "description": f"Step from detected pattern (tool: {s['tool']})",
            }
            for s in pattern.get("steps", [])
        ]

        return self.create_playbook(
            name=pb_name,
            description=f"Otomatis dibuat dari pola yang terdeteksi ({pattern.get('occurrences', 0)} kemunculan)",
            category="auto_generated",
            tags=["auto", "pattern"],
            steps=steps,
        )

    def get_execution_history(self, playbook_id: Optional[str] = None, limit: int = 20) -> list[dict]:
        history = self.execution_history
        if playbook_id:
            history = [e for e in history if e.playbook_id == playbook_id]
        return [e.to_dict() for e in history[-limit:]]

    def get_stats(self) -> dict:
        total = len(self.playbooks)
        enabled = sum(1 for pb in self.playbooks.values() if pb.enabled)
        categories = {}
        for pb in self.playbooks.values():
            categories[pb.category] = categories.get(pb.category, 0) + 1

        total_execs = sum(pb.execution_count for pb in self.playbooks.values())
        total_success = sum(pb.success_count for pb in self.playbooks.values())

        return {
            "total_playbooks": total,
            "enabled": enabled,
            "disabled": total - enabled,
            "categories": categories,
            "total_executions": total_execs,
            "total_successes": total_success,
            "overall_success_rate": round(total_success / total_execs * 100, 1) if total_execs > 0 else 0,
            "pattern_buffer_size": len(self._pattern_buffer),
        }

    async def execute(self, plan: dict) -> str:
        action = plan.get("action", plan.get("intent", ""))
        params = plan.get("params", plan)

        if action == "create":
            result = self.create_playbook(**{k: v for k, v in params.items() if k in ["name", "description", "category", "tags", "steps", "variables"]})
        elif action == "list":
            result = {"playbooks": self.list_playbooks(category=params.get("category"), enabled_only=params.get("enabled_only", False))}
        elif action == "execute":
            result = await self.execute_playbook(params.get("playbook_id", ""), variables=params.get("variables"), dry_run=params.get("dry_run", False))
        elif action == "delete":
            result = self.delete_playbook(params.get("playbook_id", ""))
        elif action == "detect_patterns":
            result = {"patterns": self.detect_patterns()}
        elif action == "stats":
            result = self.get_stats()
        elif action == "history":
            result = {"history": self.get_execution_history(params.get("playbook_id"), limit=params.get("limit", 20))}
        else:
            result = {"message": f"Playbook manager siap. Aksi: create, list, execute, delete, detect_patterns, stats, history"}

        return json.dumps(result, ensure_ascii=False, default=str)
