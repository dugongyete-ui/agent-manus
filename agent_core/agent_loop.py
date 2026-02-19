"""Agent Loop - Implementasi Agent Loop (Analyze, Think, Select, Execute, Observe)."""

import json
import logging
import time
from typing import Any, Optional

from agent_core.context_manager import ContextManager
from agent_core.knowledge_base import KnowledgeBase
from agent_core.llm_client import LLMClient
from agent_core.planner import Planner, TaskStatus
from agent_core.tool_selector import ToolSelector

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Kamu adalah Manus, agen AI otonom yang membantu pengguna menyelesaikan tugas.

Kamu memiliki akses ke alat-alat berikut:
1. **shell_tool** - Menjalankan perintah shell/terminal (ls, cat, grep, python3, node, pip, npm, dll)
2. **file_tool** - Operasi file: read, write, edit, append, view, list, delete, copy, move
3. **browser_tool** - Navigasi web, screenshot, klik elemen
4. **search_tool** - Pencarian informasi dari internet
5. **generate_tool** - Generasi media (gambar, video, audio)
6. **slides_tool** - Pembuatan presentasi
7. **webdev_tool** - Scaffolding proyek web (React, Vue, Flask, Express, Next.js)
8. **schedule_tool** - Penjadwalan tugas
9. **message_tool** - Komunikasi dengan pengguna

Saat pengguna meminta sesuatu, analisis kebutuhannya dan tentukan alat yang tepat.
Respons dalam format JSON berikut:

Jika perlu menggunakan alat:
{"action": "use_tool", "tool": "nama_tool", "params": {"key": "value"}, "reasoning": "alasan singkat"}

Jika bisa menjawab langsung tanpa alat:
{"action": "respond", "message": "respons kamu", "reasoning": "alasan singkat"}

Jika perlu beberapa langkah:
{"action": "multi_step", "steps": [{"tool": "nama_tool", "params": {"key": "value"}}], "reasoning": "alasan"}

Parameter yang tersedia untuk setiap tool:
- shell_tool: {"command": "perintah shell"}
- file_tool: {"operation": "read|write|edit|append|view|list|delete|copy|move", "path": "path", "content": "isi", "dest": "tujuan", "old_text": "teks lama", "new_text": "teks baru", "start_line": 1, "end_line": 10}
- search_tool: {"query": "kata kunci pencarian"}
- message_tool: {"content": "pesan", "type": "info|warning|success|error"}
"""


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
        self.llm = LLMClient()
        self.knowledge_base = KnowledgeBase()
        self.state = AgentState.IDLE
        self.max_iterations = config.get("agent", {}).get("max_iterations", 10)
        self.iteration_count = 0
        self.execution_log: list[dict] = []
        self._tool_executors: dict = {}
        self._tool_instances: dict = {}

        self.context_manager.set_system_prompt(SYSTEM_PROMPT)

    def register_tool(self, tool_name: str, tool_instance):
        self._tool_instances[tool_name] = tool_instance
        logger.info(f"Tool terdaftar: {tool_name}")

    def register_tool_executor(self, tool_name: str, executor_fn):
        self._tool_executors[tool_name] = executor_fn
        logger.info(f"Executor terdaftar untuk alat: {tool_name}")

    async def process_request(self, user_input: str) -> str:
        self.context_manager.add_message("user", user_input)
        self.iteration_count = 0
        self.execution_log.clear()

        try:
            while self.iteration_count < self.max_iterations:
                self.iteration_count += 1
                logger.info(f"--- Iterasi {self.iteration_count} ---")

                self.state = AgentState.THINKING
                context = self.context_manager.get_context_window()
                llm_input = self._build_llm_prompt(context)

                logger.info("Mengirim ke LLM...")
                raw_response = await self.llm.chat(llm_input)
                logger.info(f"Respons LLM diterima ({len(raw_response)} karakter)")

                action = self._parse_llm_response(raw_response)

                if action["type"] == "respond":
                    response = action["message"]
                    self.context_manager.add_message("assistant", response)
                    self.state = AgentState.COMPLETED
                    self._save_to_knowledge(user_input, response)
                    return response

                elif action["type"] == "use_tool":
                    self.state = AgentState.EXECUTING
                    tool_name = action["tool"]
                    params = action.get("params", {})
                    result = await self._execute_tool(tool_name, params)

                    observation = f"[Hasil {tool_name}]:\n{result}"
                    self.context_manager.add_message("assistant", f"Menggunakan {tool_name}...")
                    self.context_manager.add_message("system", observation)

                    self.state = AgentState.OBSERVING
                    self._log_step("execute", {"tool": tool_name, "params": params, "result": result[:500]})

                elif action["type"] == "multi_step":
                    self.state = AgentState.EXECUTING
                    all_results = []
                    for step in action.get("steps", []):
                        tool_name = step.get("tool", "")
                        params = step.get("params", {})
                        result = await self._execute_tool(tool_name, params)
                        all_results.append(f"[{tool_name}]: {result}")

                    observation = "\n".join(all_results)
                    self.context_manager.add_message("assistant", "Menjalankan beberapa langkah...")
                    self.context_manager.add_message("system", observation)

                    self.state = AgentState.OBSERVING

                elif action["type"] == "error":
                    response = action.get("message", raw_response)
                    self.context_manager.add_message("assistant", response)
                    self.state = AgentState.COMPLETED
                    return response

            final = await self._generate_final_response()
            self.context_manager.add_message("assistant", final)
            self.state = AgentState.COMPLETED
            return final

        except Exception as e:
            self.state = AgentState.ERROR
            logger.error(f"Error dalam agent loop: {e}", exc_info=True)
            return f"Terjadi kesalahan: {str(e)}"

    async def _execute_tool(self, tool_name: str, params: dict) -> str:
        tool = self._tool_instances.get(tool_name)
        if not tool:
            return f"Tool '{tool_name}' tidak ditemukan."

        start_time = time.time()
        try:
            if tool_name == "shell_tool":
                command = params.get("command", "")
                if command:
                    result = await tool.run_command(command)
                else:
                    result = "Tidak ada perintah yang diberikan."

            elif tool_name == "file_tool":
                result = await self._execute_file_tool(tool, params)

            elif tool_name == "search_tool":
                query = params.get("query", "")
                if query:
                    results = await tool.search(query)
                    result = tool._format_results(results) if results else "Tidak ada hasil."
                else:
                    result = "Tidak ada query pencarian."

            elif tool_name == "message_tool":
                content = params.get("content", "")
                msg_type = params.get("type", "info")
                if content:
                    tool.send(content, msg_type)
                    result = f"Pesan terkirim: {content}"
                else:
                    result = "Tidak ada konten pesan."

            elif tool_name == "browser_tool":
                url = params.get("url", "")
                if url:
                    nav_result = await tool.navigate(url)
                    result = nav_result.get("message", str(nav_result))
                else:
                    result = "Tidak ada URL yang diberikan."

            elif tool_name == "webdev_tool":
                name = params.get("name", "my_project")
                framework = params.get("framework", "flask")
                init_result = tool.init_project(name, framework)
                result = json.dumps(init_result, ensure_ascii=False)

            elif tool_name == "generate_tool":
                media_type = params.get("type", "image")
                prompt = params.get("prompt", "")
                gen_result = await tool.generate(media_type, prompt)
                result = gen_result.get("message", str(gen_result))

            elif tool_name == "slides_tool":
                title = params.get("title", "Presentasi")
                pres = tool.create_presentation(title)
                result = f"Presentasi '{title}' dibuat."

            elif tool_name == "schedule_tool":
                name = params.get("name", "tugas")
                interval = params.get("interval", 60)
                sched_result = tool.create_task(name, interval, "default")
                result = str(sched_result)

            else:
                result = f"Tool '{tool_name}' belum diimplementasikan."

            duration_ms = int((time.time() - start_time) * 1000)
            self.knowledge_base.log_tool_usage(tool_name, str(params)[:100], str(params)[:200], result[:200], True, duration_ms)
            logger.info(f"Tool {tool_name} selesai ({duration_ms}ms)")
            return result

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = f"Error pada {tool_name}: {str(e)}"
            self.knowledge_base.log_tool_usage(tool_name, str(params)[:100], str(params)[:200], error_msg, False, duration_ms)
            logger.error(error_msg)
            return error_msg

    async def _execute_file_tool(self, tool, params: dict) -> str:
        operation = params.get("operation", "read")
        path = params.get("path", "")

        if not path and operation not in ("list",):
            return "Path file tidak diberikan."

        if operation == "read":
            return tool.read_file(path)
        elif operation == "write":
            content = params.get("content", "")
            return tool.write_file(path, content)
        elif operation == "append":
            content = params.get("content", "")
            return tool.append_file(path, content)
        elif operation == "edit":
            old_text = params.get("old_text", "")
            new_text = params.get("new_text", "")
            return tool.edit_file(path, old_text, new_text)
        elif operation == "view":
            start_line = params.get("start_line", 1)
            end_line = params.get("end_line")
            return tool.view_file(path, start_line, end_line)
        elif operation == "list":
            target = path or "."
            entries = tool.list_directory(target)
            lines = []
            for e in entries:
                icon = "📁" if e["type"] == "directory" else "📄"
                size_str = f" ({e['size']} bytes)" if e["type"] == "file" else ""
                lines.append(f"{icon} {e['name']}{size_str}")
            return "\n".join(lines) if lines else "Direktori kosong."
        elif operation == "delete":
            return tool.delete_file(path)
        elif operation == "copy":
            dest = params.get("dest", "")
            if not dest:
                return "Tujuan copy tidak diberikan."
            return tool.copy_file(path, dest)
        elif operation == "move":
            dest = params.get("dest", "")
            if not dest:
                return "Tujuan move tidak diberikan."
            return tool.move_file(path, dest)
        else:
            return f"Operasi file tidak dikenal: {operation}"

    def _build_llm_prompt(self, context: list[dict]) -> str:
        parts = []
        for msg in context:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                parts.append(f"[System]: {content}")
            elif role == "user":
                parts.append(f"User: {content}")
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
        return "\n\n".join(parts)

    def _parse_llm_response(self, raw: str) -> dict:
        raw = raw.strip()

        json_str = None
        if "```json" in raw:
            start = raw.index("```json") + 7
            end = raw.index("```", start) if "```" in raw[start:] else len(raw)
            json_str = raw[start:end].strip()
        elif "```" in raw:
            start = raw.index("```") + 3
            end = raw.index("```", start) if "```" in raw[start:] else len(raw)
            json_str = raw[start:end].strip()
        elif raw.startswith("{"):
            brace_count = 0
            end_idx = 0
            for i, ch in enumerate(raw):
                if ch == '{':
                    brace_count += 1
                elif ch == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i + 1
                        break
            if end_idx > 0:
                json_str = raw[:end_idx]

        if json_str:
            try:
                parsed = json.loads(json_str)
                action = parsed.get("action", "respond")

                if action == "use_tool":
                    return {
                        "type": "use_tool",
                        "tool": parsed.get("tool", ""),
                        "params": parsed.get("params", {}),
                    }
                elif action == "multi_step":
                    return {
                        "type": "multi_step",
                        "steps": parsed.get("steps", []),
                    }
                elif action == "respond":
                    return {
                        "type": "respond",
                        "message": parsed.get("message", raw),
                    }
            except json.JSONDecodeError:
                pass

        return {"type": "respond", "message": raw}

    async def _generate_final_response(self) -> str:
        context = self.context_manager.get_context_window()
        prompt = self._build_llm_prompt(context)
        prompt += "\n\n[System]: Berikan ringkasan akhir dari semua yang sudah dilakukan. Respons sebagai teks biasa, bukan JSON."
        return await self.llm.chat(prompt)

    def _save_to_knowledge(self, user_input: str, response: str):
        try:
            self.knowledge_base.store(
                category="conversation",
                key=f"q_{int(time.time())}",
                value=user_input[:500],
                metadata={"response_preview": response[:200]},
            )
        except Exception as e:
            logger.debug(f"Gagal menyimpan ke knowledge base: {e}")

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

    async def cleanup(self):
        await self.llm.close()
