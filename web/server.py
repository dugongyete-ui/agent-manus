import asyncio
from contextlib import asynccontextmanager
import json
import logging
import os
import subprocess
import sys
import time
from typing import Optional
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def _ensure_deps():
    required = {
        "PIL": "Pillow", "PyPDF2": "PyPDF2", "mutagen": "mutagen",
        "psycopg2": "psycopg2-binary",
    }
    missing = []
    for mod, pkg in required.items():
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"Auto-installing: {', '.join(missing)}")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", "--no-warn-script-location"] + missing,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

_ensure_deps()

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import yaml

from web.database import (
    init_database, create_session, get_sessions, get_session,
    delete_session, update_session_title, add_message, get_messages,
    build_context_string, log_tool_execution, get_tool_executions
)
from agent_core.agent_loop import AgentLoop, SYSTEM_PROMPT, detect_intent
from agent_core.llm_client import LLMClient, AVAILABLE_MODELS, MODEL_CATEGORIES
from agent_core.knowledge_base import KnowledgeBase
from agent_core.context_manager import ContextManager
from agent_core.rlhf_engine import RLHFEngine
from agent_core.meta_learner import MetaLearner
from agent_core.security_manager import SecurityManager
from agent_core.access_control import AccessControl
from agent_core.data_privacy import DataPrivacyManager
from mcp.server import MCPServer
from mcp.registry import create_default_registry
from mcp.protocol import MCPProviderConfig, MCPProviderType
from tools.shell_tool import ShellTool
from tools.file_tool import FileTool
from tools.search_tool import SearchTool
from tools.message_tool import MessageTool
from tools.browser_tool import BrowserTool
from tools.webdev_tool import WebDevTool
from tools.generate_tool import GenerateTool
from tools.slides_tool import SlidesTool
from tools.schedule_tool import ScheduleTool
from tools.skill_manager import SkillManager
from tools.spreadsheet_tool import SpreadsheetTool
from tools.playbook_manager import PlaybookManager
from sandbox_env.vm_manager import VMManager, IsolationLevel
from sandbox_env.shell_session import ShellSessionManager
from monitoring.monitor import monitor as system_monitor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app):
    init_database()
    get_agent()
    system_monitor.health.register_check("database", lambda: init_database() or "OK", critical=True)
    system_monitor.health.register_check("agent", lambda: "OK" if agent_loop else "not initialized")
    logger.info("Manus Agent Web Server started")
    yield

app = FastAPI(title="Manus Agent", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

web_dir = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(web_dir, "static")), name="static")

generated_dir = os.path.join(os.path.dirname(web_dir), "data", "generated")
os.makedirs(generated_dir, exist_ok=True)
app.mount("/generated", StaticFiles(directory=generated_dir), name="generated")

llm_client = LLMClient()
knowledge_base = KnowledgeBase()
rlhf_engine = RLHFEngine()
meta_learner = MetaLearner()
security_manager = SecurityManager()
access_control = AccessControl()
data_privacy = DataPrivacyManager()
mcp_server = MCPServer()

agent_loop = None
def get_agent():
    global agent_loop
    if agent_loop is None:
        config_path = os.path.join(os.path.dirname(web_dir), "config", "settings.yaml")
        try:
            with open(config_path) as f:
                config = yaml.safe_load(f)
        except FileNotFoundError:
            config = {"agent": {"max_iterations": 10}, "context": {"max_tokens": 128000}}
        agent_loop = AgentLoop(config)
        agent_loop.register_tool("shell_tool", ShellTool())
        agent_loop.register_tool("file_tool", FileTool())
        agent_loop.register_tool("search_tool", SearchTool())
        agent_loop.register_tool("message_tool", MessageTool())
        agent_loop.register_tool("browser_tool", BrowserTool())
        agent_loop.register_tool("webdev_tool", WebDevTool())
        agent_loop.register_tool("generate_tool", GenerateTool())
        agent_loop.register_tool("slides_tool", SlidesTool())
        schedule_tool = ScheduleTool()
        skill_manager = SkillManager()
        spreadsheet_tool = SpreadsheetTool()
        playbook_manager = PlaybookManager()
        agent_loop.register_tool("schedule_tool", schedule_tool)
        agent_loop.register_tool("skill_manager", skill_manager)
        agent_loop.register_tool("spreadsheet_tool", spreadsheet_tool)
        agent_loop.register_tool("playbook_manager", playbook_manager)

        message_tool = agent_loop._tool_instances.get("message_tool")
        if message_tool:
            schedule_tool.set_notification_callback(
                lambda title, body, level="info": message_tool.notify(title, body, level)
            )

    return agent_loop

vm_manager = VMManager()
shell_session_manager = ShellSessionManager()


@app.get("/api/health")
async def api_health():
    return {"status": "healthy", "agent_state": agent_loop.state if agent_loop else "not_initialized"}


@app.get("/api/files/list")
async def api_list_files():
    """List all generated files available for download."""
    generated_dir = os.path.join(os.path.dirname(web_dir), "data", "generated")
    workspace_dir = os.path.join(os.path.dirname(web_dir), "user_workspace")
    files = []
    for directory in [generated_dir, workspace_dir]:
        if os.path.exists(directory):
            for fname in os.listdir(directory):
                fpath = os.path.join(directory, fname)
                if os.path.isfile(fpath):
                    files.append({
                        "filename": fname,
                        "path": fpath,
                        "size": os.path.getsize(fpath),
                        "modified": os.path.getmtime(fpath),
                        "download_url": f"/api/files/download/{fname}",
                    })
    files.sort(key=lambda x: x["modified"], reverse=True)
    return {"files": files}


@app.get("/api/files/download/{filename}")
async def api_download_file(filename: str):
    """Download a generated file."""
    import mimetypes
    generated_dir = os.path.join(os.path.dirname(web_dir), "data", "generated")
    workspace_dir = os.path.join(os.path.dirname(web_dir), "user_workspace")
    
    for directory in [generated_dir, workspace_dir]:
        fpath = os.path.join(directory, filename)
        if os.path.isfile(fpath):
            media_type = mimetypes.guess_type(fpath)[0] or "application/octet-stream"
            return FileResponse(
                path=fpath,
                filename=filename,
                media_type=media_type,
                headers={"Cache-Control": "no-cache"}
            )
    raise HTTPException(status_code=404, detail="File not found")


@app.get("/api/files/download-zip")
async def api_download_zip(files: str = ""):
    """Download multiple files as a ZIP archive."""
    import zipfile
    import tempfile
    
    generated_dir = os.path.join(os.path.dirname(web_dir), "data", "generated")
    workspace_dir = os.path.join(os.path.dirname(web_dir), "user_workspace")
    
    requested = [f.strip() for f in files.split(",") if f.strip()] if files else []
    
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    tmp_path = tmp.name
    
    with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for directory in [generated_dir, workspace_dir]:
            if not os.path.exists(directory):
                continue
            for fname in os.listdir(directory):
                fpath = os.path.join(directory, fname)
                if os.path.isfile(fpath):
                    if not requested or fname in requested:
                        zf.write(fpath, fname)
    
    return FileResponse(
        path=tmp_path,
        filename="manus_files.zip",
        media_type="application/zip",
        headers={"Cache-Control": "no-cache"}
    )


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = os.path.join(web_dir, "templates", "index.html")
    with open(html_path, "r") as f:
        return HTMLResponse(content=f.read(), headers={"Cache-Control": "no-cache"})


@app.get("/api/sessions")
async def api_get_sessions():
    sessions = get_sessions()
    for s in sessions:
        for k, v in s.items():
            if hasattr(v, 'isoformat'):
                s[k] = v.isoformat()
    return {"sessions": sessions}


@app.post("/api/sessions")
async def api_create_session(request: Request):
    body = await request.json()
    session_id = str(uuid.uuid4())[:8]
    title = body.get("title", "New Chat")
    session = create_session(session_id, title)
    for k, v in session.items():
        if hasattr(v, 'isoformat'):
            session[k] = v.isoformat()
    return {"session": session}


@app.delete("/api/sessions/{session_id}")
async def api_delete_session(session_id: str):
    if delete_session(session_id):
        return {"ok": True}
    raise HTTPException(status_code=404, detail="Session not found")


@app.patch("/api/sessions/{session_id}")
async def api_update_session(session_id: str, request: Request):
    body = await request.json()
    title = body.get("title", "")
    if title:
        update_session_title(session_id, title)
    return {"ok": True}


@app.get("/api/sessions/{session_id}/messages")
async def api_get_messages(session_id: str):
    messages = get_messages(session_id)
    for m in messages:
        for k, v in m.items():
            if hasattr(v, 'isoformat'):
                m[k] = v.isoformat()
    return {"messages": messages}


@app.post("/api/sessions/{session_id}/chat")
async def api_chat(session_id: str, request: Request):
    body = await request.json()
    user_message = body.get("message", "").strip()
    request_model = body.get("model", None)
    if not user_message:
        raise HTTPException(status_code=400, detail="Message is required")

    agent = get_agent()
    if request_model:
        agent.llm.set_model(request_model)

    session = get_session(session_id)
    if not session:
        create_session(session_id, user_message[:50])

    add_message(session_id, "user", user_message)

    history_context = build_context_string(session_id)
    full_prompt = f"[CONVERSATION HISTORY]\n{history_context}\n[END HISTORY]\n\nUser: {user_message}"

    agent = get_agent()
    tool_executions = []

    try:
        agent.context_manager.clear()
        agent.context_manager.set_system_prompt(SYSTEM_PROMPT)
        agent.context_manager.add_message("user", full_prompt)
        agent.iteration_count = 0
        agent.execution_log.clear()

        max_iterations = agent.max_iterations
        final_response = ""
        raw_response = ""

        intent_bypass = detect_intent(user_message)
        if intent_bypass:
            logger.info(f"Intent bypass aktif: {intent_bypass['type']} -> {intent_bypass.get('tool', 'multi')}")
            if intent_bypass["type"] == "use_tool":
                tool_name = intent_bypass["tool"]
                params = intent_bypass.get("params", {})
                start_time = time.time()
                result = await agent._execute_tool(tool_name, params)
                duration_ms = int((time.time() - start_time) * 1000)
                tool_exec = {
                    "tool": tool_name, "params": params,
                    "result": result[:2000], "duration_ms": duration_ms, "status": "success"
                }
                tool_executions.append(tool_exec)
                log_tool_execution(session_id, tool_name, params, result[:2000], "success", duration_ms)
                observation = f"[Hasil {tool_name}]:\n{result}"
                agent.context_manager.add_message("assistant", f"Menggunakan {tool_name}...")
                agent.context_manager.add_message("system", observation)
                context = agent.context_manager.get_context_window()
                summary_prompt = agent._build_llm_prompt(context)
                summary_prompt += "\n\n[System]: Berikan ringkasan singkat hasil tool di atas untuk user. Respons sebagai teks biasa."
                final_response = await agent.llm.chat(summary_prompt)
                if not final_response.strip():
                    final_response = f"Tool {tool_name} berhasil dijalankan.\n\nHasil:\n{result[:3000]}"
            elif intent_bypass["type"] == "multi_step":
                for step in intent_bypass.get("steps", []):
                    tool_name = step.get("tool", "")
                    params = step.get("params", {})
                    start_time = time.time()
                    result = await agent._execute_tool(tool_name, params)
                    duration_ms = int((time.time() - start_time) * 1000)
                    tool_exec = {
                        "tool": tool_name, "params": params,
                        "result": result[:2000], "duration_ms": duration_ms, "status": "success"
                    }
                    tool_executions.append(tool_exec)
                    log_tool_execution(session_id, tool_name, params, result[:2000], "success", duration_ms)
                all_results = [f"[{te['tool']}]: {te['result']}" for te in tool_executions]
                agent.context_manager.add_message("assistant", "Menjalankan beberapa langkah...")
                agent.context_manager.add_message("system", "\n".join(all_results))
                context = agent.context_manager.get_context_window()
                summary_prompt = agent._build_llm_prompt(context)
                summary_prompt += "\n\n[System]: Berikan ringkasan singkat semua hasil tool di atas. Respons sebagai teks biasa."
                final_response = await agent.llm.chat(summary_prompt)
                if not final_response.strip():
                    final_response = "Semua tools berhasil dijalankan.\n\n" + "\n".join(all_results[:5])
        else:
            for iteration in range(max_iterations):
                agent.iteration_count = iteration + 1
                context = agent.context_manager.get_context_window()
                llm_input = agent._build_llm_prompt(context)

                raw_response = await agent.llm.chat(llm_input)
                action = agent._parse_llm_response(raw_response, user_input=user_message)

                if action["type"] == "respond":
                    final_response = action["message"]
                    break

                elif action["type"] == "use_tool":
                    tool_name = action["tool"]
                    params = action.get("params", {})
                    start_time = time.time()

                    result = await agent._execute_tool(tool_name, params)
                    duration_ms = int((time.time() - start_time) * 1000)

                    tool_exec = {
                        "tool": tool_name,
                        "params": params,
                        "result": result[:2000],
                        "duration_ms": duration_ms,
                        "status": "success"
                    }
                    tool_executions.append(tool_exec)

                    log_tool_execution(session_id, tool_name, params, result[:2000], "success", duration_ms)

                    observation = f"[Hasil {tool_name}]:\n{result}"
                    agent.context_manager.add_message("assistant", f"Menggunakan {tool_name}...")
                    agent.context_manager.add_message("system", observation)

                elif action["type"] == "multi_step":
                    for step in action.get("steps", []):
                        tool_name = step.get("tool", "")
                        params = step.get("params", {})
                        start_time = time.time()

                        result = await agent._execute_tool(tool_name, params)
                        duration_ms = int((time.time() - start_time) * 1000)

                        tool_exec = {
                            "tool": tool_name,
                            "params": params,
                            "result": result[:2000],
                            "duration_ms": duration_ms,
                            "status": "success"
                        }
                        tool_executions.append(tool_exec)
                        log_tool_execution(session_id, tool_name, params, result[:2000], "success", duration_ms)

                    all_results = [f"[{te['tool']}]: {te['result']}" for te in tool_executions[-len(action.get('steps', [])):]]
                    agent.context_manager.add_message("assistant", "Menjalankan beberapa langkah...")
                    agent.context_manager.add_message("system", "\n".join(all_results))

                elif action["type"] == "error":
                    final_response = action.get("message", raw_response)
                    break
            else:
                context = agent.context_manager.get_context_window()
                prompt = agent._build_llm_prompt(context)
                prompt += "\n\n[System]: Berikan ringkasan akhir. Respons sebagai teks biasa."
                final_response = await agent.llm.chat(prompt)

        if not final_response:
            final_response = raw_response

        msg = add_message(session_id, "assistant", final_response, {"tool_executions": tool_executions})

        if len(get_messages(session_id)) <= 2:
            title = user_message[:50] + ("..." if len(user_message) > 50 else "")
            update_session_title(session_id, title)

        for m_key in msg:
            if hasattr(msg[m_key], 'isoformat'):
                msg[m_key] = msg[m_key].isoformat()

        return {
            "response": final_response,
            "message": msg,
            "tool_executions": tool_executions,
            "iterations": agent.iteration_count
        }

    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        error_msg = f"Terjadi kesalahan: {str(e)}"
        add_message(session_id, "assistant", error_msg)
        return {"response": error_msg, "message": {}, "tool_executions": tool_executions, "iterations": 0}


@app.post("/api/sessions/{session_id}/chat/stream")
async def api_chat_stream(session_id: str, request: Request):
    body = await request.json()
    user_message = body.get("message", "").strip()
    request_model = body.get("model", None)
    if not user_message:
        raise HTTPException(status_code=400, detail="Message is required")

    agent_ref = get_agent()
    if request_model:
        agent_ref.llm.set_model(request_model)

    session = get_session(session_id)
    if not session:
        create_session(session_id, user_message[:50])

    add_message(session_id, "user", user_message)
    history_context = build_context_string(session_id)
    full_prompt = f"[CONVERSATION HISTORY]\n{history_context}\n[END HISTORY]\n\nUser: {user_message}"

    async def generate():
        agent = get_agent()
        tool_executions = []
        final_response = ""
        raw_response = ""
        current_goal = user_message
        current_plan_steps = []
        done_sent = False

        try:
            agent.context_manager.clear()
            agent.context_manager.set_system_prompt(SYSTEM_PROMPT)
            agent.context_manager.add_message("user", full_prompt)
            agent.iteration_count = 0
            agent.execution_log.clear()

            max_iterations = agent.max_iterations

            yield f"data: {json.dumps({'type': 'phase', 'phase': 'planning', 'content': 'Analyzing request...'})}\n\n"
            yield f"data: {json.dumps({'type': 'planning', 'content': 'Creating execution plan...'})}\n\n"

            plan_result = await agent._create_initial_plan(user_message)

            if plan_result and "direct_response" in plan_result:
                final_response = plan_result["direct_response"]
                for char_idx in range(0, len(final_response), 3):
                    text_chunk = final_response[char_idx:char_idx+3]
                    yield f"data: {json.dumps({'type': 'chunk', 'content': text_chunk})}\n\n"
                    await asyncio.sleep(0.01)

            elif plan_result and "immediate_action" in plan_result:
                action = plan_result["immediate_action"]
                yield f"data: {json.dumps({'type': 'phase', 'phase': 'executing', 'content': 'Executing immediate action...'})}\n\n"

                if action["type"] == "use_tool":
                    tool_name = action["tool"]
                    params = action.get("params", {})
                    start_time = time.time()
                    yield f"data: {json.dumps({'type': 'tool_start', 'tool': tool_name, 'params': params})}\n\n"
                    try:
                        result = await agent._execute_tool(tool_name, params)
                        duration_ms = int((time.time() - start_time) * 1000)
                        tool_exec = {
                            "tool": tool_name, "params": params,
                            "result": result[:2000], "duration_ms": duration_ms, "status": "success"
                        }
                        tool_executions.append(tool_exec)
                        log_tool_execution(session_id, tool_name, params, result[:2000], "success", duration_ms)
                        yield f"data: {json.dumps({'type': 'tool_result', 'tool': tool_name, 'result': result[:2000], 'duration_ms': duration_ms, 'status': 'success'})}\n\n"
                        agent.context_manager.add_message("assistant", f"Menggunakan {tool_name}...")
                        agent.context_manager.add_message("system", f"[Hasil {tool_name}]:\n{result}")
                    except Exception as tool_err:
                        duration_ms = int((time.time() - start_time) * 1000)
                        error_result = f"Error executing {tool_name}: {str(tool_err)}"
                        tool_exec = {
                            "tool": tool_name, "params": params,
                            "result": error_result, "duration_ms": duration_ms, "status": "error"
                        }
                        tool_executions.append(tool_exec)
                        log_tool_execution(session_id, tool_name, params, error_result, "error", duration_ms)
                        yield f"data: {json.dumps({'type': 'tool_result', 'tool': tool_name, 'result': error_result, 'duration_ms': duration_ms, 'status': 'error'})}\n\n"
                        agent.context_manager.add_message("system", f"[Error {tool_name}]: {error_result}")

                elif action["type"] == "multi_step":
                    for step in action.get("steps", []):
                        tool_name = step.get("tool", "")
                        params = step.get("params", {})
                        start_time = time.time()
                        yield f"data: {json.dumps({'type': 'tool_start', 'tool': tool_name, 'params': params})}\n\n"
                        try:
                            result = await agent._execute_tool(tool_name, params)
                            duration_ms = int((time.time() - start_time) * 1000)
                            tool_exec = {
                                "tool": tool_name, "params": params,
                                "result": result[:2000], "duration_ms": duration_ms, "status": "success"
                            }
                            tool_executions.append(tool_exec)
                            log_tool_execution(session_id, tool_name, params, result[:2000], "success", duration_ms)
                            yield f"data: {json.dumps({'type': 'tool_result', 'tool': tool_name, 'result': result[:2000], 'duration_ms': duration_ms, 'status': 'success'})}\n\n"
                        except Exception as tool_err:
                            duration_ms = int((time.time() - start_time) * 1000)
                            error_result = f"Error executing {tool_name}: {str(tool_err)}"
                            tool_exec = {
                                "tool": tool_name, "params": params,
                                "result": error_result, "duration_ms": duration_ms, "status": "error"
                            }
                            tool_executions.append(tool_exec)
                            log_tool_execution(session_id, tool_name, params, error_result, "error", duration_ms)
                            yield f"data: {json.dumps({'type': 'tool_result', 'tool': tool_name, 'result': error_result, 'duration_ms': duration_ms, 'status': 'error'})}\n\n"
                    all_results = [f"[{te['tool']}]: {te['result']}" for te in tool_executions]
                    agent.context_manager.add_message("assistant", "Menjalankan beberapa langkah...")
                    agent.context_manager.add_message("system", "\n".join(all_results))

                yield f"data: {json.dumps({'type': 'phase', 'phase': 'synthesizing', 'content': 'Creating final response...'})}\n\n"
                context = agent.context_manager.get_context_window()
                summary_prompt = agent._build_llm_prompt(context)
                summary_prompt += "\n\n[System]: Berikan ringkasan singkat hasil tool. Respons sebagai teks biasa."
                async for chunk in agent.llm.chat_stream(summary_prompt):
                    final_response += chunk
                    yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
                if not final_response.strip():
                    fallback_text = "Tool berhasil dijalankan.\n\n" + "\n".join([f"[{te['tool']}]: {te['result'][:500]}" for te in tool_executions])
                    final_response = fallback_text
                    for ci in range(0, len(fallback_text), 3):
                        yield f"data: {json.dumps({'type': 'chunk', 'content': fallback_text[ci:ci+3]})}\n\n"

            else:
                if plan_result and "goal" in plan_result and "steps" in plan_result:
                    current_goal = plan_result["goal"]
                    current_plan_steps = list(plan_result["steps"])
                    yield f"data: {json.dumps({'type': 'plan', 'goal': current_goal, 'steps': current_plan_steps})}\n\n"
                    plan_msg = f"Plan: {current_goal}\n"
                    for i, step in enumerate(current_plan_steps, 1):
                        plan_msg += f"  {i}. {step}\n"
                    agent.context_manager.add_message("assistant", plan_msg)

                yield f"data: {json.dumps({'type': 'phase', 'phase': 'executing', 'content': 'Starting execution...'})}\n\n"

                for iteration in range(max_iterations):
                    agent.iteration_count = iteration + 1

                    yield f"data: {json.dumps({'type': 'phase', 'phase': 'executing', 'content': f'Running step {iteration + 1}...'})}\n\n"

                    context = agent.context_manager.get_context_window()
                    llm_input = agent._build_llm_prompt(context)

                    raw_response = ""
                    raw_chunks = []
                    async for chunk in agent.llm.chat_stream(llm_input):
                        raw_chunks.append(chunk)
                    raw_response = "".join(raw_chunks)

                    action = agent._parse_llm_response(raw_response, user_input=user_message)

                    if action["type"] == "plan":
                        plan_goal = action.get("goal", current_goal)
                        plan_steps = action.get("steps", [])
                        if plan_steps:
                            current_goal = plan_goal
                            current_plan_steps = list(plan_steps)
                            yield f"data: {json.dumps({'type': 'plan', 'goal': current_goal, 'steps': current_plan_steps})}\n\n"
                            plan_msg = f"Plan: {current_goal}\n"
                            for i, step in enumerate(current_plan_steps, 1):
                                plan_msg += f"  {i}. {step}\n"
                            agent.context_manager.add_message("assistant", plan_msg)
                        continue

                    elif action["type"] == "think":
                        thought = action.get("thought", "")
                        yield f"data: {json.dumps({'type': 'thinking', 'content': thought})}\n\n"
                        agent.context_manager.add_message("assistant", f"Thinking: {thought}")
                        continue

                    elif action["type"] == "respond":
                        final_response = action["message"]
                        for char_idx in range(0, len(final_response), 3):
                            text_chunk = final_response[char_idx:char_idx+3]
                            yield f"data: {json.dumps({'type': 'chunk', 'content': text_chunk})}\n\n"
                            await asyncio.sleep(0.01)
                        break

                    elif action["type"] == "use_tool":
                        tool_name = action["tool"]
                        params = action.get("params", {})
                        start_time = time.time()

                        yield f"data: {json.dumps({'type': 'tool_start', 'tool': tool_name, 'params': params})}\n\n"

                        try:
                            result = await agent._execute_tool(tool_name, params)
                            duration_ms = int((time.time() - start_time) * 1000)

                            tool_exec = {
                                "tool": tool_name,
                                "params": params,
                                "result": result[:2000],
                                "duration_ms": duration_ms,
                                "status": "success"
                            }
                            tool_executions.append(tool_exec)
                            log_tool_execution(session_id, tool_name, params, result[:2000], "success", duration_ms)

                            yield f"data: {json.dumps({'type': 'tool_result', 'tool': tool_name, 'result': result[:2000], 'duration_ms': duration_ms, 'status': 'success'})}\n\n"

                            observation = f"[Hasil {tool_name}]:\n{result}"
                            agent.context_manager.add_message("assistant", f"Menggunakan {tool_name}...")
                            agent.context_manager.add_message("system", observation)

                            yield f"data: {json.dumps({'type': 'phase', 'phase': 'reflecting', 'content': 'Analyzing results...'})}\n\n"

                            completed_step = f"Used {tool_name} with params {json.dumps(params)}"
                            remaining = current_plan_steps[iteration + 1:] if current_plan_steps else []
                            try:
                                reflection = await agent._reflect_on_result(current_goal, completed_step, result, remaining)
                                if reflection.get("type") == "think":
                                    thought = reflection.get("thought", "")
                                    yield f"data: {json.dumps({'type': 'thinking', 'content': thought})}\n\n"
                                    agent.context_manager.add_message("assistant", f"Reflection: {thought}")
                                elif reflection.get("type") == "respond":
                                    final_response = reflection.get("message", "")
                                    for char_idx in range(0, len(final_response), 3):
                                        text_chunk = final_response[char_idx:char_idx+3]
                                        yield f"data: {json.dumps({'type': 'chunk', 'content': text_chunk})}\n\n"
                                        await asyncio.sleep(0.01)
                                    break
                                elif reflection.get("type") == "use_tool":
                                    agent.context_manager.add_message("system", f"[Reflection]: Next action determined - use {reflection.get('tool', 'unknown')}")
                            except Exception as ref_err:
                                logger.warning(f"Reflection failed: {ref_err}")
                        except Exception as tool_err:
                            duration_ms = int((time.time() - start_time) * 1000)
                            error_result = f"Error executing {tool_name}: {str(tool_err)}"
                            tool_exec = {
                                "tool": tool_name,
                                "params": params,
                                "result": error_result,
                                "duration_ms": duration_ms,
                                "status": "error"
                            }
                            tool_executions.append(tool_exec)
                            log_tool_execution(session_id, tool_name, params, error_result, "error", duration_ms)
                            yield f"data: {json.dumps({'type': 'tool_result', 'tool': tool_name, 'result': error_result, 'duration_ms': duration_ms, 'status': 'error'})}\n\n"
                            agent.context_manager.add_message("system", f"[Error {tool_name}]: {error_result}")

                    elif action["type"] == "multi_step":
                        for step in action.get("steps", []):
                            tool_name = step.get("tool", "")
                            params = step.get("params", {})
                            start_time = time.time()

                            yield f"data: {json.dumps({'type': 'tool_start', 'tool': tool_name, 'params': params})}\n\n"

                            try:
                                result = await agent._execute_tool(tool_name, params)
                                duration_ms = int((time.time() - start_time) * 1000)

                                tool_exec = {
                                    "tool": tool_name,
                                    "params": params,
                                    "result": result[:2000],
                                    "duration_ms": duration_ms,
                                    "status": "success"
                                }
                                tool_executions.append(tool_exec)
                                log_tool_execution(session_id, tool_name, params, result[:2000], "success", duration_ms)

                                yield f"data: {json.dumps({'type': 'tool_result', 'tool': tool_name, 'result': result[:2000], 'duration_ms': duration_ms, 'status': 'success'})}\n\n"
                            except Exception as tool_err:
                                duration_ms = int((time.time() - start_time) * 1000)
                                error_result = f"Error executing {tool_name}: {str(tool_err)}"
                                tool_exec = {
                                    "tool": tool_name,
                                    "params": params,
                                    "result": error_result,
                                    "duration_ms": duration_ms,
                                    "status": "error"
                                }
                                tool_executions.append(tool_exec)
                                log_tool_execution(session_id, tool_name, params, error_result, "error", duration_ms)
                                yield f"data: {json.dumps({'type': 'tool_result', 'tool': tool_name, 'result': error_result, 'duration_ms': duration_ms, 'status': 'error'})}\n\n"

                        all_results = [f"[{te['tool']}]: {te['result']}" for te in tool_executions[-len(action.get('steps', [])):]]
                        agent.context_manager.add_message("assistant", "Menjalankan beberapa langkah...")
                        agent.context_manager.add_message("system", "\n".join(all_results))

                    elif action["type"] == "error":
                        final_response = action.get("message", raw_response)
                        yield f"data: {json.dumps({'type': 'chunk', 'content': final_response})}\n\n"
                        break
                else:
                    yield f"data: {json.dumps({'type': 'phase', 'phase': 'synthesizing', 'content': 'Creating final response...'})}\n\n"
                    context = agent.context_manager.get_context_window()
                    prompt = agent._build_llm_prompt(context)
                    prompt += "\n\n[System]: Berikan ringkasan akhir. Respons sebagai teks biasa."

                    async for chunk in agent.llm.chat_stream(prompt):
                        final_response += chunk
                        yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"

                if not final_response and raw_response:
                    final_response = raw_response
                    for ci in range(0, len(final_response), 3):
                        yield f"data: {json.dumps({'type': 'chunk', 'content': final_response[ci:ci+3]})}\n\n"
                        await asyncio.sleep(0.01)

                if not final_response:
                    intent_fallback = detect_intent(user_message)
                    if intent_fallback:
                        logger.info(f"Fallback to intent detection: {intent_fallback['type']}")
                        yield f"data: {json.dumps({'type': 'status', 'content': 'Using fallback intent detection...'})}\n\n"
                        if intent_fallback["type"] == "use_tool":
                            tool_name = intent_fallback["tool"]
                            params = intent_fallback.get("params", {})
                            start_time = time.time()
                            yield f"data: {json.dumps({'type': 'tool_start', 'tool': tool_name, 'params': params})}\n\n"
                            try:
                                result = await agent._execute_tool(tool_name, params)
                                duration_ms = int((time.time() - start_time) * 1000)
                                tool_exec = {
                                    "tool": tool_name, "params": params,
                                    "result": result[:2000], "duration_ms": duration_ms, "status": "success"
                                }
                                tool_executions.append(tool_exec)
                                log_tool_execution(session_id, tool_name, params, result[:2000], "success", duration_ms)
                                yield f"data: {json.dumps({'type': 'tool_result', 'tool': tool_name, 'result': result[:2000], 'duration_ms': duration_ms, 'status': 'success'})}\n\n"
                                final_response = f"Tool {tool_name} executed.\n\nResult:\n{result[:3000]}"
                                for ci in range(0, len(final_response), 3):
                                    yield f"data: {json.dumps({'type': 'chunk', 'content': final_response[ci:ci+3]})}\n\n"
                            except Exception as tool_err:
                                duration_ms = int((time.time() - start_time) * 1000)
                                error_result = f"Error executing {tool_name}: {str(tool_err)}"
                                tool_exec = {
                                    "tool": tool_name, "params": params,
                                    "result": error_result, "duration_ms": duration_ms, "status": "error"
                                }
                                tool_executions.append(tool_exec)
                                log_tool_execution(session_id, tool_name, params, error_result, "error", duration_ms)
                                yield f"data: {json.dumps({'type': 'tool_result', 'tool': tool_name, 'result': error_result, 'duration_ms': duration_ms, 'status': 'error'})}\n\n"

            add_message(session_id, "assistant", final_response, {"tool_executions": tool_executions})

            if len(get_messages(session_id)) <= 2:
                title = user_message[:50] + ("..." if len(user_message) > 50 else "")
                update_session_title(session_id, title)

            if not final_response and not raw_response:
                final_response = "I couldn't process your request"
                yield f"data: {json.dumps({'type': 'chunk', 'content': final_response})}\n\n"

            yield f"data: {json.dumps({'type': 'done', 'content': final_response, 'tool_executions': tool_executions, 'iterations': agent.iteration_count})}\n\n"
            done_sent = True

        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            error_msg = f"Terjadi kesalahan: {str(e)}"
            if not done_sent:
                try:
                    add_message(session_id, "assistant", error_msg)
                except:
                    pass
                yield f"data: {json.dumps({'type': 'error', 'content': error_msg})}\n\n"
                done_sent = True
        finally:
            if not done_sent:
                yield f"data: {json.dumps({'type': 'done', 'content': final_response or '', 'tool_executions': tool_executions, 'iterations': agent.iteration_count if agent else 0})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/sessions/{session_id}/tools")
async def api_get_tool_executions(session_id: str):
    executions = get_tool_executions(session_id)
    for e in executions:
        for k, v in e.items():
            if hasattr(v, 'isoformat'):
                e[k] = v.isoformat()
    return {"executions": executions}


@app.get("/api/agent/status")
async def api_agent_status():
    agent = get_agent()
    tools = list(agent._tool_instances.keys())
    kb_stats = knowledge_base.get_stats()
    return {
        "state": agent.state,
        "tools": tools,
        "knowledge_base": kb_stats,
        "max_iterations": agent.max_iterations,
    }


@app.get("/api/agent/tools")
async def api_agent_tools():
    agent = get_agent()
    return {"tools": [{"name": n, "type": type(t).__name__} for n, t in agent._tool_instances.items()]}


@app.get("/api/models")
async def api_list_models(category: Optional[str] = None):
    agent = get_agent()
    models = agent.llm.list_models(category)
    current = agent.llm.get_current_model()
    return {
        "models": models,
        "current": current,
        "categories": MODEL_CATEGORIES,
    }


@app.post("/api/models/switch")
async def api_switch_model(request: Request):
    body = await request.json()
    model_id = body.get("model", "")
    if not model_id:
        raise HTTPException(status_code=400, detail="Model ID is required")
    agent = get_agent()
    success = agent.llm.set_model(model_id)
    if not success:
        available = list(AVAILABLE_MODELS.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Model '{model_id}' tidak tersedia. Model yang tersedia: {', '.join(available)}",
        )
    return {
        "ok": True,
        "current": agent.llm.get_current_model(),
    }


@app.get("/api/models/stats")
async def api_model_stats():
    agent = get_agent()
    return {
        "current_model": agent.llm.get_current_model(),
        "retry_stats": agent.llm.get_retry_stats(),
    }


@app.get("/api/files")
async def api_list_files_path(path: str = "."):
    file_tool = FileTool()
    try:
        entries = file_tool.list_directory(path)
        return {"path": path, "entries": entries}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/files/read")
async def api_read_file(path: str):
    file_tool = FileTool()
    try:
        content = file_tool.read_file(path)
        return {"path": path, "content": content[:50000]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/schedule/tasks")
async def api_schedule_tasks():
    agent = get_agent()
    tool = agent._tool_instances.get("schedule_tool")
    if not tool:
        return {"tasks": []}
    return {"tasks": tool.list_tasks()}


@app.post("/api/schedule/tasks")
async def api_create_schedule_task(request: Request):
    body = await request.json()
    agent = get_agent()
    tool = agent._tool_instances.get("schedule_tool")
    if not tool:
        raise HTTPException(status_code=500, detail="Schedule tool not available")

    task_type = body.get("type", "interval")
    if task_type == "cron":
        result = tool.create_cron_task(
            name=body.get("name", "Tugas Baru"),
            cron_expression=body.get("cron_expression", ""),
            callback_name=body.get("callback", "default"),
            description=body.get("description", ""),
        )
    elif task_type == "once":
        import time as _time
        delay = body.get("delay_seconds", 60)
        result = tool.create_once_task(
            name=body.get("name", "Tugas Sekali"),
            run_at=_time.time() + delay,
            callback_name=body.get("callback", "default"),
            description=body.get("description", ""),
        )
    else:
        result = tool.create_task(
            name=body.get("name", "Tugas Baru"),
            interval=body.get("interval", 60),
            callback_name=body.get("callback", "default"),
            description=body.get("description", ""),
        )
    return result


@app.delete("/api/schedule/tasks/{task_id}")
async def api_cancel_schedule_task(task_id: str):
    agent = get_agent()
    tool = agent._tool_instances.get("schedule_tool")
    if not tool:
        raise HTTPException(status_code=500, detail="Schedule tool not available")
    return tool.cancel_task(task_id)


@app.post("/api/schedule/tasks/{task_id}/pause")
async def api_pause_schedule_task(task_id: str):
    agent = get_agent()
    tool = agent._tool_instances.get("schedule_tool")
    if not tool:
        raise HTTPException(status_code=500, detail="Schedule tool not available")
    return tool.pause_task(task_id)


@app.post("/api/schedule/tasks/{task_id}/resume")
async def api_resume_schedule_task(task_id: str):
    agent = get_agent()
    tool = agent._tool_instances.get("schedule_tool")
    if not tool:
        raise HTTPException(status_code=500, detail="Schedule tool not available")
    return tool.resume_task(task_id)


@app.get("/api/schedule/stats")
async def api_schedule_stats():
    agent = get_agent()
    tool = agent._tool_instances.get("schedule_tool")
    if not tool:
        return {"total_tasks": 0}
    return tool.get_stats()


@app.get("/api/schedule/tasks/{task_id}/history")
async def api_schedule_task_history(task_id: str):
    agent = get_agent()
    tool = agent._tool_instances.get("schedule_tool")
    if not tool:
        raise HTTPException(status_code=500, detail="Schedule tool not available")
    return tool.get_task_history(task_id)


@app.get("/api/skills")
async def api_list_skills():
    agent = get_agent()
    tool = agent._tool_instances.get("skill_manager")
    if not tool:
        return {"skills": []}
    return {"skills": tool.list_skills()}


@app.get("/api/skills/{skill_name}")
async def api_get_skill(skill_name: str):
    agent = get_agent()
    tool = agent._tool_instances.get("skill_manager")
    if not tool:
        raise HTTPException(status_code=500, detail="Skill manager not available")
    result = tool.get_skill_info(skill_name)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Not found"))
    return result


@app.post("/api/skills")
async def api_create_skill(request: Request):
    body = await request.json()
    agent = get_agent()
    tool = agent._tool_instances.get("skill_manager")
    if not tool:
        raise HTTPException(status_code=500, detail="Skill manager not available")
    return tool.create_skill(
        name=body.get("name", ""),
        description=body.get("description", ""),
        capabilities=body.get("capabilities", []),
    )


@app.delete("/api/skills/{skill_name}")
async def api_delete_skill(skill_name: str):
    agent = get_agent()
    tool = agent._tool_instances.get("skill_manager")
    if not tool:
        raise HTTPException(status_code=500, detail="Skill manager not available")
    return tool.delete_skill(skill_name)


@app.post("/api/skills/{skill_name}/run")
async def api_run_skill_script(skill_name: str, request: Request):
    body = await request.json()
    agent = get_agent()
    tool = agent._tool_instances.get("skill_manager")
    if not tool:
        raise HTTPException(status_code=500, detail="Skill manager not available")
    script = body.get("script", "main")
    args = body.get("args", {})
    return await tool.run_script(skill_name, script, args)


@app.get("/api/skills/search/{query}")
async def api_search_skills(query: str):
    agent = get_agent()
    tool = agent._tool_instances.get("skill_manager")
    if not tool:
        return {"results": []}
    return {"results": tool.search_skills(query)}


@app.post("/api/learning/feedback")
async def api_learning_feedback(request: Request):
    try:
        body = await request.json()
        result = rlhf_engine.record_feedback(
            session_id=body.get("session_id", ""),
            message_id=body.get("message_id", ""),
            feedback_type=body.get("feedback_type", "rating"),
            value=body.get("value", 0),
            context=body.get("context"),
            comment=body.get("comment", ""),
        )
        return result
    except Exception as e:
        logger.error(f"Error recording feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/learning/stats")
async def api_learning_stats():
    try:
        return rlhf_engine.get_feedback_stats()
    except Exception as e:
        logger.error(f"Error getting feedback stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/learning/insights")
async def api_learning_insights():
    try:
        return rlhf_engine.get_learning_insights()
    except Exception as e:
        logger.error(f"Error getting learning insights: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/learning/tool-preferences")
async def api_learning_tool_preferences(context: str = "general"):
    try:
        agent = get_agent()
        tool_names = list(agent._tool_instances.keys())
        return {"preferences": rlhf_engine.get_tool_preference(tool_names, context)}
    except Exception as e:
        logger.error(f"Error getting tool preferences: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/learning/meta/summary")
async def api_meta_learning_summary():
    try:
        return meta_learner.get_learning_summary()
    except Exception as e:
        logger.error(f"Error getting learning summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/learning/meta/performance")
async def api_meta_learning_performance():
    try:
        return meta_learner.get_performance_report()
    except Exception as e:
        logger.error(f"Error getting performance report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/learning/meta/strategy")
async def api_meta_learning_strategy(task: str = ""):
    try:
        return meta_learner.get_strategy_for_task(task)
    except Exception as e:
        logger.error(f"Error getting strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/security/stats")
async def api_security_stats():
    try:
        return security_manager.get_security_stats()
    except Exception as e:
        logger.error(f"Error getting security stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/security/audit")
async def api_security_audit():
    try:
        return security_manager.run_audit()
    except Exception as e:
        logger.error(f"Error running security audit: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/security/events")
async def api_security_events(limit: int = 50, level: Optional[str] = None):
    try:
        return {"events": security_manager.get_recent_events(limit=limit, threat_level=level)}
    except Exception as e:
        logger.error(f"Error getting security events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/security/events/{event_id}/resolve")
async def api_security_resolve_event(event_id: str):
    try:
        success = security_manager.resolve_event(event_id)
        if success:
            return {"ok": True, "event_id": event_id}
        raise HTTPException(status_code=404, detail="Event tidak ditemukan")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resolving event: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/security/validate-command")
async def api_security_validate_command(request: Request):
    try:
        body = await request.json()
        command = body.get("command", "")
        return security_manager.validate_command(command)
    except Exception as e:
        logger.error(f"Error validating command: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/security/validate-path")
async def api_security_validate_path(request: Request):
    try:
        body = await request.json()
        path = body.get("path", "")
        operation = body.get("operation", "read")
        return security_manager.validate_file_path(path, operation)
    except Exception as e:
        logger.error(f"Error validating path: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/security/rbac/stats")
async def api_rbac_stats():
    try:
        return access_control.get_rbac_stats()
    except Exception as e:
        logger.error(f"Error getting RBAC stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/security/rbac/accounts")
async def api_rbac_accounts():
    try:
        return {"accounts": access_control.list_accounts()}
    except Exception as e:
        logger.error(f"Error listing accounts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/security/rbac/login")
async def api_rbac_login(request: Request):
    try:
        body = await request.json()
        username = body.get("username", "")
        password = body.get("password", "")
        result = access_control.authenticate(username, password)
        if result is None:
            raise HTTPException(status_code=401, detail="Autentikasi gagal")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during login: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/security/privacy/stats")
async def api_privacy_stats():
    try:
        return data_privacy.get_privacy_stats()
    except Exception as e:
        logger.error(f"Error getting privacy stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/security/privacy/compliance")
async def api_privacy_compliance():
    try:
        return data_privacy.get_compliance_report()
    except Exception as e:
        logger.error(f"Error getting compliance report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/security/privacy/detect-pii")
async def api_privacy_detect_pii(request: Request):
    try:
        body = await request.json()
        text = body.get("text", "")
        findings = data_privacy.detect_pii(text)
        return {"findings": findings, "total": len(findings)}
    except Exception as e:
        logger.error(f"Error detecting PII: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/mcp/status")
async def api_mcp_status():
    try:
        agent = get_agent()
        return {
            "mcp_enabled": agent.llm.mcp_enabled,
            "current_model": agent.llm.get_current_model(),
            "stats": agent.llm.get_mcp_stats(),
        }
    except Exception as e:
        logger.error(f"Error getting MCP status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/mcp/providers")
async def api_mcp_providers():
    try:
        return mcp_server.handle_list_providers()
    except Exception as e:
        logger.error(f"Error listing MCP providers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/mcp/models")
async def api_mcp_models():
    try:
        return mcp_server.handle_list_models()
    except Exception as e:
        logger.error(f"Error listing MCP models: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mcp/providers/register")
async def api_mcp_register_provider(request: Request):
    try:
        body = await request.json()
        result = await mcp_server.handle_register_provider(body)
        return result
    except Exception as e:
        logger.error(f"Error registering MCP provider: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/mcp/providers/{name}")
async def api_mcp_unregister_provider(name: str):
    try:
        return mcp_server.handle_unregister_provider(name)
    except Exception as e:
        logger.error(f"Error unregistering MCP provider: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mcp/providers/{name}/toggle")
async def api_mcp_toggle_provider(name: str, request: Request):
    try:
        body = await request.json()
        enabled = body.get("enabled", True)
        return mcp_server.handle_toggle_provider(name, enabled)
    except Exception as e:
        logger.error(f"Error toggling MCP provider: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mcp/providers/{name}/api-key")
async def api_mcp_set_api_key(name: str, request: Request):
    try:
        body = await request.json()
        api_key = body.get("api_key", "")
        return mcp_server.handle_set_api_key(name, api_key)
    except Exception as e:
        logger.error(f"Error setting MCP API key: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mcp/switch")
async def api_mcp_switch_model(request: Request):
    try:
        body = await request.json()
        model = body.get("model", "")
        provider = body.get("provider", "")
        result = mcp_server.handle_switch_model(model, provider)
        agent = get_agent()
        if result.get("ok"):
            agent.llm.set_model(model)
        return result
    except Exception as e:
        logger.error(f"Error switching MCP model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mcp/toggle")
async def api_mcp_toggle(request: Request):
    try:
        body = await request.json()
        enabled = body.get("enabled", True)
        agent = get_agent()
        agent.llm.enable_mcp(enabled)
        return {"ok": True, "mcp_enabled": agent.llm.mcp_enabled}
    except Exception as e:
        logger.error(f"Error toggling MCP: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/mcp/health")
async def api_mcp_health():
    try:
        return await mcp_server.handle_health()
    except Exception as e:
        logger.error(f"Error getting MCP health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/mcp/stats")
async def api_mcp_stats():
    try:
        return mcp_server.handle_stats()
    except Exception as e:
        logger.error(f"Error getting MCP stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/mcp/log")
async def api_mcp_request_log(limit: int = 20):
    try:
        return mcp_server.handle_request_log(limit)
    except Exception as e:
        logger.error(f"Error getting MCP request log: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mcp/complete")
async def api_mcp_complete(request: Request):
    try:
        body = await request.json()
        result = await mcp_server.handle_complete(body)
        return result
    except Exception as e:
        logger.error(f"Error MCP complete: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mcp/chat")
async def api_mcp_chat(request: Request):
    try:
        body = await request.json()
        result = await mcp_server.handle_chat(body)
        return result
    except Exception as e:
        logger.error(f"Error MCP chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mcp/stream")
async def api_mcp_stream(request: Request):
    body = await request.json()

    async def generate():
        try:
            async for chunk_data in mcp_server.handle_stream(body):
                yield f"data: {json.dumps(chunk_data)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.get("/api/vm/list")
async def api_vm_list(state: Optional[str] = None):
    return {"vms": vm_manager.list_vms(state_filter=state)}


@app.post("/api/vm/create")
async def api_vm_create(request: Request):
    try:
        body = await request.json()
        isolation = None
        if body.get("isolation_level"):
            try:
                isolation = IsolationLevel(body["isolation_level"])
            except ValueError:
                pass
        result = vm_manager.create_vm(
            name=body.get("name", "sandbox"),
            runtime=body.get("runtime", "python3"),
            isolation_level=isolation,
            environment=body.get("environment"),
            tags=body.get("tags"),
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/vm/{vm_id}/start")
async def api_vm_start(vm_id: str):
    return vm_manager.start_vm(vm_id)


@app.post("/api/vm/{vm_id}/stop")
async def api_vm_stop(vm_id: str):
    return vm_manager.stop_vm(vm_id)


@app.post("/api/vm/{vm_id}/execute")
async def api_vm_execute(vm_id: str, request: Request):
    try:
        body = await request.json()
        system_monitor.metrics.increment("vm.executions")
        timer_id = system_monitor.performance.start_timer("vm_execute")
        result = await vm_manager.execute_in_vm(vm_id, body.get("command", ""), body.get("timeout"))
        system_monitor.performance.stop_timer(timer_id, {"vm_id": vm_id})
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/vm/{vm_id}/execute_code")
async def api_vm_execute_code(vm_id: str, request: Request):
    try:
        body = await request.json()
        result = await vm_manager.execute_code_in_vm(vm_id, body.get("code", ""), body.get("runtime"), body.get("timeout"))
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/vm/{vm_id}")
async def api_vm_get(vm_id: str):
    vm = vm_manager.get_vm(vm_id)
    if not vm:
        raise HTTPException(status_code=404, detail="VM tidak ditemukan")
    return vm


@app.delete("/api/vm/{vm_id}")
async def api_vm_destroy(vm_id: str):
    return vm_manager.destroy_vm(vm_id)


@app.post("/api/vm/{vm_id}/snapshot")
async def api_vm_snapshot(vm_id: str, request: Request):
    body = await request.json()
    return vm_manager.create_snapshot(vm_id, body.get("name", "snapshot"), body.get("description", ""))


@app.post("/api/vm/{vm_id}/restore/{snapshot_id}")
async def api_vm_restore(vm_id: str, snapshot_id: str):
    return vm_manager.restore_snapshot(vm_id, snapshot_id)


@app.get("/api/vm/{vm_id}/logs")
async def api_vm_logs(vm_id: str, limit: int = 50, level: Optional[str] = None):
    return vm_manager.get_vm_logs(vm_id, limit, level)


@app.get("/api/vm/stats")
async def api_vm_stats():
    return vm_manager.get_stats()


@app.post("/api/shell/create")
async def api_shell_create(request: Request):
    try:
        body = await request.json()
        result = await shell_session_manager.create_session(
            working_dir=body.get("working_dir"),
            env=body.get("env"),
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/shell/{session_id}/execute")
async def api_shell_execute(session_id: str, request: Request):
    try:
        body = await request.json()
        system_monitor.metrics.increment("shell.executions")
        timer_id = system_monitor.performance.start_timer("shell_execute")
        result = await shell_session_manager.execute_in_session(
            session_id, body.get("command", ""), body.get("timeout", 120)
        )
        system_monitor.performance.stop_timer(timer_id, {"session_id": session_id})
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/shell/{session_id}/script")
async def api_shell_script(session_id: str, request: Request):
    try:
        body = await request.json()
        result = await shell_session_manager.execute_script_in_session(
            session_id, body.get("code", ""), body.get("runtime", "bash"), body.get("timeout", 120)
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/shell/{session_id}")
async def api_shell_get(session_id: str):
    session = shell_session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sesi tidak ditemukan")
    return session


@app.get("/api/shell/{session_id}/history")
async def api_shell_history(session_id: str, limit: int = 50):
    return shell_session_manager.get_session_history(session_id, limit)


@app.delete("/api/shell/{session_id}")
async def api_shell_close(session_id: str):
    return await shell_session_manager.close_session(session_id)


@app.get("/api/shell/list")
async def api_shell_list():
    return {"sessions": shell_session_manager.list_sessions()}


@app.get("/api/shell/stats")
async def api_shell_stats():
    return shell_session_manager.get_stats()


@app.post("/api/spreadsheet/create")
async def api_spreadsheet_create(request: Request):
    try:
        body = await request.json()
        agent = get_agent()
        tool = agent._tool_instances.get("spreadsheet_tool")
        if not tool:
            raise HTTPException(status_code=500, detail="SpreadsheetTool tidak tersedia")
        result = tool.create_spreadsheet(
            name=body.get("name", "untitled"),
            headers=body.get("headers", []),
            data=body.get("data"),
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/spreadsheet/read")
async def api_spreadsheet_read(request: Request):
    try:
        body = await request.json()
        agent = get_agent()
        tool = agent._tool_instances.get("spreadsheet_tool")
        if not tool:
            raise HTTPException(status_code=500, detail="SpreadsheetTool tidak tersedia")
        return tool.read_spreadsheet(body.get("file_path", ""), body.get("limit"), body.get("offset", 0))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/spreadsheet/stats")
async def api_spreadsheet_stats(request: Request):
    try:
        body = await request.json()
        agent = get_agent()
        tool = agent._tool_instances.get("spreadsheet_tool")
        if not tool:
            raise HTTPException(status_code=500, detail="SpreadsheetTool tidak tersedia")
        return tool.get_statistics(body.get("file_path", ""), body.get("column"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/spreadsheet/filter")
async def api_spreadsheet_filter(request: Request):
    try:
        body = await request.json()
        agent = get_agent()
        tool = agent._tool_instances.get("spreadsheet_tool")
        if not tool:
            raise HTTPException(status_code=500, detail="SpreadsheetTool tidak tersedia")
        return tool.filter_data(body.get("file_path", ""), body.get("column", ""), body.get("operator", "eq"), body.get("value", ""))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/playbook/list")
async def api_playbook_list(category: Optional[str] = None):
    try:
        agent = get_agent()
        tool = agent._tool_instances.get("playbook_manager")
        if not tool:
            raise HTTPException(status_code=500, detail="PlaybookManager tidak tersedia")
        return {"playbooks": tool.list_playbooks(category=category)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/playbook/create")
async def api_playbook_create(request: Request):
    try:
        body = await request.json()
        agent = get_agent()
        tool = agent._tool_instances.get("playbook_manager")
        if not tool:
            raise HTTPException(status_code=500, detail="PlaybookManager tidak tersedia")
        return tool.create_playbook(
            name=body.get("name", ""),
            description=body.get("description", ""),
            category=body.get("category", "general"),
            tags=body.get("tags"),
            steps=body.get("steps"),
            variables=body.get("variables"),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/playbook/{playbook_id}/execute")
async def api_playbook_execute(playbook_id: str, request: Request):
    try:
        body = await request.json()
        agent = get_agent()
        tool = agent._tool_instances.get("playbook_manager")
        if not tool:
            raise HTTPException(status_code=500, detail="PlaybookManager tidak tersedia")
        return await tool.execute_playbook(playbook_id, variables=body.get("variables"), dry_run=body.get("dry_run", False))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/playbook/{playbook_id}")
async def api_playbook_delete(playbook_id: str):
    try:
        agent = get_agent()
        tool = agent._tool_instances.get("playbook_manager")
        if not tool:
            raise HTTPException(status_code=500, detail="PlaybookManager tidak tersedia")
        return tool.delete_playbook(playbook_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/playbook/stats")
async def api_playbook_stats():
    try:
        agent = get_agent()
        tool = agent._tool_instances.get("playbook_manager")
        if not tool:
            raise HTTPException(status_code=500, detail="PlaybookManager tidak tersedia")
        return tool.get_stats()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/playbook/patterns")
async def api_playbook_patterns():
    try:
        agent = get_agent()
        tool = agent._tool_instances.get("playbook_manager")
        if not tool:
            raise HTTPException(status_code=500, detail="PlaybookManager tidak tersedia")
        return {"patterns": tool.detect_patterns()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/monitor/dashboard")
async def api_monitor_dashboard():
    return system_monitor.get_dashboard()


@app.get("/api/monitor/health")
async def api_monitor_health():
    return await system_monitor.health.run_checks()


@app.get("/api/monitor/performance")
async def api_monitor_performance(operation: Optional[str] = None):
    return system_monitor.performance.get_stats(operation)


@app.get("/api/monitor/performance/slow")
async def api_monitor_slow_ops(threshold: float = 5.0, limit: int = 20):
    return {"slow_operations": system_monitor.performance.get_slow_operations(threshold, limit)}


@app.get("/api/monitor/requests")
async def api_monitor_requests(limit: int = 50):
    return {
        "recent": system_monitor.request_logger.get_recent(limit),
        "stats": system_monitor.request_logger.get_stats(),
    }


@app.get("/api/monitor/requests/errors")
async def api_monitor_request_errors(limit: int = 50):
    return {"errors": system_monitor.request_logger.get_errors(limit)}


@app.get("/api/monitor/metrics/{name}")
async def api_monitor_metric(name: str, last_n: int = 100):
    return {"metric": name, "points": system_monitor.metrics.get_metric(name, last_n)}


@app.get("/api/monitor/system")
async def api_monitor_system():
    return system_monitor.get_system_info()


@app.post("/api/tests/run")
async def api_run_tests():
    try:
        from tests.test_framework import create_test_suite
        suite = create_test_suite()
        result = await suite.run_all()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.middleware("http")
async def monitor_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start

    if request.url.path.startswith("/api/"):
        system_monitor.request_logger.log_request(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration=duration,
        )
        system_monitor.metrics.increment("http.requests.total")
        system_monitor.performance.record_timing("http_request", duration, {"path": request.url.path})

    return response


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)
