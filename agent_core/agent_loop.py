"""Agent Loop - Implementasi Agent Loop (Analyze, Think, Select, Execute, Observe)."""

import logging
import time
from typing import Any, Optional

from agent_core.context_manager import ContextManager
from agent_core.planner import Planner, TaskStatus
from agent_core.tool_selector import ToolSelector

logger = logging.getLogger(__name__)


class AgentState:
    IDLE = "idle"
    ANALYZING = "analyzing"
    THINKING = "thinking"
    SELECTING = "selecting"
    EXECUTING = "executing"
    OBSERVING = "observing"
    COMPLETED = "completed"
    ERROR = "error"


class AgentLoop:
    def __init__(self, config: dict):
        self.config = config
        self.context_manager = ContextManager(
            max_tokens=config.get("context", {}).get("max_tokens", 128000),
            memory_window=config.get("context", {}).get("memory_window", 20),
            summarization_threshold=config.get("context", {}).get("summarization_threshold", 15),
        )
        self.tool_selector = ToolSelector(config_path="config/tool_configs.json")
        self.planner = Planner()
        self.state = AgentState.IDLE
        self.max_iterations = config.get("agent", {}).get("max_iterations", 50)
        self.iteration_count = 0
        self.execution_log: list[dict] = []
        self._tool_executors: dict = {}

    def register_tool_executor(self, tool_name: str, executor_fn):
        self._tool_executors[tool_name] = executor_fn
        logger.info(f"Executor terdaftar untuk alat: {tool_name}")

    async def process_request(self, user_input: str) -> str:
        self.context_manager.add_message("user", user_input)
        self.iteration_count = 0

        try:
            while self.iteration_count < self.max_iterations:
                self.iteration_count += 1
                logger.info(f"--- Iterasi {self.iteration_count} ---")

                analysis = await self._analyze(user_input)
                if analysis.get("direct_response"):
                    response = analysis["direct_response"]
                    self.context_manager.add_message("assistant", response)
                    self.state = AgentState.COMPLETED
                    return response

                plan = await self._think(analysis)

                selected_tools = self._select(plan)

                results = await self._execute(selected_tools, plan)

                should_continue, observation = self._observe(results)

                if not should_continue:
                    self.context_manager.add_message("assistant", observation)
                    self.state = AgentState.COMPLETED
                    return observation

                user_input = observation

            return "Batas iterasi tercapai. Silakan coba lagi dengan instruksi yang lebih spesifik."

        except Exception as e:
            self.state = AgentState.ERROR
            logger.error(f"Error dalam agent loop: {e}")
            return f"Terjadi kesalahan: {str(e)}"

    async def _analyze(self, input_text: str) -> dict:
        self.state = AgentState.ANALYZING
        logger.info("Fase: ANALYZE")

        analysis = {
            "input": input_text,
            "intent": self._detect_intent(input_text),
            "requires_tools": True,
            "complexity": self._assess_complexity(input_text),
        }

        if analysis["complexity"] == "simple" and not any(
            kw in input_text.lower() for kw in ["buat", "jalankan", "cari", "tulis", "buka", "generate"]
        ):
            analysis["direct_response"] = self._generate_direct_response(input_text)
            analysis["requires_tools"] = False

        self._log_step("analyze", analysis)
        return analysis

    async def _think(self, analysis: dict) -> dict:
        self.state = AgentState.THINKING
        logger.info("Fase: THINK")

        intent = analysis.get("intent", "")
        steps = self._decompose_task(intent, analysis.get("input", ""))

        if steps:
            self.planner.create_plan(intent, steps)

        plan = {
            "intent": intent,
            "steps": steps,
            "analysis": analysis,
        }

        self._log_step("think", plan)
        return plan

    def _select(self, plan: dict) -> list:
        self.state = AgentState.SELECTING
        logger.info("Fase: SELECT")

        intent = plan.get("intent", "")
        selected = self.tool_selector.select_tools(intent)
        logger.info(f"Alat terpilih: {[t.name for t in selected]}")

        self._log_step("select", {"tools": [t.name for t in selected]})
        return selected

    async def _execute(self, tools: list, plan: dict) -> list[dict]:
        self.state = AgentState.EXECUTING
        logger.info("Fase: EXECUTE")

        results = []
        for tool_info in tools:
            executor = self._tool_executors.get(tool_info.name)
            if executor:
                try:
                    result = await executor(plan)
                    results.append({
                        "tool": tool_info.name,
                        "success": True,
                        "output": result,
                    })
                    self.tool_selector.record_usage(tool_info.name, True)
                except Exception as e:
                    results.append({
                        "tool": tool_info.name,
                        "success": False,
                        "error": str(e),
                    })
                    self.tool_selector.record_usage(tool_info.name, False)
            else:
                results.append({
                    "tool": tool_info.name,
                    "success": False,
                    "error": f"Tidak ada executor untuk {tool_info.name}",
                })

        self._log_step("execute", {"results": results})
        return results

    def _observe(self, results: list[dict]) -> tuple[bool, str]:
        self.state = AgentState.OBSERVING
        logger.info("Fase: OBSERVE")

        successes = [r for r in results if r.get("success")]
        failures = [r for r in results if not r.get("success")]

        observation_parts = []
        for r in successes:
            observation_parts.append(f"[{r['tool']}] Berhasil: {r.get('output', 'OK')}")
        for r in failures:
            observation_parts.append(f"[{r['tool']}] Gagal: {r.get('error', 'Unknown')}")

        observation = "\n".join(observation_parts) if observation_parts else "Tidak ada hasil."
        should_continue = len(failures) > 0 and len(successes) == 0

        next_task = self.planner.get_next_task()
        if next_task:
            should_continue = True

        self._log_step("observe", {"observation": observation, "continue": should_continue})
        return should_continue, observation

    def _detect_intent(self, text: str) -> str:
        intent_keywords = {
            "create_file": ["buat file", "tulis file", "create file"],
            "run_code": ["jalankan", "eksekusi", "run", "execute"],
            "search": ["cari", "temukan", "search", "find"],
            "browse": ["buka", "navigasi", "browse", "open url"],
            "generate_media": ["generate", "buat gambar", "buat video"],
            "create_presentation": ["presentasi", "slide", "pptx"],
            "build_web": ["website", "web app", "aplikasi web"],
            "schedule": ["jadwalkan", "schedule", "timer"],
            "communicate": ["kirim pesan", "beritahu", "notify"],
        }
        text_lower = text.lower()
        for intent, keywords in intent_keywords.items():
            for kw in keywords:
                if kw in text_lower:
                    return intent
        return "general"

    def _assess_complexity(self, text: str) -> str:
        word_count = len(text.split())
        if word_count < 10:
            return "simple"
        elif word_count < 50:
            return "medium"
        return "complex"

    def _decompose_task(self, intent: str, input_text: str) -> list[str]:
        decompositions = {
            "build_web": [
                "Analisis kebutuhan proyek web",
                "Inisialisasi proyek dengan framework yang sesuai",
                "Buat struktur file dan komponen",
                "Implementasi logika bisnis",
                "Uji dan verifikasi hasil",
            ],
            "create_presentation": [
                "Analisis topik presentasi",
                "Buat outline slide",
                "Generate konten untuk setiap slide",
                "Tambahkan elemen visual",
                "Finalisasi dan simpan file",
            ],
        }
        return decompositions.get(intent, [f"Proses permintaan: {input_text[:100]}"])

    def _generate_direct_response(self, text: str) -> str:
        return f"Saya memahami permintaan Anda. Untuk memproses '{text[:100]}', saya siap membantu."

    def _log_step(self, phase: str, data: Any):
        entry = {
            "iteration": self.iteration_count,
            "phase": phase,
            "data": data,
            "timestamp": time.time(),
        }
        self.execution_log.append(entry)

    def get_execution_summary(self) -> str:
        lines = [f"=== Ringkasan Eksekusi ({self.iteration_count} iterasi) ==="]
        for entry in self.execution_log:
            lines.append(f"  [{entry['phase'].upper()}] Iterasi {entry['iteration']}")
        if self.planner.tasks:
            lines.append(self.planner.get_plan_summary())
        return "\n".join(lines)
