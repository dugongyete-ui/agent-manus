"""Meta-Learner - Modul meta-learning untuk agen belajar bagaimana belajar."""

import json
import logging
import os
import time
import math
from typing import Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class ExecutionPattern:
    def __init__(self, pattern_id: str, task_type: str, tool_sequence: list[str],
                 success: bool, duration_ms: int, feedback_score: float = 0):
        self.pattern_id = pattern_id
        self.task_type = task_type
        self.tool_sequence = tool_sequence
        self.success = success
        self.duration_ms = duration_ms
        self.feedback_score = feedback_score
        self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            "pattern_id": self.pattern_id,
            "task_type": self.task_type,
            "tool_sequence": self.tool_sequence,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "feedback_score": self.feedback_score,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionPattern":
        p = cls(
            pattern_id=data["pattern_id"],
            task_type=data.get("task_type", "general"),
            tool_sequence=data.get("tool_sequence", []),
            success=data.get("success", False),
            duration_ms=data.get("duration_ms", 0),
            feedback_score=data.get("feedback_score", 0),
        )
        p.timestamp = data.get("timestamp", time.time())
        return p


class StrategyProfile:
    def __init__(self, task_type: str):
        self.task_type = task_type
        self.total_executions = 0
        self.successful_executions = 0
        self.avg_duration_ms = 0
        self.best_tool_sequences: list[dict] = []
        self.worst_tool_sequences: list[dict] = []
        self.preferred_tools: dict[str, float] = {}
        self.avg_iterations = 0
        self.last_updated = time.time()

    def to_dict(self) -> dict:
        return {
            "task_type": self.task_type,
            "total_executions": self.total_executions,
            "successful_executions": self.successful_executions,
            "success_rate": round(self.successful_executions / self.total_executions, 4) if self.total_executions > 0 else 0,
            "avg_duration_ms": round(self.avg_duration_ms),
            "best_tool_sequences": self.best_tool_sequences[:5],
            "worst_tool_sequences": self.worst_tool_sequences[:3],
            "preferred_tools": {k: round(v, 4) for k, v in sorted(self.preferred_tools.items(), key=lambda x: x[1], reverse=True)[:10]},
            "avg_iterations": round(self.avg_iterations, 2),
            "last_updated": self.last_updated,
        }


class PerformanceTracker:
    def __init__(self):
        self.metrics: dict[str, list[float]] = defaultdict(list)
        self.baselines: dict[str, float] = {}
        self.improvements: dict[str, float] = {}

    def record_metric(self, name: str, value: float):
        self.metrics[name].append(value)
        if len(self.metrics[name]) > 200:
            self.metrics[name] = self.metrics[name][-200:]

    def compute_baseline(self, name: str, window: int = 20) -> float:
        values = self.metrics.get(name, [])
        if len(values) < window:
            baseline = sum(values) / len(values) if values else 0
        else:
            baseline = sum(values[:window]) / window
        self.baselines[name] = baseline
        return baseline

    def compute_improvement(self, name: str, window: int = 20) -> float:
        values = self.metrics.get(name, [])
        baseline = self.baselines.get(name)
        if baseline is None:
            baseline = self.compute_baseline(name, window)

        if len(values) < window:
            recent = sum(values) / len(values) if values else 0
        else:
            recent = sum(values[-window:]) / window

        if baseline == 0:
            improvement = 0
        else:
            improvement = (recent - baseline) / abs(baseline)

        self.improvements[name] = improvement
        return improvement

    def to_dict(self) -> dict:
        result = {}
        for name in self.metrics:
            values = self.metrics[name]
            result[name] = {
                "current": round(values[-1], 4) if values else 0,
                "avg": round(sum(values) / len(values), 4) if values else 0,
                "min": round(min(values), 4) if values else 0,
                "max": round(max(values), 4) if values else 0,
                "count": len(values),
                "baseline": round(self.baselines.get(name, 0), 4),
                "improvement": round(self.improvements.get(name, 0), 4),
            }
        return result


class MetaLearner:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.patterns_file = os.path.join(data_dir, "meta_patterns.json")
        self.strategies_file = os.path.join(data_dir, "meta_strategies.json")
        self.execution_patterns: list[ExecutionPattern] = []
        self.strategy_profiles: dict[str, StrategyProfile] = {}
        self.performance = PerformanceTracker()
        self.task_type_classifier: dict[str, list[str]] = {
            "code": ["code", "program", "script", "function", "class", "debug", "error", "bug", "compile", "run"],
            "search": ["search", "find", "lookup", "query", "information", "what is", "how to", "explain"],
            "file": ["file", "read", "write", "create", "delete", "folder", "directory", "save", "open"],
            "web": ["website", "web", "page", "url", "browse", "navigate", "scrape", "download"],
            "media": ["image", "video", "audio", "generate", "create", "design", "picture", "photo"],
            "shell": ["command", "terminal", "shell", "install", "run", "execute", "bash", "pip", "npm"],
            "analysis": ["analyze", "analyze_file", "inspect", "review", "check", "examine", "report", "statistics"],
            "communication": ["message", "tell", "notify", "respond", "answer", "explain", "help"],
        }
        self.max_patterns = 500
        self._load_data()
        logger.info("Meta-Learner diinisialisasi")

    def _load_data(self):
        os.makedirs(self.data_dir, exist_ok=True)
        if os.path.exists(self.patterns_file):
            try:
                with open(self.patterns_file, "r") as f:
                    data = json.load(f)
                self.execution_patterns = [ExecutionPattern.from_dict(p) for p in data.get("patterns", [])]
                perf_data = data.get("performance", {})
                for name, values in perf_data.get("metrics", {}).items():
                    self.performance.metrics[name] = values
                self.performance.baselines = perf_data.get("baselines", {})
                logger.info(f"Meta-learning data dimuat: {len(self.execution_patterns)} patterns")
            except Exception as e:
                logger.warning(f"Gagal memuat meta-learning data: {e}")

        if os.path.exists(self.strategies_file):
            try:
                with open(self.strategies_file, "r") as f:
                    data = json.load(f)
                for name, sd in data.get("strategies", {}).items():
                    profile = StrategyProfile(name)
                    profile.total_executions = sd.get("total_executions", 0)
                    profile.successful_executions = sd.get("successful_executions", 0)
                    profile.avg_duration_ms = sd.get("avg_duration_ms", 0)
                    profile.best_tool_sequences = sd.get("best_tool_sequences", [])
                    profile.worst_tool_sequences = sd.get("worst_tool_sequences", [])
                    profile.preferred_tools = sd.get("preferred_tools", {})
                    profile.avg_iterations = sd.get("avg_iterations", 0)
                    self.strategy_profiles[name] = profile
            except Exception as e:
                logger.warning(f"Gagal memuat strategy data: {e}")

    def _save_data(self):
        os.makedirs(self.data_dir, exist_ok=True)
        patterns_data = {
            "patterns": [p.to_dict() for p in self.execution_patterns[-self.max_patterns:]],
            "performance": {
                "metrics": dict(self.performance.metrics),
                "baselines": self.performance.baselines,
            },
            "metadata": {"last_updated": time.time(), "total_patterns": len(self.execution_patterns)},
        }
        with open(self.patterns_file, "w") as f:
            json.dump(patterns_data, f, indent=2, ensure_ascii=False)

        strategies_data = {
            "strategies": {name: s.to_dict() for name, s in self.strategy_profiles.items()},
            "metadata": {"last_updated": time.time()},
        }
        with open(self.strategies_file, "w") as f:
            json.dump(strategies_data, f, indent=2, ensure_ascii=False)

    def classify_task(self, user_input: str) -> str:
        input_lower = user_input.lower()
        scores = {}
        for task_type, keywords in self.task_type_classifier.items():
            score = sum(1 for kw in keywords if kw in input_lower)
            if score > 0:
                scores[task_type] = score

        if not scores:
            return "general"
        return max(scores, key=scores.get)

    def record_execution(self, user_input: str, tool_sequence: list[str],
                         success: bool, duration_ms: int, iterations: int,
                         feedback_score: float = 0) -> dict:
        task_type = self.classify_task(user_input)
        pattern_id = f"pat_{int(time.time())}_{len(self.execution_patterns)}"

        pattern = ExecutionPattern(
            pattern_id=pattern_id,
            task_type=task_type,
            tool_sequence=tool_sequence,
            success=success,
            duration_ms=duration_ms,
            feedback_score=feedback_score,
        )
        self.execution_patterns.append(pattern)

        if len(self.execution_patterns) > self.max_patterns:
            self.execution_patterns = self.execution_patterns[-self.max_patterns:]

        self._update_strategy(task_type, pattern, iterations)

        self.performance.record_metric("success_rate", 1.0 if success else 0.0)
        self.performance.record_metric("duration_ms", duration_ms)
        self.performance.record_metric("iterations", iterations)
        self.performance.record_metric(f"{task_type}_success", 1.0 if success else 0.0)

        self._save_data()
        logger.info(f"Execution pattern direkam: {pattern_id} (type={task_type}, success={success})")

        return {
            "pattern_id": pattern_id,
            "task_type": task_type,
            "success": success,
            "strategy_updated": True,
        }

    def _update_strategy(self, task_type: str, pattern: ExecutionPattern, iterations: int):
        if task_type not in self.strategy_profiles:
            self.strategy_profiles[task_type] = StrategyProfile(task_type)

        profile = self.strategy_profiles[task_type]
        profile.total_executions += 1

        if pattern.success:
            profile.successful_executions += 1

        alpha = 0.2
        profile.avg_duration_ms = (1 - alpha) * profile.avg_duration_ms + alpha * pattern.duration_ms
        profile.avg_iterations = (1 - alpha) * profile.avg_iterations + alpha * iterations

        seq_key = " -> ".join(pattern.tool_sequence) if pattern.tool_sequence else "direct"
        seq_entry = {
            "sequence": pattern.tool_sequence,
            "key": seq_key,
            "success": pattern.success,
            "duration_ms": pattern.duration_ms,
            "score": pattern.feedback_score,
        }

        if pattern.success:
            existing = next((s for s in profile.best_tool_sequences if s["key"] == seq_key), None)
            if existing:
                existing["score"] = (existing.get("score", 0) + pattern.feedback_score) / 2
            else:
                profile.best_tool_sequences.append(seq_entry)
            profile.best_tool_sequences.sort(key=lambda x: x.get("score", 0), reverse=True)
            profile.best_tool_sequences = profile.best_tool_sequences[:10]
        else:
            profile.worst_tool_sequences.append(seq_entry)
            profile.worst_tool_sequences = profile.worst_tool_sequences[-5:]

        for tool in pattern.tool_sequence:
            if tool not in profile.preferred_tools:
                profile.preferred_tools[tool] = 0.0
            reward = 0.3 if pattern.success else -0.1
            profile.preferred_tools[tool] = (1 - alpha) * profile.preferred_tools[tool] + alpha * reward

        profile.last_updated = time.time()

    def get_strategy_for_task(self, user_input: str) -> dict:
        task_type = self.classify_task(user_input)
        profile = self.strategy_profiles.get(task_type)

        if not profile or profile.total_executions < 3:
            return {
                "task_type": task_type,
                "has_strategy": False,
                "suggestion": "Belum cukup data untuk strategi optimal. Gunakan pendekatan default.",
                "recommended_tools": [],
                "estimated_iterations": 3,
            }

        recommended_tools = sorted(
            profile.preferred_tools.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:5]

        best_seq = profile.best_tool_sequences[0] if profile.best_tool_sequences else None

        return {
            "task_type": task_type,
            "has_strategy": True,
            "success_rate": round(profile.successful_executions / profile.total_executions, 4),
            "avg_duration_ms": round(profile.avg_duration_ms),
            "recommended_tools": [{"tool": t, "score": round(s, 4)} for t, s in recommended_tools],
            "best_sequence": best_seq.get("sequence", []) if best_seq else [],
            "estimated_iterations": round(profile.avg_iterations),
            "total_experience": profile.total_executions,
            "suggestion": self._generate_strategy_suggestion(profile),
        }

    def _generate_strategy_suggestion(self, profile: StrategyProfile) -> str:
        rate = profile.successful_executions / profile.total_executions if profile.total_executions > 0 else 0

        if rate > 0.8:
            return f"Strategi untuk '{profile.task_type}' sangat efektif (success rate: {rate:.0%}). Ikuti pola yang sama."
        elif rate > 0.5:
            if profile.best_tool_sequences:
                best = profile.best_tool_sequences[0]
                return f"Coba gunakan urutan tool: {' -> '.join(best.get('sequence', []))} untuk hasil lebih baik."
            return f"Strategi cukup efektif ({rate:.0%}). Evaluasi tool yang kurang optimal."
        else:
            avoid = [t for t, s in profile.preferred_tools.items() if s < 0][:3]
            if avoid:
                return f"Performa rendah ({rate:.0%}). Hindari: {', '.join(avoid)}. Coba pendekatan berbeda."
            return f"Performa rendah ({rate:.0%}). Pertimbangkan pendekatan alternatif."

    def get_performance_report(self) -> dict:
        for metric in self.performance.metrics:
            self.performance.compute_improvement(metric)

        return {
            "metrics": self.performance.to_dict(),
            "strategy_profiles": {name: s.to_dict() for name, s in self.strategy_profiles.items()},
            "total_patterns": len(self.execution_patterns),
            "task_type_distribution": self._get_task_distribution(),
            "overall_improvement": self._compute_overall_improvement(),
        }

    def _get_task_distribution(self) -> dict:
        distribution = defaultdict(int)
        for p in self.execution_patterns:
            distribution[p.task_type] += 1
        total = len(self.execution_patterns)
        return {
            k: {"count": v, "percentage": round(v / total * 100, 1) if total > 0 else 0}
            for k, v in sorted(distribution.items(), key=lambda x: x[1], reverse=True)
        }

    def _compute_overall_improvement(self) -> dict:
        success_imp = self.performance.improvements.get("success_rate", 0)
        duration_imp = self.performance.improvements.get("duration_ms", 0)
        iterations_imp = self.performance.improvements.get("iterations", 0)

        overall = (success_imp * 0.5) + (-duration_imp * 0.3) + (-iterations_imp * 0.2)

        if overall > 0.1:
            trend = "improving"
        elif overall < -0.1:
            trend = "declining"
        else:
            trend = "stable"

        return {
            "overall_score": round(overall, 4),
            "trend": trend,
            "success_improvement": round(success_imp, 4),
            "speed_improvement": round(-duration_imp, 4),
            "efficiency_improvement": round(-iterations_imp, 4),
        }

    def get_learning_summary(self) -> dict:
        total_patterns = len(self.execution_patterns)
        if total_patterns == 0:
            return {
                "status": "initializing",
                "message": "Meta-learner belum memiliki data. Mulai gunakan agen untuk mengumpulkan pola.",
                "patterns_count": 0,
                "strategies_count": 0,
            }

        success_patterns = sum(1 for p in self.execution_patterns if p.success)

        return {
            "status": "active",
            "patterns_count": total_patterns,
            "strategies_count": len(self.strategy_profiles),
            "overall_success_rate": round(success_patterns / total_patterns, 4),
            "task_types_learned": list(self.strategy_profiles.keys()),
            "performance": self.get_performance_report(),
        }
