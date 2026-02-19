import asyncio
import json
import logging
import os
import subprocess
import sys
import time
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
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import yaml

from web.database import (
    init_database, create_session, get_sessions, get_session,
    delete_session, update_session_title, add_message, get_messages,
    build_context_string, log_tool_execution, get_tool_executions
)
from agent_core.agent_loop import AgentLoop, SYSTEM_PROMPT
from agent_core.llm_client import LLMClient
from agent_core.knowledge_base import KnowledgeBase
from agent_core.context_manager import ContextManager
from tools.shell_tool import ShellTool
from tools.file_tool import FileTool
from tools.search_tool import SearchTool
from tools.message_tool import MessageTool
from tools.browser_tool import BrowserTool
from tools.webdev_tool import WebDevTool
from tools.generate_tool import GenerateTool
from tools.slides_tool import SlidesTool
from tools.schedule_tool import ScheduleTool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Manus Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

web_dir = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(web_dir, "static")), name="static")

llm_client = LLMClient()
knowledge_base = KnowledgeBase()

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
        agent_loop.register_tool("schedule_tool", ScheduleTool())
    return agent_loop


@app.on_event("startup")
async def startup():
    init_database()
    get_agent()
    logger.info("Manus Agent Web Server started")


@app.get("/api/health")
async def api_health():
    return {"status": "healthy", "agent_state": agent_loop.state if agent_loop else "not_initialized"}


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
    if not user_message:
        raise HTTPException(status_code=400, detail="Message is required")

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

        for iteration in range(max_iterations):
            agent.iteration_count = iteration + 1
            context = agent.context_manager.get_context_window()
            llm_input = agent._build_llm_prompt(context)

            raw_response = await agent.llm.chat(llm_input)
            action = agent._parse_llm_response(raw_response)

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
    if not user_message:
        raise HTTPException(status_code=400, detail="Message is required")

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

        try:
            agent.context_manager.clear()
            agent.context_manager.set_system_prompt(SYSTEM_PROMPT)
            agent.context_manager.add_message("user", full_prompt)
            agent.iteration_count = 0
            agent.execution_log.clear()

            max_iterations = agent.max_iterations

            for iteration in range(max_iterations):
                agent.iteration_count = iteration + 1

                yield f"data: {json.dumps({'type': 'status', 'content': 'Menganalisis...'})}\n\n"

                context = agent.context_manager.get_context_window()
                llm_input = agent._build_llm_prompt(context)

                raw_response = ""
                raw_chunks = []
                async for chunk in agent.llm.chat_stream(llm_input):
                    raw_chunks.append(chunk)
                raw_response = "".join(raw_chunks)

                action = agent._parse_llm_response(raw_response)

                if action["type"] == "respond":
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

                elif action["type"] == "multi_step":
                    for step in action.get("steps", []):
                        tool_name = step.get("tool", "")
                        params = step.get("params", {})
                        start_time = time.time()

                        yield f"data: {json.dumps({'type': 'tool_start', 'tool': tool_name, 'params': params})}\n\n"

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

                    all_results = [f"[{te['tool']}]: {te['result']}" for te in tool_executions[-len(action.get('steps', [])):]]
                    agent.context_manager.add_message("assistant", "Menjalankan beberapa langkah...")
                    agent.context_manager.add_message("system", "\n".join(all_results))

                elif action["type"] == "error":
                    final_response = action.get("message", raw_response)
                    yield f"data: {json.dumps({'type': 'chunk', 'content': final_response})}\n\n"
                    break
            else:
                yield f"data: {json.dumps({'type': 'status', 'content': 'Menyusun jawaban akhir...'})}\n\n"
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

            add_message(session_id, "assistant", final_response, {"tool_executions": tool_executions})

            if len(get_messages(session_id)) <= 2:
                title = user_message[:50] + ("..." if len(user_message) > 50 else "")
                update_session_title(session_id, title)

            yield f"data: {json.dumps({'type': 'done', 'content': final_response, 'tool_executions': tool_executions, 'iterations': agent.iteration_count})}\n\n"

        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            error_msg = f"Terjadi kesalahan: {str(e)}"
            add_message(session_id, "assistant", error_msg)
            yield f"data: {json.dumps({'type': 'error', 'content': error_msg})}\n\n"

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


@app.get("/api/files")
async def api_list_files(path: str = "."):
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


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)
