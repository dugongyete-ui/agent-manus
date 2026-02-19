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
from agent_core.rlhf_engine import RLHFEngine
from agent_core.meta_learner import MetaLearner
from agent_core.security_manager import SecurityManager

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Kamu adalah Manus, agen AI otonom yang membantu pengguna menyelesaikan tugas.

Kamu memiliki akses ke alat-alat berikut:
1. **shell_tool** - Menjalankan perintah shell/terminal (ls, cat, grep, python3, node, pip, npm, dll). Mendukung run_code untuk eksekusi kode langsung.
2. **file_tool** - Operasi file: read, write, edit, append, view, list, delete, copy, move. Juga analyze_file untuk analisis dokumen (PDF, gambar, audio, kode, data).
3. **browser_tool** - Navigasi web dengan Playwright: navigate, screenshot, click, fill_form, type_text, extract_text, extract_links, execute_javascript, scroll, go_back, go_forward, wait_for_element
4. **search_tool** - Pencarian web via DuckDuckGo. Juga bisa fetch halaman web: fetch_page_content
5. **generate_tool** - Generasi media (gambar, SVG, chart, audio, video, dokumen)
6. **slides_tool** - Pembuatan presentasi
7. **webdev_tool** - Scaffolding proyek web (React, Vue, Flask, Express, Next.js, FastAPI). Mendukung install_dependencies, add_dependency, build_project
8. **schedule_tool** - Penjadwalan & otomatisasi tugas: interval, cron, dan one-time. Operasi: create, create_cron, create_once, cancel, pause, resume, list, status, history, stats
9. **message_tool** - Komunikasi dengan pengguna
10. **skill_manager** - Manajemen skill modular: list, info, create, update, delete, run_script, search, reload

Saat pengguna meminta sesuatu, analisis kebutuhannya dan tentukan alat yang tepat.
Respons dalam format JSON berikut:

Jika perlu menggunakan alat:
{"action": "use_tool", "tool": "nama_tool", "params": {"key": "value"}, "reasoning": "alasan singkat"}

Jika bisa menjawab langsung tanpa alat:
{"action": "respond", "message": "respons kamu", "reasoning": "alasan singkat"}

Jika perlu beberapa langkah:
{"action": "multi_step", "steps": [{"tool": "nama_tool", "params": {"key": "value"}}], "reasoning": "alasan"}

Parameter yang tersedia untuk setiap tool:
- shell_tool: {"command": "perintah"} atau {"action": "run_code", "code": "kode", "runtime": "python3|node|bash"}
- file_tool: {"operation": "read|write|edit|append|view|list|delete|copy|move|analyze", "path": "path", "content": "isi", "dest": "tujuan", "old_text": "teks lama", "new_text": "teks baru", "start_line": 1, "end_line": 10}
- browser_tool: {"action": "navigate|screenshot|click|fill|type|extract_text|extract_links|execute_js|scroll|go_back|wait_for", "url": "url", "selector": "css_selector", "value": "nilai", "script": "js_code", "direction": "up|down|top|bottom", "path": "screenshot.png"}
- search_tool: {"query": "kata kunci"} atau {"action": "fetch", "url": "url"}
- webdev_tool: {"action": "init|install_deps|add_dep|build", "name": "nama", "framework": "react|vue|flask|express|nextjs|fastapi", "packages": ["pkg1"], "project_dir": "dir"}
- schedule_tool: {"action": "create|create_cron|create_once|cancel|pause|resume|list|status|history|stats", "name": "nama", "interval": 60, "cron_expression": "*/5 * * * *", "delay_seconds": 300, "callback": "default", "task_id": "sched_1"}
- skill_manager: {"action": "list|info|create|update|delete|run_script|search|reload", "name": "nama_skill", "description": "deskripsi", "capabilities": ["cap1"], "script": "nama_script", "args": {}, "query": "kata kunci"}
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
        self.rlhf_engine = RLHFEngine()
        self.meta_learner = MetaLearner()
        self.security_manager = SecurityManager()
        self.planner = Planner(meta_learner=self.meta_learner)
        self.llm = LLMClient()
        self.knowledge_base = KnowledgeBase()
        self.state = AgentState.IDLE
        self.max_iterations = config.get("agent", {}).get("max_iterations", 10)
        self.iteration_count = 0
        self.execution_log: list[dict] = []
        self._tool_executors: dict = {}
        self._tool_instances: dict = {}
        self._current_tools_used: list[str] = []

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
        self._current_tools_used = []
        start_time = time.time()

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
                    duration_total = int((time.time() - start_time) * 1000)
                    self.meta_learner.record_execution(
                        user_input, self._current_tools_used, True,
                        duration_total, self.iteration_count
                    )
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
            duration_total = int((time.time() - start_time) * 1000)
            self.meta_learner.record_execution(
                user_input, self._current_tools_used, True,
                duration_total, self.iteration_count
            )
            return final

        except Exception as e:
            self.state = AgentState.ERROR
            logger.error(f"Error dalam agent loop: {e}", exc_info=True)
            return f"Terjadi kesalahan: {str(e)}"

    async def _execute_tool(self, tool_name: str, params: dict) -> str:
        tool = self._tool_instances.get(tool_name)
        if not tool:
            return f"Tool '{tool_name}' tidak ditemukan."

        if tool_name == "shell_tool" and "command" in params:
            sec_check = self.security_manager.validate_command(params["command"])
            if not sec_check.get("allowed"):
                return f"[KEAMANAN] Perintah diblokir: {sec_check.get('reason', 'tidak diizinkan')}"

        if tool_name == "file_tool" and "path" in params:
            operation = params.get("operation", "read")
            sec_check = self.security_manager.validate_file_path(params["path"], operation)
            if not sec_check.get("allowed"):
                return f"[KEAMANAN] Akses path diblokir: {sec_check.get('reason', 'tidak diizinkan')}"

        self._current_tools_used.append(tool_name)

        start_time = time.time()
        try:
            if tool_name == "shell_tool":
                action = params.get("action", "")
                if action == "run_code":
                    code = params.get("code", "")
                    runtime = params.get("runtime", "python3")
                    result = await tool.run_code(code, runtime) if code else "Tidak ada kode yang diberikan."
                else:
                    command = params.get("command", "")
                    result = await tool.run_command(command) if command else "Tidak ada perintah yang diberikan."

            elif tool_name == "file_tool":
                result = await self._execute_file_tool(tool, params)

            elif tool_name == "search_tool":
                action = params.get("action", "")
                if action == "fetch":
                    url = params.get("url", "")
                    if url:
                        fetch_result = await tool.fetch_page_content(url)
                        if fetch_result.get("success"):
                            result = f"Judul: {fetch_result.get('title', '')}\n\n{fetch_result.get('text', '')[:5000]}"
                        else:
                            result = f"Gagal fetch: {fetch_result.get('error', 'unknown')}"
                    else:
                        result = "Tidak ada URL untuk fetch."
                else:
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
                result = await self._execute_browser_tool(tool, params)

            elif tool_name == "webdev_tool":
                result = await self._execute_webdev_tool(tool, params)

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
                result = await tool.execute(params)

            elif tool_name == "skill_manager":
                result = await tool.execute(params)

            else:
                result = f"Tool '{tool_name}' belum diimplementasikan."

            duration_ms = int((time.time() - start_time) * 1000)
            self.knowledge_base.log_tool_usage(tool_name, str(params)[:100], str(params)[:200], result[:200], True, duration_ms)
            self.rlhf_engine.record_tool_outcome(tool_name, True, duration_ms, context="execution")
            logger.info(f"Tool {tool_name} selesai ({duration_ms}ms)")
            return result

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = f"Error pada {tool_name}: {str(e)}"
            self.knowledge_base.log_tool_usage(tool_name, str(params)[:100], str(params)[:200], error_msg, False, duration_ms)
            self.rlhf_engine.record_tool_outcome(tool_name, False, duration_ms, context="execution")
            logger.error(error_msg)
            return error_msg

    async def _execute_browser_tool(self, tool, params: dict) -> str:
        action = params.get("action", "navigate")

        if action == "navigate":
            url = params.get("url", "")
            if not url:
                return "Tidak ada URL yang diberikan."
            r = await tool.navigate(url)
            return r.get("message", str(r))
        elif action == "screenshot":
            path = params.get("path", "screenshot.png")
            full_page = params.get("full_page", False)
            r = await tool.screenshot(path, full_page)
            return r.get("message", str(r))
        elif action == "click":
            selector = params.get("selector", "")
            if not selector:
                return "Selector tidak diberikan."
            r = await tool.click_element(selector)
            return r.get("message", str(r))
        elif action == "fill":
            selector = params.get("selector", "")
            value = params.get("value", "")
            r = await tool.fill_form(selector, value)
            return r.get("message", str(r))
        elif action == "type":
            selector = params.get("selector", "")
            text = params.get("value", "")
            r = await tool.type_text(selector, text)
            return r.get("message", str(r))
        elif action == "extract_text":
            selector = params.get("selector")
            r = await tool.extract_text(selector)
            if r.get("success"):
                return r.get("text", "") or "\n".join(r.get("texts", []))
            return f"Gagal: {r.get('error', '')}"
        elif action == "extract_links":
            r = await tool.extract_links()
            if r.get("success"):
                links = r.get("links", [])[:20]
                return "\n".join([f"- [{l['text'][:80]}]({l['href']})" for l in links])
            return f"Gagal: {r.get('error', '')}"
        elif action == "execute_js":
            script = params.get("script", "")
            r = await tool.execute_javascript(script)
            return r.get("message", str(r))
        elif action == "scroll":
            direction = params.get("direction", "down")
            amount = params.get("amount", 500)
            r = await tool.scroll(direction, amount)
            return f"Scroll {direction}" if r.get("success") else str(r)
        elif action == "go_back":
            r = await tool.go_back()
            return r.get("message", str(r))
        elif action == "go_forward":
            r = await tool.go_forward()
            return r.get("message", str(r))
        elif action == "wait_for":
            selector = params.get("selector", "")
            r = await tool.wait_for_element(selector)
            return r.get("message", str(r))
        else:
            url = params.get("url", "")
            if url:
                r = await tool.navigate(url)
                return r.get("message", str(r))
            return f"Aksi browser tidak dikenal: {action}"

    async def _execute_webdev_tool(self, tool, params: dict) -> str:
        action = params.get("action", "init")

        if action == "init":
            name = params.get("name", "my_project")
            framework = params.get("framework", "flask")
            output_dir = params.get("output_dir", ".")
            r = tool.init_project(name, framework, output_dir)
            return json.dumps(r, ensure_ascii=False)
        elif action == "install_deps":
            project_dir = params.get("project_dir", ".")
            manager = params.get("manager", "npm")
            r = await tool.install_dependencies(project_dir, manager)
            return json.dumps(r, ensure_ascii=False)
        elif action == "add_dep":
            project_dir = params.get("project_dir", ".")
            packages = params.get("packages", [])
            manager = params.get("manager", "npm")
            dev = params.get("dev", False)
            r = await tool.add_dependency(project_dir, packages, manager, dev)
            return json.dumps(r, ensure_ascii=False)
        elif action == "build":
            project_dir = params.get("project_dir", ".")
            framework = params.get("framework", "")
            r = await tool.build_project(project_dir, framework)
            return json.dumps(r, ensure_ascii=False)
        elif action == "list_frameworks":
            frameworks = tool.list_frameworks()
            return json.dumps(frameworks, ensure_ascii=False)
        else:
            return f"Aksi webdev tidak dikenal: {action}. Gunakan: init, install_deps, add_dep, build, list_frameworks"

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
        for tool_name, tool in self._tool_instances.items():
            if hasattr(tool, 'close'):
                try:
                    await tool.close()
                except Exception as e:
                    logger.debug(f"Error menutup {tool_name}: {e}")
            if hasattr(tool, 'cleanup'):
                try:
                    await tool.cleanup()
                except Exception as e:
                    logger.debug(f"Error cleanup {tool_name}: {e}")
        await self.llm.close()
