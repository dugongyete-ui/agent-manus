"""Agent Loop - Implementasi Agent Loop (Analyze, Think, Select, Execute, Observe)."""

import json
import logging
import os
import re
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

SYSTEM_PROMPT = """Kamu adalah Manus, agen AI otonom yang BENAR-BENAR mengeksekusi tools. Kamu BUKAN chatbot biasa.

ATURAN MUTLAK:
1. Output HANYA JSON murni, TANPA markdown, TANPA teks tambahan, TANPA penjelasan
2. JANGAN PERNAH berkata "saya tidak bisa", "saya hanya AI", "saya tidak memiliki akses"
3. SELALU gunakan tool yang tepat untuk setiap permintaan
4. JANGAN menjelaskan apa yang akan kamu lakukan - LANGSUNG lakukan

FORMAT RESPONS (pilih salah satu, output JSON SAJA):
{"action":"use_tool","tool":"nama_tool","params":{...}}
{"action":"respond","message":"teks jawaban"}
{"action":"multi_step","steps":[{"tool":"t","params":{}}]}

TOOLS TERSEDIA:
1. shell_tool: {"command":"cmd"} atau {"action":"run_code","code":"...","runtime":"python3"}
2. file_tool: {"operation":"read|write|edit|list|delete|copy|move|analyze|search|info","path":"...","content":"..."}
3. browser_tool: {"action":"navigate|screenshot|click|fill|type|extract_text|extract_links|execute_js|scroll","url":"...","selector":"..."}
4. search_tool: {"query":"..."} atau {"action":"fetch","url":"..."}
5. generate_tool: {"type":"image|svg|chart|audio","prompt":"...","width":1024,"height":768}
6. slides_tool: {"action":"create|add_slide|export|list","title":"...","slides":[{"title":"...","content":"..."}]}
7. webdev_tool: {"action":"init|install_deps|add_dep|build|list_frameworks","framework":"react|vue|flask|express|nextjs|fastapi","name":"..."}
8. schedule_tool: {"action":"create|list|cancel","name":"...","interval":60}
9. message_tool: {"content":"...","type":"info|warning|success|error"}
10. skill_manager: {"action":"list|info|create|run_script|search","name":"..."}

PEMETAAN WAJIB:
- "buka/open/navigate [URL]" -> {"action":"use_tool","tool":"browser_tool","params":{"action":"navigate","url":"..."}}
- "cari/search [query]" -> {"action":"use_tool","tool":"search_tool","params":{"query":"..."}}
- "jalankan/run [command]" -> {"action":"use_tool","tool":"shell_tool","params":{"command":"..."}}
- "buat/baca/edit file" -> {"action":"use_tool","tool":"file_tool","params":{"operation":"...","path":"..."}}
- "buat gambar/image" -> {"action":"use_tool","tool":"generate_tool","params":{"type":"image","prompt":"..."}}
- pertanyaan umum -> {"action":"respond","message":"jawaban langsung"}

CONTOH OUTPUT BENAR:
{"action":"use_tool","tool":"search_tool","params":{"query":"berita terbaru AI 2026"}}
{"action":"use_tool","tool":"browser_tool","params":{"action":"navigate","url":"https://google.com"}}
{"action":"use_tool","tool":"shell_tool","params":{"command":"ls -la"}}
{"action":"respond","message":"Ini adalah jawaban saya..."}

INGAT: Output JSON murni. Tidak ada teks sebelum atau sesudah JSON. Tidak ada markdown code block.
"""

INTENT_PATTERNS = [
    {
        "patterns": [
            r"buka\s+((?:https?://)?(?:www\.)?[\w\-\.]+\.\w+[^\s]*)",
            r"(?:navigasi|navigate|akses|kunjungi|visit|open)\s+((?:https?://)?(?:www\.)?[\w\-\.]+\.\w+[^\s]*)",
            r"(?:buka|open|akses)\s+(?:situs|website|web|halaman|site)\s+([\w\-\.]+\.\w+[^\s]*)",
            r"(?:analisis|analyze|lihat|cek|check)\s+(?:situs|website|web|halaman|site)\s+([\w\-\.]+\.\w+[^\s]*)",
        ],
        "tool": "browser_tool",
        "build_params": lambda m: {"action": "navigate", "url": _ensure_url(m.group(1).strip().rstrip('.,;:'))},
    },
    {
        "patterns": [
            r"(?:cari|search|temukan|find|google)\s+(?:informasi\s+)?(?:tentang\s+|mengenai\s+|soal\s+|about\s+)?(.*)",
            r"(?:cari|search|find)\s+(.*)",
        ],
        "tool": "search_tool",
        "build_params": lambda m: {"query": m.group(1).strip().rstrip('.,;:')},
    },
    {
        "patterns": [
            r"(?:jalankan|run|eksekusi|execute)\s+(?:perintah|command|terminal|shell|cmd)\s*[:\-]?\s*(.*)",
            r"(?:jalankan|run|eksekusi|execute)\s+((?:ls|cat|grep|find|pwd|echo|mkdir|pip|npm|curl|wget|python|node|git|apt|cd|df|du|ps|top|whoami|hostname|date|uname)(?:\s+.*)?)",
            r"\$\s*(.*)",
        ],
        "tool": "shell_tool",
        "build_params": lambda m: {"command": m.group(1).strip()},
    },
    {
        "patterns": [
            r"(?:buat|create|tulis|write)\s+file\s+([\w\-\./]+)\s+(?:dengan\s+(?:isi|konten|content)\s+)?(.*)",
            r"(?:tulis|write)\s+(?:ke\s+)?file\s+([\w\-\./]+)",
            r"(?:baca|read|tampilkan|show|lihat|view)\s+(?:file|isi)\s+([\w\-\./]+)",
        ],
        "tool": "file_tool",
        "build_params": lambda m: _build_file_params(m),
    },
    {
        "patterns": [
            r"(?:buat|create|generate|hasilkan)\s+(?:gambar|image|foto|picture)\s+(.*)",
            r"(?:buat|create|generate)\s+(?:grafik|chart)\s+(.*)",
            r"(?:buat|create|generate)\s+(?:svg|ikon|icon)\s+(.*)",
        ],
        "tool": "generate_tool",
        "build_params": lambda m: {"type": "image", "prompt": m.group(1).strip(), "width": 1024, "height": 768},
    },
    {
        "patterns": [
            r"(?:buat|create)\s+(?:presentasi|slides?|ppt)\s+(?:tentang\s+)?(.*)",
        ],
        "tool": "slides_tool",
        "build_params": lambda m: {"action": "create", "title": m.group(1).strip(), "slides": [{"title": m.group(1).strip(), "content": "Konten presentasi"}]},
    },
    {
        "patterns": [
            r"(?:buat|create|init)\s+(?:proyek|project)\s+(?:web\s+)?(\w+)\s+(?:dengan|using|pakai)\s+(\w+)",
            r"(?:buat|create|scaffold)\s+(?:aplikasi|app)\s+(\w+)\s+(\w+)",
        ],
        "tool": "webdev_tool",
        "build_params": lambda m: {"action": "init", "name": m.group(1).strip(), "framework": m.group(2).strip().lower()},
    },
    {
        "patterns": [
            r"(?:jadwalkan|schedule|atur\s+jadwal)\s+(.*)",
        ],
        "tool": "schedule_tool",
        "build_params": lambda m: {"action": "create", "name": m.group(1).strip(), "interval": 60},
    },
    {
        "patterns": [
            r"(?:daftar|list)\s+(?:skill|kemampuan|keahlian)",
            r"(?:cari|search)\s+skill\s+(.*)",
        ],
        "tool": "skill_manager",
        "build_params": lambda m: {"action": "list"} if "list" in (m.group(0) or "").lower() or "daftar" in (m.group(0) or "").lower() else {"action": "search", "query": m.group(1).strip() if m.lastindex else ""},
    },
    {
        "patterns": [
            r"(?:tampilkan|show|lihat)\s+(?:daftar\s+)?(?:file|direktori|folder)",
            r"(?:ls|dir)\b",
        ],
        "tool": "shell_tool",
        "build_params": lambda m: {"command": "ls -la"},
    },
    {
        "patterns": [
            r"(?:coba|test|uji)\s+(?:semua\s+)?tools?",
            r"(?:jalankan|run)\s+(?:semua\s+)?tools?",
            r"demo\s+(?:semua\s+)?tools?",
        ],
        "tool": "_all_tools_demo",
        "build_params": lambda m: {},
    },
]


def _ensure_url(url_str: str) -> str:
    url_str = url_str.strip().rstrip('.,;:!?')
    if not url_str.startswith("http"):
        url_str = "https://" + url_str
    return url_str


def _build_file_params(m):
    full = m.group(0).lower()
    if any(w in full for w in ["baca", "read", "tampilkan", "show", "lihat", "view"]):
        return {"operation": "read", "path": m.group(1).strip()}
    path = m.group(1).strip()
    content = m.group(2).strip() if m.lastindex >= 2 and m.group(2) else "# New file\n"
    return {"operation": "write", "path": path, "content": content}


_QUESTION_PATTERNS = re.compile(
    r"^\s*(?:apa|siapa|dimana|kapan|kenapa|mengapa|bagaimana|berapa|apakah|what|who|where|when|why|how|which|can you|could you|do you|are you|is there|tolong jelaskan|jelaskan|explain)\b",
    re.IGNORECASE,
)

def detect_intent(user_input: str) -> Optional[dict]:
    text = user_input.strip()
    if len(text) < 3:
        return None
    if _QUESTION_PATTERNS.search(text):
        return None
    for rule in INTENT_PATTERNS:
        for pattern in rule["patterns"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                tool = rule["tool"]
                if tool == "_all_tools_demo":
                    return _build_all_tools_demo()
                try:
                    params = rule["build_params"](match)
                except Exception:
                    continue
                param_values = [str(v).strip() for v in params.values() if isinstance(v, str)]
                if not params or all(len(v) == 0 for v in param_values):
                    continue
                logger.info(f"Intent terdeteksi: {tool} dari '{text[:60]}' -> {params}")
                return {"type": "use_tool", "tool": tool, "params": params}
    return None


def _build_all_tools_demo():
    return {
        "type": "multi_step",
        "steps": [
            {"tool": "shell_tool", "params": {"command": "echo 'Shell tool aktif!' && date && uname -a"}},
            {"tool": "file_tool", "params": {"operation": "list", "path": "."}},
            {"tool": "search_tool", "params": {"query": "latest technology news 2026"}},
            {"tool": "message_tool", "params": {"content": "Semua tools berhasil dijalankan!", "type": "success"}},
            {"tool": "skill_manager", "params": {"action": "list"}},
            {"tool": "schedule_tool", "params": {"action": "list"}},
        ],
    }


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
                gen_params = {k: v for k, v in params.items() if k not in ("type", "prompt")}
                gen_result = await tool.generate(media_type, prompt, **gen_params)
                if isinstance(gen_result, dict):
                    result = gen_result.get("message", json.dumps(gen_result, ensure_ascii=False))
                else:
                    result = str(gen_result)

            elif tool_name == "slides_tool":
                action = params.get("action", "create")
                if action == "create":
                    title = params.get("title", "Presentasi")
                    slides_data = params.get("slides", [])
                    author = params.get("author", "Manus Agent")
                    theme = params.get("theme", "modern")
                    pres = tool.create_presentation(title, author=author)
                    for slide_data in slides_data:
                        s_title = slide_data.get("title", "")
                        s_content = slide_data.get("content", "")
                        s_layout = slide_data.get("layout", "title_content")
                        tool.add_slide(pres, s_title, s_content, s_layout)
                    result = f"Presentasi '{title}' dibuat dengan {len(slides_data)} slide."
                elif action == "add_slide":
                    s_title = params.get("title", "Slide")
                    s_content = params.get("content", "")
                    s_layout = params.get("layout", "title_content")
                    result = f"Slide '{s_title}' ditambahkan."
                elif action == "export":
                    title = params.get("title", "Presentasi")
                    fmt = params.get("format", "html")
                    if hasattr(tool, 'export_html'):
                        export_result = tool.export_html(title)
                        result = export_result if isinstance(export_result, str) else json.dumps(export_result, ensure_ascii=False)
                    elif hasattr(tool, 'export_presentation'):
                        export_result = tool.export_presentation(title, fmt)
                        result = export_result if isinstance(export_result, str) else json.dumps(export_result, ensure_ascii=False)
                    else:
                        result = f"Presentasi '{title}' di-export."
                elif action == "list":
                    if hasattr(tool, 'list_presentations'):
                        presentations = tool.list_presentations()
                        result = json.dumps(presentations, ensure_ascii=False)
                    else:
                        result = "Daftar presentasi kosong."
                else:
                    result = f"Aksi slides tidak dikenal: {action}"

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
        elif operation == "analyze":
            if hasattr(tool, 'analyze_file'):
                r = tool.analyze_file(path)
                return json.dumps(r, ensure_ascii=False, default=str) if isinstance(r, dict) else str(r)
            return tool.read_file(path)
        elif operation == "search":
            pattern = params.get("pattern", "*")
            directory = params.get("directory", path or ".")
            if hasattr(tool, 'search_files'):
                results = tool.search_files(directory, pattern)
                return "\n".join(results) if isinstance(results, list) else str(results)
            import glob as glob_mod
            matches = glob_mod.glob(os.path.join(directory, "**", pattern), recursive=True)
            return "\n".join(matches[:50]) if matches else "Tidak ditemukan file yang cocok."
        elif operation == "info":
            if hasattr(tool, 'get_file_info'):
                r = tool.get_file_info(path)
                return json.dumps(r, ensure_ascii=False, default=str) if isinstance(r, dict) else str(r)
            import os as os_mod
            try:
                stat = os_mod.stat(path)
                return json.dumps({"path": path, "size": stat.st_size, "modified": stat.st_mtime, "exists": True}, ensure_ascii=False)
            except FileNotFoundError:
                return json.dumps({"path": path, "exists": False})
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

    def _parse_llm_response(self, raw: str, user_input: str = "") -> dict:
        raw = raw.strip()

        json_candidates = []

        if "```json" in raw:
            start = raw.index("```json") + 7
            rest = raw[start:]
            end = rest.find("```")
            if end == -1:
                end = len(rest)
            json_candidates.append(rest[:end].strip())
        if "```" in raw and not json_candidates:
            start = raw.index("```") + 3
            rest = raw[start:]
            end = rest.find("```")
            if end == -1:
                end = len(rest)
            candidate = rest[:end].strip()
            if candidate.startswith("{"):
                json_candidates.append(candidate)

        first_brace = raw.find("{")
        if first_brace != -1:
            brace_count = 0
            end_idx = 0
            for i in range(first_brace, len(raw)):
                if raw[i] == '{':
                    brace_count += 1
                elif raw[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i + 1
                        break
            if end_idx > 0:
                json_candidates.append(raw[first_brace:end_idx])

        for json_str in json_candidates:
            try:
                parsed = json.loads(json_str)
                if not isinstance(parsed, dict):
                    continue
                action = parsed.get("action", "")

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
                elif "tool" in parsed and "params" in parsed:
                    return {
                        "type": "use_tool",
                        "tool": parsed.get("tool", ""),
                        "params": parsed.get("params", {}),
                    }
                elif "steps" in parsed and isinstance(parsed["steps"], list):
                    return {
                        "type": "multi_step",
                        "steps": parsed["steps"],
                    }
                elif "message" in parsed:
                    return {
                        "type": "respond",
                        "message": parsed["message"],
                    }
            except (json.JSONDecodeError, ValueError):
                continue

        tool_pattern = re.search(
            r'(?:menggunakan|gunakan|use|call|jalankan|run)\s+(shell_tool|file_tool|browser_tool|search_tool|generate_tool|slides_tool|webdev_tool|schedule_tool|message_tool|skill_manager)',
            raw, re.IGNORECASE
        )
        if tool_pattern:
            tool_name = tool_pattern.group(1).lower()
            return {
                "type": "use_tool",
                "tool": tool_name,
                "params": {},
            }

        if user_input:
            intent = detect_intent(user_input)
            if intent:
                logger.info(f"Fallback intent detection dari user_input: {intent['type']}")
                return intent

        refusal_patterns = [
            r"(?:saya|aku)\s+(?:tidak\s+)?(?:bisa|dapat|mampu)\s+(?:tidak\s+)?(?:langsung\s+)?(?:membuka|menjalankan|mengeksekusi|mengakses)",
            r"(?:tidak\s+)?(?:memiliki|punya)\s+(?:akses|kemampuan)",
            r"(?:sebagai\s+)?(?:AI|model\s+bahasa|asisten\s+virtual)",
            r"(?:saya\s+)?(?:hanya\s+)?(?:bisa\s+)?(?:menjelaskan|mendeskripsikan|memberikan\s+gambaran)",
            r"(?:i\s+)?(?:can'?t|cannot|unable\s+to)\s+(?:directly|actually)?\s*(?:open|run|execute|access|browse)",
        ]
        is_refusal = any(re.search(p, raw, re.IGNORECASE) for p in refusal_patterns)

        if is_refusal and user_input:
            intent = detect_intent(user_input)
            if intent:
                logger.info(f"LLM refused but intent detected, forcing tool: {intent}")
                return intent

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
