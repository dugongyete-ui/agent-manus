"""Agent Loop - Implementasi Agent Loop (Plan, Think, Execute, Reflect, Synthesize)."""

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

SYSTEM_PROMPT = """You are Manus, an autonomous AI agent that EXECUTES tools directly. You are NOT a chatbot.

=== CRITICAL OUTPUT RULE ===
Your ENTIRE response must be a SINGLE valid JSON object. NOTHING else.
- NO text before or after the JSON
- NO markdown code blocks (no ```)
- NO explanations outside the JSON
- NO comments

=== DECISION PRIORITY ===
1. If a tool can fulfill the request -> ALWAYS use {"action":"use_tool",...}
2. If multiple tools are needed -> use {"action":"multi_step",...} or {"action":"plan",...}
3. If the request is ambiguous and you cannot determine the right tool -> use {"action":"respond","message":"Please clarify: [specific question about what the user wants]"}
4. ONLY if no tool is relevant (general knowledge question, greeting, opinion) -> use {"action":"respond","message":"..."}

NEVER say "I can't", "I'm just an AI", or "I don't have access". You HAVE tools. USE them.

=== JSON RESPONSE FORMATS (choose exactly ONE) ===

FORMAT 1 - PLAN (for complex multi-step tasks):
{"action":"plan","goal":"clear description of what to achieve","steps":["step 1: what to do","step 2: what to do","step 3: what to do"]}

Example:
{"action":"plan","goal":"Create a Python web scraper","steps":["step 1: search_tool - find best scraping library","step 2: file_tool - create scraper.py","step 3: shell_tool - run and test the script"]}

FORMAT 2 - THINK (reason before deciding next action):
{"action":"think","thought":"your analysis and reasoning"}

Example:
{"action":"think","thought":"The user wants to analyze a website. I should first navigate to it with browser_tool, then extract the text content."}

FORMAT 3 - USE TOOL (execute a single tool - PREFERRED for most requests):
{"action":"use_tool","tool":"tool_name","params":{"key":"value"}}

Examples:
{"action":"use_tool","tool":"shell_tool","params":{"command":"ls -la /home/runner/workspace"}}
{"action":"use_tool","tool":"file_tool","params":{"operation":"read","path":"config.yaml"}}
{"action":"use_tool","tool":"file_tool","params":{"operation":"write","path":"hello.py","content":"print('Hello World')"}}
{"action":"use_tool","tool":"search_tool","params":{"query":"latest Python frameworks 2026"}}
{"action":"use_tool","tool":"browser_tool","params":{"action":"navigate","url":"https://google.com"}}
{"action":"use_tool","tool":"generate_tool","params":{"type":"image","prompt":"sunset landscape","width":1024,"height":768}}
{"action":"use_tool","tool":"slides_tool","params":{"action":"create","title":"AI Overview","slides":[{"title":"Introduction","content":"What is AI?"},{"title":"Applications","content":"Real-world uses of AI"}]}}
{"action":"use_tool","tool":"webdev_tool","params":{"action":"init","name":"myapp","framework":"flask"}}
{"action":"use_tool","tool":"schedule_tool","params":{"action":"list"}}
{"action":"use_tool","tool":"message_tool","params":{"content":"Task completed successfully!","type":"success"}}
{"action":"use_tool","tool":"skill_manager","params":{"action":"list"}}
{"action":"use_tool","tool":"shell_tool","params":{"action":"run_code","code":"for i in range(5): print(i)","runtime":"python3"}}

FORMAT 4 - MULTI STEP (execute multiple tools in sequence):
{"action":"multi_step","steps":[{"tool":"tool_name","params":{"key":"value"}},{"tool":"tool_name2","params":{"key":"value"}}]}

Example:
{"action":"multi_step","steps":[{"tool":"shell_tool","params":{"command":"date"}},{"tool":"file_tool","params":{"operation":"list","path":"."}}]}

FORMAT 5 - RESPOND (text answer - ONLY when no tool is needed):
{"action":"respond","message":"your response text here"}

Example:
{"action":"respond","message":"Python is a high-level programming language known for its simplicity and readability."}

=== AVAILABLE TOOLS ===
1. shell_tool - Run shell commands or code
   params: {"command":"cmd"} or {"action":"run_code","code":"...","runtime":"python3|node|bash|ruby|php"}
2. file_tool - File operations (read/write/edit/list/delete/copy/move/analyze/search/info)
   params: {"operation":"read|write|edit|list|delete|copy|move|analyze|search|info","path":"...","content":"..."}
3. browser_tool - Web browser automation
   params: {"action":"navigate|screenshot|click|fill|type|extract_text|extract_links|execute_js|scroll","url":"...","selector":"..."}
4. search_tool - Internet search or URL fetch
   params: {"query":"..."} or {"action":"fetch","url":"..."}
5. generate_tool - Generate media (image/svg/chart/audio/document)
   params: {"type":"image|svg|chart|audio","prompt":"...","width":1024,"height":768}
6. slides_tool - Create and manage presentations
   params: {"action":"create|add_slide|export|list","title":"...","slides":[{"title":"...","content":"..."}]}
7. webdev_tool - Scaffold web projects
   params: {"action":"init|install_deps|add_dep|build|list_frameworks","framework":"react|vue|flask|express|nextjs|fastapi","name":"..."}
8. schedule_tool - Schedule recurring or one-time tasks
   params: {"action":"create|list|cancel","name":"...","interval":60}
9. message_tool - Send notifications to user
   params: {"content":"...","type":"info|warning|success|error"}
10. skill_manager - Manage extensible skills
    params: {"action":"list|info|create|run_script|search","name":"..."}

=== MANDATORY MAPPING ===
User says "open/buka/navigate [URL]" -> {"action":"use_tool","tool":"browser_tool","params":{"action":"navigate","url":"[URL]"}}
User says "search/cari [query]" -> {"action":"use_tool","tool":"search_tool","params":{"query":"[query]"}}
User says "run/jalankan [command]" -> {"action":"use_tool","tool":"shell_tool","params":{"command":"[command]"}}
User says "create/read/write/edit file" -> {"action":"use_tool","tool":"file_tool","params":{...}}
User says "generate/buat image/gambar" -> {"action":"use_tool","tool":"generate_tool","params":{...}}
User asks a general knowledge question -> {"action":"respond","message":"[answer]"}
User request is unclear or ambiguous -> {"action":"respond","message":"Could you clarify what you'd like me to do? For example: [suggestions]"}

=== WORKFLOW FOR COMPLEX TASKS ===
1. First output: {"action":"plan",...} with clear steps
2. Then for each step: {"action":"use_tool",...}
3. After seeing each result: decide if more steps are needed
4. When done: {"action":"respond","message":"summary of what was accomplished"}

OUTPUT ONLY VALID JSON. NOTHING ELSE.
"""

PLANNING_PROMPT = """You are analyzing a user request to create an execution plan.
Analyze the request and determine what tools to use and in what order.

User request: {user_input}

Respond with ONLY this JSON format:
{{"action":"plan","goal":"clear description of what to achieve","steps":["step 1: description with tool_name","step 2: description with tool_name","step 3: ..."]}}

If the request is a simple question that needs no tools, respond with:
{{"action":"respond","message":"your direct answer"}}

Output ONLY valid JSON. No other text."""

REFLECTION_PROMPT = """You just executed a tool and got a result. Analyze it and decide what to do next.

Original goal: {goal}
Current plan: {plan_summary}
Step just completed: {completed_step}
Result: {result}
Steps remaining: {remaining_steps}

Based on the result, decide your next action. Respond with ONLY ONE of these JSON formats:

If more work is needed (continue with plan):
{{"action":"use_tool","tool":"tool_name","params":{{...}}}}

If the result requires a different approach:
{{"action":"think","thought":"analysis of why we need to change approach and what to do instead"}}

If all work is done and you can give a final answer:
{{"action":"respond","message":"comprehensive summary of everything done and results"}}

Output ONLY valid JSON. No other text."""

SYNTHESIS_PROMPT = """Based on everything that was done, provide a comprehensive final response to the user.

Original request: {user_input}
Execution log:
{execution_summary}

Provide a clear, helpful summary of what was accomplished, including key results and findings.
Respond as plain text, not JSON. Be thorough but concise."""

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
    PLANNING = "planning"
    THINKING = "thinking"
    SELECTING = "selecting"
    EXECUTING = "executing"
    REFLECTING = "reflecting"
    OBSERVING = "observing"
    SYNTHESIZING = "synthesizing"
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
        self._current_plan: Optional[dict] = None
        self._plan_step_index: int = 0

        self.context_manager.set_system_prompt(SYSTEM_PROMPT)

    def register_tool(self, tool_name: str, tool_instance):
        self._tool_instances[tool_name] = tool_instance
        logger.info(f"Tool terdaftar: {tool_name}")

    def register_tool_executor(self, tool_name: str, executor_fn):
        self._tool_executors[tool_name] = executor_fn
        logger.info(f"Executor terdaftar untuk alat: {tool_name}")

    async def _create_initial_plan(self, user_input: str) -> Optional[dict]:
        self.state = AgentState.PLANNING
        logger.info("Phase 1 - PLANNING: Asking LLM to create execution plan...")

        prompt = PLANNING_PROMPT.format(user_input=user_input)
        try:
            raw_response = await self.llm.chat(prompt)
            logger.info(f"Planning response received ({len(raw_response)} chars)")

            action = self._parse_llm_response(raw_response, user_input)

            if action["type"] == "plan":
                goal = action.get("goal", user_input)
                steps = action.get("steps", [])
                if steps:
                    self.planner.create_plan(goal, steps)
                    self._current_plan = {
                        "goal": goal,
                        "steps": steps,
                        "results": [],
                        "status": "in_progress",
                    }
                    self._plan_step_index = 0
                    logger.info(f"Plan created: {goal} with {len(steps)} steps")
                    self._log_step("plan_created", {"goal": goal, "steps": steps})
                    return self._current_plan
                else:
                    logger.info("Plan had no steps, proceeding without plan")
                    return None

            elif action["type"] == "respond":
                return {"direct_response": action["message"]}

            elif action["type"] in ("use_tool", "multi_step"):
                return {"immediate_action": action}

            return None

        except Exception as e:
            logger.warning(f"Planning phase failed: {e}, proceeding without plan")
            return None

    async def _reflect_on_result(self, goal: str, completed_step: str, result: str, remaining_steps: list[str]) -> dict:
        self.state = AgentState.REFLECTING
        logger.info("Phase 3 - REFLECTION: Analyzing result and deciding next steps...")

        plan_summary = self.planner.get_plan_summary() if self.planner.tasks else "No formal plan"
        remaining_str = json.dumps(remaining_steps, ensure_ascii=False) if remaining_steps else "None"

        result_truncated = result[:2000] if len(result) > 2000 else result

        prompt = REFLECTION_PROMPT.format(
            goal=goal,
            plan_summary=plan_summary,
            completed_step=completed_step,
            result=result_truncated,
            remaining_steps=remaining_str,
        )

        try:
            raw_response = await self.llm.chat(prompt)
            logger.info(f"Reflection response received ({len(raw_response)} chars)")
            action = self._parse_llm_response(raw_response)
            return action
        except Exception as e:
            logger.warning(f"Reflection failed: {e}")
            if remaining_steps:
                return {"type": "think", "thought": f"Reflection failed but continuing with remaining steps: {remaining_steps[0]}"}
            return {"type": "respond", "message": f"Task completed. Result: {result_truncated}"}

    async def process_request(self, user_input: str) -> str:
        self.context_manager.add_message("user", user_input)
        self.iteration_count = 0
        self.execution_log.clear()
        self._current_tools_used = []
        self._current_plan = None
        self._plan_step_index = 0
        self._retry_done = False
        start_time = time.time()

        try:
            plan_result = await self._create_initial_plan(user_input)

            if plan_result and "direct_response" in plan_result:
                response = plan_result["direct_response"]
                self.context_manager.add_message("assistant", response)
                self.state = AgentState.COMPLETED
                self._save_to_knowledge(user_input, response)
                return response

            if plan_result and "immediate_action" in plan_result:
                action = plan_result["immediate_action"]
                if action["type"] == "use_tool":
                    result = await self._execute_tool(action["tool"], action.get("params", {}))
                    self.context_manager.add_message("assistant", f"Menggunakan {action['tool']}...")
                    self.context_manager.add_message("system", f"[Hasil {action['tool']}]:\n{result}")
                    self._log_step("execute", {"tool": action["tool"], "params": action.get("params", {}), "result": result[:500]})
                elif action["type"] == "multi_step":
                    all_results = []
                    for step in action.get("steps", []):
                        tool_name = step.get("tool", "")
                        params = step.get("params", {})
                        result = await self._execute_tool(tool_name, params)
                        all_results.append(f"[{tool_name}]: {result}")
                    combined = "\n".join(all_results)
                    self.context_manager.add_message("assistant", "Menjalankan beberapa langkah...")
                    self.context_manager.add_message("system", combined)

            if self._current_plan and "steps" in self._current_plan:
                plan_msg = f"📋 Plan: {self._current_plan['goal']}\n"
                for i, step in enumerate(self._current_plan['steps'], 1):
                    plan_msg += f"  {i}. {step}\n"
                self.context_manager.add_message("assistant", plan_msg)
                logger.info(f"Executing plan with {len(self._current_plan['steps'])} steps")

            self.state = AgentState.EXECUTING

            while self.iteration_count < self.max_iterations:
                self.iteration_count += 1
                logger.info(f"--- Iteration {self.iteration_count} ---")

                if self._current_plan and "steps" in self._current_plan:
                    if self._plan_step_index < len(self._current_plan["steps"]):
                        current_step_desc = self._current_plan["steps"][self._plan_step_index]
                        remaining = self._current_plan["steps"][self._plan_step_index + 1:]

                        task = self.planner.get_next_task()
                        if task:
                            self.planner.update_task_status(task.task_id, TaskStatus.IN_PROGRESS)

                        self.state = AgentState.THINKING
                        step_prompt = f"Execute this step from your plan:\nStep: {current_step_desc}\nGoal: {self._current_plan['goal']}\n\nRespond with the appropriate tool action as JSON."
                        self.context_manager.add_message("system", step_prompt)

                self.state = AgentState.THINKING
                context = self.context_manager.get_context_window()
                llm_input = self._build_llm_prompt(context)

                logger.info("Sending to LLM...")
                raw_response = await self.llm.chat(llm_input)
                logger.info(f"LLM response received ({len(raw_response)} chars)")

                action = self._parse_llm_response(raw_response, user_input)

                if action["type"] == "respond" and self.iteration_count == 1 and not hasattr(self, '_retry_done'):
                    intent = detect_intent(user_input)
                    if intent and intent.get("type") == "use_tool":
                        logger.info(f"JSON parse yielded 'respond' but intent says tool needed. Retrying with correction prompt...")
                        retry_prompt = (
                            f"Your previous response was plain text, but the user's request requires a tool action.\n"
                            f"User request: {user_input}\n"
                            f"You MUST respond with ONLY a valid JSON object.\n"
                            f"The correct tool is likely: {intent.get('tool', 'unknown')}\n"
                            f"Example: {{\"action\":\"use_tool\",\"tool\":\"{intent.get('tool', 'shell_tool')}\",\"params\":{{...}}}}\n"
                            f"Respond with ONLY the JSON. No other text."
                        )
                        retry_response = await self.llm.chat(retry_prompt)
                        retry_action = self._parse_llm_response(retry_response, user_input)
                        if retry_action["type"] != "respond":
                            action = retry_action
                            logger.info(f"Retry succeeded: got action type '{action['type']}'")
                        else:
                            action = intent
                            logger.info(f"Retry still plain text, using intent detection directly")
                        self._retry_done = True

                if action["type"] == "plan":
                    goal = action.get("goal", user_input)
                    steps = action.get("steps", [])
                    if steps and not self._current_plan:
                        self.planner.create_plan(goal, steps)
                        self._current_plan = {
                            "goal": goal,
                            "steps": steps,
                            "results": [],
                            "status": "in_progress",
                        }
                        self._plan_step_index = 0
                        plan_msg = f"📋 Plan: {goal}\n"
                        for i, step in enumerate(steps, 1):
                            plan_msg += f"  {i}. {step}\n"
                        self.context_manager.add_message("assistant", plan_msg)
                        self._log_step("plan_created", {"goal": goal, "steps": steps})
                    continue

                elif action["type"] == "think":
                    thought = action.get("thought", "")
                    logger.info(f"LLM thinking: {thought[:200]}")
                    self.context_manager.add_message("assistant", f"💭 {thought}")
                    self._log_step("think", {"thought": thought[:500]})
                    continue

                elif action["type"] == "respond":
                    response = action["message"]
                    self.context_manager.add_message("assistant", response)
                    self.state = AgentState.COMPLETED
                    self._save_to_knowledge(user_input, response)
                    duration_total = int((time.time() - start_time) * 1000)
                    self.meta_learner.record_execution(
                        user_input, self._current_tools_used, True,
                        duration_total, self.iteration_count
                    )
                    if self._current_plan:
                        self._current_plan["status"] = "completed"
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

                    if self._current_plan and "steps" in self._current_plan:
                        self._current_plan["results"].append({
                            "step": self._plan_step_index,
                            "tool": tool_name,
                            "result": result[:1000],
                        })

                        task = None
                        for t in self.planner.tasks:
                            if t.status == TaskStatus.IN_PROGRESS:
                                task = t
                                break
                        if task:
                            task.tools_used.append(tool_name)
                            self.planner.update_task_status(task.task_id, TaskStatus.COMPLETED, result[:500])

                        self._plan_step_index += 1
                        remaining = self._current_plan["steps"][self._plan_step_index:]

                        reflection = await self._reflect_on_result(
                            goal=self._current_plan["goal"],
                            completed_step=self._current_plan["steps"][self._plan_step_index - 1],
                            result=result,
                            remaining_steps=remaining,
                        )

                        if reflection["type"] == "respond":
                            response = reflection["message"]
                            self.context_manager.add_message("assistant", response)
                            self.state = AgentState.COMPLETED
                            self._current_plan["status"] = "completed"
                            self._save_to_knowledge(user_input, response)
                            duration_total = int((time.time() - start_time) * 1000)
                            self.meta_learner.record_execution(
                                user_input, self._current_tools_used, True,
                                duration_total, self.iteration_count
                            )
                            return response
                        elif reflection["type"] == "think":
                            thought = reflection.get("thought", "")
                            self.context_manager.add_message("assistant", f"💭 {thought}")
                            self._log_step("reflection_think", {"thought": thought[:500]})
                        elif reflection["type"] == "use_tool":
                            self.context_manager.add_message("system",
                                f"[Reflection decided next action: {reflection.get('tool', 'unknown')}]")

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

            self.state = AgentState.SYNTHESIZING
            final = await self._generate_final_response(user_input)
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

    def _fix_json_string(self, raw: str) -> str:
        fixed = raw.strip()

        fixed = re.sub(r'```json\s*', '', fixed)
        fixed = re.sub(r'```\s*$', '', fixed)
        fixed = re.sub(r'^```\s*', '', fixed)

        fixed = re.sub(r',\s*}', '}', fixed)
        fixed = re.sub(r',\s*]', ']', fixed)

        fixed = re.sub(r'//[^\n]*', '', fixed)

        fixed = re.sub(r"(?<=[{,:\[]\s*)(\b(?:action|tool|params|type|command|query|url|path|operation|content|message|thought|goal|steps|name|action|prompt|width|height|format|selector|value|script|runtime|code|interval|framework|output_dir|cron_expression|callback|description|capabilities|old_text|new_text|dest|pattern|directory|start_line|end_line|direction|amount|full_page|dev|manager|packages|project_dir|slides|author|theme|layout|delay_seconds)\b)(?=\s*:)", r'"\1"', fixed)

        fixed = re.sub(r"(?<=:\s*)'([^']*)'", r'"\1"', fixed)

        if fixed.startswith('{') and not fixed.endswith('}'):
            open_braces = fixed.count('{')
            close_braces = fixed.count('}')
            if open_braces > close_braces:
                fixed += '}' * (open_braces - close_braces)

        if fixed.count('[') > fixed.count(']'):
            fixed += ']' * (fixed.count('[') - fixed.count(']'))

        return fixed

    def _extract_tool_from_text(self, raw: str, user_input: str = "") -> dict | None:
        VALID_TOOLS = {"shell_tool", "file_tool", "browser_tool", "search_tool", "generate_tool",
                       "slides_tool", "webdev_tool", "schedule_tool", "message_tool", "skill_manager"}

        tool_pattern = re.search(
            r'(?:menggunakan|gunakan|use|call|jalankan|run|execute|using)\s+(shell_tool|file_tool|browser_tool|search_tool|generate_tool|slides_tool|webdev_tool|schedule_tool|message_tool|skill_manager)',
            raw, re.IGNORECASE
        )
        if tool_pattern:
            tool_name = tool_pattern.group(1).lower()
            if tool_name in VALID_TOOLS:
                if user_input:
                    intent = detect_intent(user_input)
                    if intent and intent.get("tool") == tool_name:
                        return intent
                return {"type": "use_tool", "tool": tool_name, "params": {}}

        command_match = re.search(r'(?:run|execute|jalankan)\s+(?:command\s+)?[`"\']([^`"\']+)[`"\']', raw, re.IGNORECASE)
        if command_match:
            return {"type": "use_tool", "tool": "shell_tool", "params": {"command": command_match.group(1)}}

        url_match = re.search(r'(?:navigate|open|buka|go to)\s+(?:to\s+)?(https?://[^\s"\'<>]+)', raw, re.IGNORECASE)
        if url_match:
            return {"type": "use_tool", "tool": "browser_tool", "params": {"action": "navigate", "url": url_match.group(1)}}

        search_match = re.search(r'(?:search|cari|look up)\s+(?:for\s+)?["\']([^"\']+)["\']', raw, re.IGNORECASE)
        if search_match:
            return {"type": "use_tool", "tool": "search_tool", "params": {"query": search_match.group(1)}}

        file_read_match = re.search(r'(?:read|baca)\s+(?:file\s+)?["\']?([^\s"\']+\.\w+)["\']?', raw, re.IGNORECASE)
        if file_read_match:
            return {"type": "use_tool", "tool": "file_tool", "params": {"operation": "read", "path": file_read_match.group(1)}}

        return None

    def _parse_llm_response(self, raw: str, user_input: str = "") -> dict:
        raw = raw.strip()

        json_candidates = []

        if "```json" in raw:
            for match in re.finditer(r'```json\s*(.*?)```', raw, re.DOTALL):
                candidate = match.group(1).strip()
                if candidate:
                    json_candidates.append(candidate)

        if "```" in raw and not json_candidates:
            for match in re.finditer(r'```\s*(.*?)```', raw, re.DOTALL):
                candidate = match.group(1).strip()
                if candidate.startswith("{"):
                    json_candidates.append(candidate)

        brace_positions = []
        i = 0
        while i < len(raw):
            if raw[i] == '{':
                brace_count = 0
                start = i
                for j in range(i, len(raw)):
                    if raw[j] == '{':
                        brace_count += 1
                    elif raw[j] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            candidate = raw[start:j + 1]
                            if candidate not in json_candidates:
                                json_candidates.append(candidate)
                            brace_positions.append((start, j + 1))
                            i = j + 1
                            break
                else:
                    i += 1
            else:
                i += 1

        all_candidates = []
        for json_str in json_candidates:
            all_candidates.append(json_str)
            fixed = self._fix_json_string(json_str)
            if fixed != json_str:
                all_candidates.append(fixed)

        if not all_candidates:
            fixed_raw = self._fix_json_string(raw)
            if fixed_raw.startswith('{'):
                all_candidates.append(fixed_raw)

        for json_str in all_candidates:
            try:
                parsed = json.loads(json_str)
                if not isinstance(parsed, dict):
                    continue
                action = parsed.get("action", "")

                if action == "plan":
                    return {
                        "type": "plan",
                        "goal": parsed.get("goal", ""),
                        "steps": parsed.get("steps", []),
                    }
                elif action == "think":
                    return {
                        "type": "think",
                        "thought": parsed.get("thought", ""),
                    }
                elif action == "use_tool":
                    tool = parsed.get("tool", "")
                    if tool:
                        return {
                            "type": "use_tool",
                            "tool": tool,
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
                    steps = parsed["steps"]
                    if steps and isinstance(steps[0], dict) and "tool" in steps[0]:
                        return {
                            "type": "multi_step",
                            "steps": steps,
                        }
                    elif steps and isinstance(steps[0], str):
                        return {
                            "type": "plan",
                            "goal": parsed.get("goal", ""),
                            "steps": steps,
                        }
                elif "goal" in parsed and "steps" in parsed:
                    return {
                        "type": "plan",
                        "goal": parsed["goal"],
                        "steps": parsed.get("steps", []),
                    }
                elif "thought" in parsed:
                    return {
                        "type": "think",
                        "thought": parsed["thought"],
                    }
                elif "message" in parsed:
                    return {
                        "type": "respond",
                        "message": parsed["message"],
                    }
                elif "command" in parsed:
                    return {
                        "type": "use_tool",
                        "tool": "shell_tool",
                        "params": parsed,
                    }
                elif "query" in parsed:
                    return {
                        "type": "use_tool",
                        "tool": "search_tool",
                        "params": parsed,
                    }
                elif "url" in parsed:
                    return {
                        "type": "use_tool",
                        "tool": "browser_tool",
                        "params": {"action": "navigate", "url": parsed["url"]},
                    }
                elif "operation" in parsed and "path" in parsed:
                    return {
                        "type": "use_tool",
                        "tool": "file_tool",
                        "params": parsed,
                    }
            except (json.JSONDecodeError, ValueError):
                continue

        text_tool = self._extract_tool_from_text(raw, user_input)
        if text_tool:
            logger.info(f"Extracted tool from text: {text_tool.get('tool', text_tool.get('type'))}")
            return text_tool

        refusal_patterns = [
            r"(?:saya|aku)\s+(?:tidak\s+)?(?:bisa|dapat|mampu)\s+(?:tidak\s+)?(?:langsung\s+)?(?:membuka|menjalankan|mengeksekusi|mengakses)",
            r"(?:tidak\s+)?(?:memiliki|punya)\s+(?:akses|kemampuan)",
            r"(?:sebagai\s+)?(?:AI|model\s+bahasa|asisten\s+virtual)",
            r"(?:saya\s+)?(?:hanya\s+)?(?:bisa\s+)?(?:menjelaskan|mendeskripsikan|memberikan\s+gambaran)",
            r"(?:i\s+)?(?:can'?t|cannot|unable\s+to)\s+(?:directly|actually)?\s*(?:open|run|execute|access|browse)",
            r"(?:i\s+)?(?:don'?t|do\s+not)\s+have\s+(?:access|ability|capability)",
            r"(?:as\s+an?\s+)?(?:AI|language\s+model|virtual\s+assistant)",
        ]
        is_refusal = any(re.search(p, raw, re.IGNORECASE) for p in refusal_patterns)

        if is_refusal and user_input:
            intent = detect_intent(user_input)
            if intent:
                logger.info(f"LLM refused but intent detected, forcing tool: {intent}")
                return intent

        if user_input and not is_refusal:
            intent = detect_intent(user_input)
            if intent:
                logger.info(f"Fallback intent detection from user_input: {intent['type']}")
                return intent

        return {"type": "respond", "message": raw}

    async def _generate_final_response(self, user_input: str = "") -> str:
        self.state = AgentState.SYNTHESIZING
        logger.info("Phase 4 - SYNTHESIS: Generating final comprehensive response...")

        execution_summary = ""
        for entry in self.execution_log:
            phase = entry.get("phase", "unknown")
            data = entry.get("data", {})
            if phase == "plan_created":
                execution_summary += f"Plan: {data.get('goal', '')}\n"
                for i, step in enumerate(data.get('steps', []), 1):
                    execution_summary += f"  Step {i}: {step}\n"
            elif phase == "execute":
                execution_summary += f"Executed {data.get('tool', '')}: {str(data.get('result', ''))[:300]}\n"
            elif phase == "think":
                execution_summary += f"Analysis: {data.get('thought', '')[:200]}\n"

        if self.planner.tasks:
            execution_summary += "\n" + self.planner.get_plan_summary()

        if user_input and execution_summary:
            prompt = SYNTHESIS_PROMPT.format(
                user_input=user_input,
                execution_summary=execution_summary,
            )
            return await self.llm.chat(prompt)

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
