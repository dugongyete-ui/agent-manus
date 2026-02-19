# Manus Agent

## Overview

Manus Agent is an autonomous AI agent framework designed in Python, operating on an iterative loop of Analyze -> Think -> Select -> Execute -> Observe. It features a modular architecture, enabling the agent to utilize a diverse set of tools for tasks such as shell operations, file management, browser automation, web search, media generation, presentations, web development scaffolding, task scheduling, skill management, and user messaging. The project incorporates a sandbox environment to ensure secure code execution and robust VM lifecycle management. The core vision for Manus Agent is to provide a highly adaptable and intelligent assistant capable of automating complex workflows and enhancing productivity across various domains.

## User Preferences

Preferred communication style: Simple, everyday language.

## Recent Changes

### Fase 16: Deep Analysis & Planning Orchestration (Feb 19, 2026)
- **4-Phase Execution Flow**: Implemented Planning → Execution → Reflection → Synthesis orchestration loop, replacing the shallow instant-response pattern
- **LLM as Primary Decision Maker**: Removed `detect_intent()` regex bypass as primary dispatcher - LLM now decides what tools to use. Intent detection is fallback only
- **Planner Integration**: Planner class now actively used in main flow via `_create_initial_plan()` and `_reflect_on_result()` methods
- **Universal System Prompt**: Rewrote system prompt to work across ALL models (not just default). Supports `plan`, `think`, `use_tool`, `multi_step`, `respond` action types
- **Deep Analysis Mode**: Multi-step execution with iterative reflection. Agent analyzes tool results and decides if more steps are needed before synthesizing final answer
- **Robust JSON Parser**: `_parse_llm_response()` handles mixed text+JSON, trailing commas, multiple JSON blocks, and infers tool type from context
- **Shell Tool Workspace Isolation**: Shell commands now execute in `/home/runner/workspace/user_workspace/` instead of project root
- **Frontend Planning UI**: Added plan card visualization, thinking indicators, reflection display, and phase status tracking in the chat interface
- **New SSE Event Types**: `planning`, `plan`, `thinking`, `reflection`, `phase` events for rich frontend visualization of agent reasoning process

### Fase 15: Full Tool Test & MCP SSE Fix (Feb 19, 2026)
- **MCP SSE Parser Fix**: Fixed `CustomProvider.complete()` and `stream()` to handle SSE responses where data chunks are JSON-quoted strings (`data: "text"`) instead of JSON objects
- **Intent Detection Safety**: Added question-pattern bypass to prevent questions (apa/siapa/bagaimana/why/how/etc.) from triggering tool execution; added empty-param validation to skip invalid matches
- **All 10 Tools Verified**: shell_tool, file_tool, search_tool, browser_tool, generate_tool, slides_tool, webdev_tool, schedule_tool, message_tool, skill_manager - all tested and working
- **MCP Multi-Model Verified**: Successfully tested chat with claude40opusthinking_labs and gpt5_thinking models via dzeck provider; streaming also works

### Fase 14: Intent Bypass & Real Tool Execution (Feb 19, 2026)
- **First-Iteration Intent Bypass**: Added `detect_intent()` bypass in both `api_chat` and `api_chat_stream` endpoints - tools execute IMMEDIATELY when intent is clear (e.g., "buka google.com" -> browser_tool runs without LLM), skipping unnecessary LLM round-trips
- **Fallback Intent Detection Fix**: `_parse_llm_response()` now receives `user_input` parameter in server.py, enabling fallback intent detection when LLM returns plain text instead of JSON
- **System Prompt v2**: Complete rewrite with explicit examples, mandatory mapping rules, and stronger enforcement of JSON-only output format
- **Setup Script v2**: Optimized `setup.sh` with parallel pip install, auto-detect missing modules, MCP module verification, and server startup test

### Fase 13: Autonomous Tool Execution Fix (Feb 19, 2026)
- **System Prompt Overhaul**: Rewrote agent system prompt to enforce JSON-only tool call responses; prevents LLM from responding "I can't run tools"
- **Robust JSON Parser**: Enhanced `_parse_llm_response()` to handle JSON in markdown code blocks, embedded in text, and fallback text-based tool detection
- **File Tool Completeness**: Added `analyze`, `search`, and `info` operations to `_execute_file_tool()` with fallback implementations
- **Slides HTML Export**: Added `export_html()` method to SlidesTool for generating interactive HTML presentations with keyboard navigation
- **Browser Tool Fix**: Updated to use system-installed Chromium (`/nix/store/...chromium`) via `shutil.which()` for reliable headless browsing
- **Generate Tool**: Updated `generate()` to accept `**kwargs` for passing params directly from tool calls
- **Slides Tool Handler**: Expanded `_execute_tool` slides handling to support `create`, `add_slide`, `export`, and `list` actions

### Fase 12: Integrasi Eksternal Tanpa Kunci (Feb 19, 2026)
- **Multi-Model AI Support**: Added 16 AI models accessible via public API endpoint with `?provider=Perplexity&model={model}` pattern
  - Models: gpt5_thinking, 03, o3pro, claude40opus, claude40opusthinking, claude41opusthinking, claude45sonnet, claude45sonnetthinking, grok4, o3_research, o3pro_research, claude40sonnetthinking_research, o3pro_labs, claude40opusthinking_labs, r1
  - Categories: thinking, reasoning, general, research, labs
- **Retry Logic**: Exponential backoff with jitter for rate-limited public endpoints (max 5 retries, respects Retry-After headers)
- **Data Validation**: All API responses are validated and sanitized against injection attacks (XSS, code injection patterns)
- **Auto Parameter Generator**: Automatic intent detection from user input (search, analysis, generation, explanation, coding, etc.)
- **Model Selector UI**: Interactive dropdown in top bar for switching between AI models, with category filtering
- **API Endpoints**: `/api/models` (list), `/api/models/switch` (change), `/api/models/stats` (retry stats)

## System Architecture

### Agent Core
The `agent_core` module orchestrates the agent's primary functions. The `AgentLoop` manages the iterative reasoning process, interacting with a Language Model for action planning and execution, and integrates self-improvement mechanisms like `RLHFEngine` (Reinforcement Learning from Human Feedback) and `MetaLearner` for optimizing strategies and tool usage. Security is paramount, with `SecurityManager`, `AccessControl` (Role-Based Access Control), and `DataPrivacyManager` ensuring secure operations, access management, and compliance with data privacy standards (including PII detection and GDPR). The `LLMClient` handles communication with AI APIs supporting 16 models across 5 categories (thinking, reasoning, general, research, labs) with robust retry logic and data validation. `ContextManager` maintains conversation history with token limits and auto-summarization, while `KnowledgeBase` provides persistent memory via SQLite for knowledge entries and tool usage logs. `Planner` facilitates hierarchical task management, and `ToolSelector` intelligently dispatches tasks to appropriate tools. `UserManager` manages user profiles and preferences.

### Tools
The `tools` directory contains various specialized tools callable by the agent:
- **`ShellTool`**: Secure execution of shell commands and code in multiple languages (Python, Node, Bash, Ruby, PHP).
- **`FileTool`**: Comprehensive file system operations, including CRUD, and multimodal analysis (PDF, images, audio, code, data).
- **`BrowserTool`**: Full browser automation using Playwright/Chromium for navigation, interaction, and data extraction.
- **`SearchTool`**: Web search capabilities utilizing DuckDuckGo, including content fetching and caching.
- **`GenerateTool`**: Multimodal content generation, supporting images, SVG, charts, audio, video, and documents.
- **`SlidesTool`**: Logic for creating and managing presentations.
- **`WebDevTool`**: Scaffolding for web projects across multiple frameworks (React, Vue, Flask, Express, Next.js, FastAPI).
- **`ScheduleTool`**: Robust task scheduling with cron, interval, and one-time options, featuring persistence and history tracking.
- **`MessageTool`**: Facilitates structured communication with the user.
- **`SkillManager`**: Manages dynamic discovery, loading, and execution of extensible skills.

### Skills System
The `skills` system allows for dynamic extensibility. Each skill is a modular directory containing `SKILL.md` for documentation, `config.json` for metadata, and a `scripts/` folder for implementation. Skills are loaded and managed by the `SkillManager`, with built-in examples including `skill_creator`, `code_analyzer`, and `system_monitor`.

### Sandbox Environment
The `sandbox_env` provides a secure and isolated environment for operations. `RuntimeExecutor` handles code execution across various runtimes with timeouts. `PackageManager` manages package installations (pip, npm, yarn). `VMManager` controls the lifecycle of virtual machines (start, stop, snapshot, restore).

### Web UI
The web interface is built with a FastAPI backend on port 5000, using Jinja2 templates for rendering. It features a PostgreSQL database for persistent storage of sessions, messages, and tool execution logs. The UI includes a dark theme with model selector dropdown, and provides various panels for activity, files, tools, schedule management, skill overview, learning insights (feedback, tool performance), and security monitoring (audits, RBAC, privacy compliance).

### LLM Integration (Fase 12)
- **Multi-Model**: 16 AI models accessible without API keys via public endpoint
- **Retry Logic**: Exponential backoff with jitter, configurable max retries, respects rate limit headers
- **Data Validation**: Response sanitization against XSS/injection, dynamic JSON structure parsing
- **Auto Parameters**: Intent-based query parameter generation from user input
- **Model Management API**: REST endpoints for listing, switching, and monitoring models

### MCP (Model Context Protocol) Integration (Fase 12 - Phase 2)
- **Protocol Layer** (`mcp/protocol.py`): Dataclass-based message types (MCPMessage, MCPRequest, MCPResponse, MCPToolCall), provider config, transport config
- **Provider Adapters** (`mcp/providers.py`): Unified interface for OpenAI, Anthropic, Google, Custom/Local providers with schema conversion
- **Registry** (`mcp/registry.py`): Provider registration, model routing, statistics tracking, default provider configuration (dzeck with 15 models)
- **Client** (`mcp/client.py`): High-level async API for chat/complete/stream with automatic provider routing and retry logic
- **Server** (`mcp/server.py`): Request handler with REST-compatible methods for all MCP operations
- **Transport** (`mcp/transport.py`): stdio and HTTP/SSE transport layer support
- **LLM Integration**: `LLMClient` now initializes MCP Client internally, syncs model switching, exposes MCP stats/health
- **API Endpoints**: `/api/mcp/status`, `/api/mcp/providers`, `/api/mcp/models`, `/api/mcp/switch`, `/api/mcp/toggle`, `/api/mcp/health`, `/api/mcp/stats`, `/api/mcp/log`, `/api/mcp/complete`, `/api/mcp/chat`, `/api/mcp/stream`
- **Backend Only**: MCP berjalan di belakang layar tanpa tampilan di UI, otomatis aktif saat server start, tidak memerlukan API key (menggunakan public API endpoint)

### Key Design Patterns
The system is built on principles of asynchronous operations (`async/await`), a strong emphasis on **safety** (command/path blocklists, timeouts, PII detection, RBAC), **self-improvement** through RLHF and meta-learning, **modular tool design**, **configuration-driven behavior**, **auto-cleanup** of resources, and an **extensible skills system**.

## External Dependencies

### Python Packages
- `pyyaml`: Configuration parsing.
- `aiohttp`: Asynchronous HTTP client for external API interactions.
- `aiofiles`: Asynchronous file operations.
- `rich`, `prompt-toolkit`: Enhancements for terminal UI.
- `playwright`: Headless browser automation.
- `beautifulsoup4`: HTML parsing.
- `Pillow`: Image processing and generation.
- `PyPDF2`: PDF text extraction and metadata.
- `mutagen`: Audio file metadata analysis.

### System Dependencies
- **Playwright Chromium dependencies**: Various `nspr`, `nss`, `atk`, `cups`, `mesa`, `pango`, `alsa-lib`, `libdrm`, `libxkbcommon`, and Xorg libraries for headless browser functionality.

### Data Storage
- **SQLite**: Used for the agent's knowledge base (`knowledge_base.db`).
- **JSON files**: Store user profiles (`user_profiles.json`) and scheduled tasks (`scheduled_tasks.json`).
- **PostgreSQL**: Backend database for the web UI, storing conversation sessions, messages, and tool execution logs.
