"""RLHF Engine - Reinforcement Learning from Human Feedback untuk Manus Agent."""

import json
import logging
import os
import time
import math
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class FeedbackType(Enum):
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    RATING = "rating"
    CORRECTION = "correction"
    PREFERENCE = "preference"


class FeedbackEntry:
    def __init__(self, feedback_id: str, session_id: str, message_id: str,
                 feedback_type: FeedbackType, value: float, context: dict = None,
                 comment: str = ""):
        self.feedback_id = feedback_id
        self.session_id = session_id
        self.message_id = message_id
        self.feedback_type = feedback_type
        self.value = value
        self.context = context or {}
        self.comment = comment
        self.created_at = time.time()

    def to_dict(self) -> dict:
        return {
            "feedback_id": self.feedback_id,
            "session_id": self.session_id,
            "message_id": self.message_id,
            "feedback_type": self.feedback_type.value,
            "value": self.value,
            "context": self.context,
            "comment": self.comment,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FeedbackEntry":
        entry = cls(
            feedback_id=data["feedback_id"],
            session_id=data.get("session_id", ""),
            message_id=data.get("message_id", ""),
            feedback_type=FeedbackType(data.get("feedback_type", "rating")),
            value=data.get("value", 0),
            context=data.get("context", {}),
            comment=data.get("comment", ""),
        )
        entry.created_at = data.get("created_at", time.time())
        return entry


class RewardSignal:
    def __init__(self, tool_name: str, action_context: str, reward: float,
                 timestamp: float = None):
        self.tool_name = tool_name
        self.action_context = action_context
        self.reward = reward
        self.timestamp = timestamp or time.time()

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "action_context": self.action_context,
            "reward": self.reward,
            "timestamp": self.timestamp,
        }


class ToolPolicy:
    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        self.total_reward = 0.0
        self.usage_count = 0
        self.success_count = 0
        self.fail_count = 0
        self.avg_reward = 0.0
        self.confidence = 0.0
        self.context_rewards: dict[str, float] = {}

    def update(self, reward: float, context: str = "general"):
        self.usage_count += 1
        self.total_reward += reward
        if reward > 0:
            self.success_count += 1
        elif reward < 0:
            self.fail_count += 1
        self.avg_reward = self.total_reward / self.usage_count if self.usage_count > 0 else 0

        self.confidence = min(1.0, self.usage_count / 50.0)

        if context not in self.context_rewards:
            self.context_rewards[context] = 0.0
        alpha = 0.3
        self.context_rewards[context] = (1 - alpha) * self.context_rewards[context] + alpha * reward

    def get_context_score(self, context: str) -> float:
        if context in self.context_rewards:
            return self.context_rewards[context]
        return self.avg_reward

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "total_reward": round(self.total_reward, 4),
            "usage_count": self.usage_count,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "avg_reward": round(self.avg_reward, 4),
            "confidence": round(self.confidence, 4),
            "success_rate": round(self.success_count / self.usage_count, 4) if self.usage_count > 0 else 0,
            "context_rewards": {k: round(v, 4) for k, v in self.context_rewards.items()},
        }


class RLHFEngine:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.feedback_file = os.path.join(data_dir, "rlhf_feedback.json")
        self.policy_file = os.path.join(data_dir, "rlhf_policy.json")
        self.feedback_history: list[FeedbackEntry] = []
        self.reward_history: list[RewardSignal] = []
        self.tool_policies: dict[str, ToolPolicy] = {}
        self.response_quality_scores: list[dict] = []
        self.learning_rate = 0.1
        self.discount_factor = 0.95
        self.exploration_rate = 0.15
        self.max_history = 500
        self._load_data()
        logger.info("RLHF Engine diinisialisasi")

    def _load_data(self):
        os.makedirs(self.data_dir, exist_ok=True)
        if os.path.exists(self.feedback_file):
            try:
                with open(self.feedback_file, "r") as f:
                    data = json.load(f)
                self.feedback_history = [FeedbackEntry.from_dict(d) for d in data.get("feedback", [])]
                self.reward_history = [
                    RewardSignal(r["tool_name"], r["action_context"], r["reward"], r.get("timestamp", 0))
                    for r in data.get("rewards", [])
                ]
                self.response_quality_scores = data.get("quality_scores", [])
                logger.info(f"RLHF data dimuat: {len(self.feedback_history)} feedback, {len(self.reward_history)} rewards")
            except Exception as e:
                logger.warning(f"Gagal memuat RLHF data: {e}")

        if os.path.exists(self.policy_file):
            try:
                with open(self.policy_file, "r") as f:
                    policy_data = json.load(f)
                for name, pd in policy_data.get("policies", {}).items():
                    policy = ToolPolicy(name)
                    policy.total_reward = pd.get("total_reward", 0)
                    policy.usage_count = pd.get("usage_count", 0)
                    policy.success_count = pd.get("success_count", 0)
                    policy.fail_count = pd.get("fail_count", 0)
                    policy.avg_reward = pd.get("avg_reward", 0)
                    policy.confidence = pd.get("confidence", 0)
                    policy.context_rewards = pd.get("context_rewards", {})
                    self.tool_policies[name] = policy
            except Exception as e:
                logger.warning(f"Gagal memuat policy data: {e}")

    def _save_data(self):
        os.makedirs(self.data_dir, exist_ok=True)
        feedback_data = {
            "feedback": [f.to_dict() for f in self.feedback_history[-self.max_history:]],
            "rewards": [r.to_dict() for r in self.reward_history[-self.max_history:]],
            "quality_scores": self.response_quality_scores[-self.max_history:],
            "metadata": {
                "last_updated": time.time(),
                "total_feedback": len(self.feedback_history),
                "total_rewards": len(self.reward_history),
            },
        }
        with open(self.feedback_file, "w") as f:
            json.dump(feedback_data, f, indent=2, ensure_ascii=False)

        policy_data = {
            "policies": {name: p.to_dict() for name, p in self.tool_policies.items()},
            "metadata": {
                "last_updated": time.time(),
                "learning_rate": self.learning_rate,
                "exploration_rate": self.exploration_rate,
            },
        }
        with open(self.policy_file, "w") as f:
            json.dump(policy_data, f, indent=2, ensure_ascii=False)

    def record_feedback(self, session_id: str, message_id: str,
                        feedback_type: str, value: float,
                        context: dict = None, comment: str = "") -> dict:
        feedback_id = f"fb_{int(time.time())}_{len(self.feedback_history)}"
        try:
            fb_type = FeedbackType(feedback_type)
        except ValueError:
            fb_type = FeedbackType.RATING

        if fb_type == FeedbackType.THUMBS_UP:
            value = 1.0
        elif fb_type == FeedbackType.THUMBS_DOWN:
            value = -1.0
        else:
            value = max(-1.0, min(1.0, value))

        entry = FeedbackEntry(
            feedback_id=feedback_id,
            session_id=session_id,
            message_id=message_id,
            feedback_type=fb_type,
            value=value,
            context=context or {},
            comment=comment,
        )
        self.feedback_history.append(entry)

        if context and "tools_used" in context:
            for tool_name in context["tools_used"]:
                self._update_tool_reward(tool_name, value, context.get("action_type", "general"))

        self._update_quality_score(session_id, message_id, value)
        self._save_data()

        logger.info(f"Feedback direkam: {feedback_id} ({fb_type.value}: {value})")
        return {"feedback_id": feedback_id, "status": "recorded", "value": value}

    def record_tool_outcome(self, tool_name: str, success: bool,
                            duration_ms: int, context: str = "general") -> dict:
        base_reward = 1.0 if success else -0.5
        speed_bonus = 0.0
        if success and duration_ms < 1000:
            speed_bonus = 0.2
        elif success and duration_ms < 5000:
            speed_bonus = 0.1
        elif duration_ms > 30000:
            speed_bonus = -0.1

        total_reward = base_reward + speed_bonus

        signal = RewardSignal(tool_name, context, total_reward)
        self.reward_history.append(signal)
        self._update_tool_reward(tool_name, total_reward, context)
        self._save_data()

        return {
            "tool": tool_name,
            "reward": round(total_reward, 4),
            "success": success,
        }

    def _update_tool_reward(self, tool_name: str, reward: float, context: str = "general"):
        if tool_name not in self.tool_policies:
            self.tool_policies[tool_name] = ToolPolicy(tool_name)
        self.tool_policies[tool_name].update(reward, context)

    def _update_quality_score(self, session_id: str, message_id: str, score: float):
        self.response_quality_scores.append({
            "session_id": session_id,
            "message_id": message_id,
            "score": score,
            "timestamp": time.time(),
        })

    def get_tool_preference(self, tool_candidates: list[str], context: str = "general") -> list[dict]:
        scored = []
        for tool_name in tool_candidates:
            policy = self.tool_policies.get(tool_name)
            if not policy:
                scored.append({
                    "tool": tool_name,
                    "score": 0.5 + self.exploration_rate,
                    "confidence": 0.0,
                    "reason": "belum ada data",
                })
                continue

            base_score = policy.get_context_score(context)
            normalized = (base_score + 1) / 2

            exploration_bonus = self.exploration_rate * (1 - policy.confidence)
            final_score = normalized * policy.confidence + exploration_bonus

            scored.append({
                "tool": tool_name,
                "score": round(final_score, 4),
                "confidence": round(policy.confidence, 4),
                "avg_reward": round(policy.avg_reward, 4),
                "success_rate": round(policy.success_count / policy.usage_count, 4) if policy.usage_count > 0 else 0,
                "reason": f"reward={policy.avg_reward:.2f}, conf={policy.confidence:.2f}",
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored

    def get_strategy_suggestion(self, task_type: str) -> dict:
        relevant_feedback = [
            f for f in self.feedback_history[-100:]
            if f.context.get("task_type") == task_type
        ]

        positive = [f for f in relevant_feedback if f.value > 0]
        negative = [f for f in relevant_feedback if f.value < 0]

        successful_tools = {}
        for f in positive:
            for tool in f.context.get("tools_used", []):
                successful_tools[tool] = successful_tools.get(tool, 0) + 1

        failed_tools = {}
        for f in negative:
            for tool in f.context.get("tools_used", []):
                failed_tools[tool] = failed_tools.get(tool, 0) + 1

        return {
            "task_type": task_type,
            "total_feedback": len(relevant_feedback),
            "positive_count": len(positive),
            "negative_count": len(negative),
            "satisfaction_rate": round(len(positive) / len(relevant_feedback), 4) if relevant_feedback else 0,
            "recommended_tools": sorted(successful_tools.items(), key=lambda x: x[1], reverse=True)[:5],
            "avoid_tools": sorted(failed_tools.items(), key=lambda x: x[1], reverse=True)[:3],
            "suggestion": self._generate_suggestion(positive, negative, successful_tools, failed_tools),
        }

    def _generate_suggestion(self, positive: list, negative: list,
                             success_tools: dict, fail_tools: dict) -> str:
        if not positive and not negative:
            return "Belum ada data feedback untuk memberikan saran."

        parts = []
        total = len(positive) + len(negative)
        rate = len(positive) / total if total > 0 else 0

        if rate >= 0.8:
            parts.append("Performa sangat baik. Pertahankan strategi saat ini.")
        elif rate >= 0.6:
            parts.append("Performa baik. Ada ruang untuk perbaikan.")
        elif rate >= 0.4:
            parts.append("Performa rata-rata. Perlu penyesuaian strategi.")
        else:
            parts.append("Performa perlu ditingkatkan secara signifikan.")

        if success_tools:
            top_tools = list(success_tools.keys())[:3]
            parts.append(f"Tool paling efektif: {', '.join(top_tools)}.")

        if fail_tools:
            bad_tools = list(fail_tools.keys())[:2]
            parts.append(f"Tool yang perlu dihindari/diperbaiki: {', '.join(bad_tools)}.")

        return " ".join(parts)

    def get_feedback_stats(self) -> dict:
        total = len(self.feedback_history)
        if total == 0:
            return {
                "total_feedback": 0,
                "positive": 0,
                "negative": 0,
                "neutral": 0,
                "avg_score": 0,
                "trend": "neutral",
                "tool_policies": {},
            }

        positive = sum(1 for f in self.feedback_history if f.value > 0)
        negative = sum(1 for f in self.feedback_history if f.value < 0)
        neutral = total - positive - negative
        avg_score = sum(f.value for f in self.feedback_history) / total

        recent = self.feedback_history[-20:]
        older = self.feedback_history[-40:-20] if len(self.feedback_history) > 20 else []
        recent_avg = sum(f.value for f in recent) / len(recent) if recent else 0
        older_avg = sum(f.value for f in older) / len(older) if older else recent_avg

        if recent_avg > older_avg + 0.1:
            trend = "improving"
        elif recent_avg < older_avg - 0.1:
            trend = "declining"
        else:
            trend = "stable"

        return {
            "total_feedback": total,
            "positive": positive,
            "negative": negative,
            "neutral": neutral,
            "avg_score": round(avg_score, 4),
            "satisfaction_rate": round(positive / total, 4) if total > 0 else 0,
            "trend": trend,
            "recent_avg": round(recent_avg, 4),
            "tool_policies": {name: p.to_dict() for name, p in self.tool_policies.items()},
            "total_rewards": len(self.reward_history),
        }

    def get_learning_insights(self) -> dict:
        insights = {
            "patterns": [],
            "recommendations": [],
            "performance_by_tool": {},
        }

        for name, policy in self.tool_policies.items():
            tool_data = policy.to_dict()
            if policy.usage_count >= 5:
                if policy.avg_reward > 0.5:
                    insights["patterns"].append(f"{name}: performa tinggi (avg reward: {policy.avg_reward:.2f})")
                elif policy.avg_reward < -0.2:
                    insights["patterns"].append(f"{name}: performa rendah (avg reward: {policy.avg_reward:.2f})")

                best_ctx = max(policy.context_rewards.items(), key=lambda x: x[1], default=("", 0))
                worst_ctx = min(policy.context_rewards.items(), key=lambda x: x[1], default=("", 0))
                if best_ctx[0]:
                    insights["patterns"].append(f"{name} paling efektif untuk: {best_ctx[0]}")
                if worst_ctx[0] and worst_ctx[1] < 0:
                    insights["patterns"].append(f"{name} kurang efektif untuk: {worst_ctx[0]}")

            insights["performance_by_tool"][name] = tool_data

        if self.feedback_history:
            recent_scores = [f.value for f in self.feedback_history[-50:]]
            avg = sum(recent_scores) / len(recent_scores)
            if avg < 0.3:
                insights["recommendations"].append("Tingkatkan kualitas respons - skor rata-rata rendah.")
            if avg > 0.7:
                insights["recommendations"].append("Kualitas respons sangat baik - pertahankan strategi.")

        low_confidence = [name for name, p in self.tool_policies.items() if p.confidence < 0.3]
        if low_confidence:
            insights["recommendations"].append(f"Kumpulkan lebih banyak data untuk: {', '.join(low_confidence)}")

        return insights

    def reset_policy(self, tool_name: Optional[str] = None):
        if tool_name:
            if tool_name in self.tool_policies:
                self.tool_policies[tool_name] = ToolPolicy(tool_name)
        else:
            self.tool_policies.clear()
        self._save_data()
