# Manus Agent

## Overview

Manus Agent is an autonomous AI agent framework built in Python that follows an iterative agent loop pattern (Analyze -> Think -> Select -> Execute -> Observe). It provides a modular architecture where the agent can use various tools (shell, file operations, browser automation, web search, media generation, presentations, web development scaffolding, task scheduling, skill management, and user messaging) to accomplish tasks requested by users. The project includes a sandbox environment for safe code execution and VM lifecycle management.

The codebase is primarily in Indonesian (variable names, comments, log messages), reflecting its origin. All modules are fully implemented with working logic.

## Recent Changes

- **2026-02-19**: Wave 4 Phase 8 completed - Skill management system:
  - `tools/skill_manager.py`: SkillManager class with dynamic skill discovery, loading, execution, listing, and use tracking
  - Enhanced `skills/skill_creator/scripts/create_skill.py` with improved templates and validation
  - New skills: `code_analyzer` (code stats/complexity/imports), `system_monitor` (CPU/memory/disk/processes)
  - UI updated with Skills tab in right panel showing loaded skills with capabilities, scripts, and usage stats
- **2026-02-19**: Wave 4 Phase 6 completed - Full task scheduling & automation:
  - `tools/schedule_tool.py`: CronParser (5-field cron expressions), TaskType enum (INTERVAL/CRON/ONCE), TaskStatus lifecycle, notification callbacks, task history tracking (50-entry limit), JSON persistence (`data/scheduled_tasks.json`), pause/resume/cancel
  - UI updated with Schedule tab showing task stats, task list with pause/resume/cancel controls
  - REST API endpoints: `/api/schedule/tasks`, `/api/schedule/stats`, `/api/schedule/tasks/{id}/pause|resume`
  - REST API endpoints: `/api/skills`, `/api/skills/{name}`, `/api/skills/{name}/execute`
- **2026-02-19**: Wave 4 Phase 5 completed - Multimodal capabilities:
  - `generate_tool.py`: Full image generation (Pillow with gradient/shapes/text), SVG generation, chart generation (bar/pie/line), audio synthesis (notification/melody/ambient/tone), video generation (frame animation with ffmpeg/GIF fallback), document generation (HTML/Markdown/text)
  - `file_tool.py`: Multimodal document understanding - PDF extraction (PyPDF2), image analysis (dimensions/mode/brightness/histogram/thumbnail), audio analysis (mutagen/wave metadata), code analysis (function/class/import extraction), CSV/JSON/YAML/XML parsing, file search, directory tree, binary read/write, base64 encoding
  - UI responsive fix: dvh units, proper flex layout, mobile breakpoints (768px/400px), compact welcome screen on small screens
- **2026-02-19**: Wave 3 completed - Full web UI with dark theme (purple accent), FastAPI backend with all endpoints, PostgreSQL conversation memory (sessions/messages/tool_executions), sidebar chat list, main chat panel, right panel with Activity/Files/Tools tabs, code viewer modal.
- **2026-02-19**: Wave 2 completed - browser_tool.py now uses real Playwright/Chromium, search_tool.py uses DuckDuckGo scraping, shell_tool.py enhanced with security blocklists and run_code(), webdev_tool.py expanded with 6 frameworks and dependency management. All tools integrated into agent_loop.py.
- **2026-02-19**: Wave 1 verified - all core modules (agent_loop, context_manager, knowledge_base, llm_client, planner, tool_selector, user_manager) tested and working. 9 tools and sandbox env all importable and functional.

## User Preferences

Preferred communication style: Simple, everyday language.

## Project Structure

```
/home/runner/workspace/
+-- agent_core/                   # Core Agent Loop logic and context management
|   +-- __init__.py
|   +-- main.py                   # Entry point, initializes Agent Loop with CLI
|   +-- agent_loop.py             # Agent Loop (Analyze, Think, Select, Execute, Observe)
|   +-- context_manager.py        # Conversation context and memory management
|   +-- knowledge_base.py         # SQLite-based persistent knowledge storage
|   +-- llm_client.py             # LLM API client (Dzeck AI SSE streaming)
|   +-- planner.py                # Task plan creation and management
|   +-- tool_selector.py          # Tool selection based on intent and keywords
|   +-- user_manager.py           # User profile and preference management
+-- tools/                        # Tool implementations callable by agent
|   +-- __init__.py
|   +-- shell_tool.py             # Shell commands with security + run_code()
|   +-- file_tool.py              # File system operations wrapper
|   +-- browser_tool.py           # Playwright/Chromium browser automation
|   +-- search_tool.py            # DuckDuckGo web search + page fetching
|   +-- generate_tool.py          # Media generation wrapper (image, video, audio)
|   +-- slides_tool.py            # Presentation creation logic
|   +-- webdev_tool.py            # Web project scaffolding (6 frameworks)
|   +-- schedule_tool.py          # Cron/interval/one-time task scheduling with persistence
|   +-- message_tool.py           # User communication logic
|   +-- skill_manager.py          # Dynamic skill discovery, loading, and execution
+-- skills/                       # Extensible skills directory
|   +-- skill_creator/            # Meta-skill for creating new skills
|   |   +-- SKILL.md
|   |   +-- config.json
|   |   +-- scripts/create_skill.py
|   +-- code_analyzer/            # Code analysis skill (stats, complexity, imports)
|   |   +-- SKILL.md
|   |   +-- config.json
|   |   +-- scripts/analyze.py
|   +-- system_monitor/           # System health monitoring skill
|   |   +-- SKILL.md
|   |   +-- config.json
|   |   +-- scripts/monitor.py
|   +-- another_skill/            # Example/template skill
|       +-- SKILL.md
|       +-- config.json
+-- sandbox_env/                  # Sandbox environment management
|   +-- __init__.py
|   +-- vm_manager.py             # VM lifecycle management (start, stop, snapshot)
|   +-- package_manager.py        # Package installation (pip, npm, yarn)
|   +-- runtime_executor.py       # Multi-runtime code execution
+-- config/                       # Global configuration files
|   +-- settings.yaml             # System settings
|   +-- tool_configs.json         # Per-tool configuration
+-- logs/                         # System and agent activity logs
+-- data/                         # Persistent data
|   +-- knowledge_base.db         # Agent knowledge base (SQLite)
|   +-- user_profiles.json        # User profiles and preferences
|   +-- scheduled_tasks.json      # Persisted scheduled tasks
+-- web/                          # Web UI & API server
|   +-- __init__.py
|   +-- server.py                 # FastAPI server (port 5000)
|   +-- database.py               # PostgreSQL database layer
|   +-- templates/
|   |   +-- index.html            # Main HTML template
|   +-- static/
|       +-- css/style.css         # Dark theme styles
|       +-- js/app.js             # Frontend JavaScript
+-- pyproject.toml                # Python dependencies
```

## System Architecture

### Agent Core (`agent_core/`)
- **AgentLoop** (`agent_loop.py`): Orchestrates the main loop with LLM-powered reasoning. Sends context to Dzeck AI API, parses JSON action responses, executes tools, and observes results iteratively. Max iterations: 10. Supports use_tool, multi_step, and respond actions. Registers 10 tools including schedule_tool and skill_manager.
- **LLMClient** (`llm_client.py`): Connects to Dzeck AI streaming API (SSE format). Supports streaming and non-streaming chat, system prompts, and multi-message context.
- **ContextManager** (`context_manager.py`): Manages conversation history with token limits (128K), sliding memory window (20 messages), and auto-summarization (threshold: 15).
- **KnowledgeBase** (`knowledge_base.py`): SQLite-based persistent memory. Stores knowledge entries (category/key/value), conversation summaries, and tool usage logs with statistics.
- **UserManager** (`user_manager.py`): JSON-based user profile management with preferences, interaction tracking, and persistence.
- **Planner** (`planner.py`): Task plans with priorities, statuses (PENDING -> IN_PROGRESS -> COMPLETED/FAILED/CANCELLED), hierarchical subtasks.
- **ToolSelector** (`tool_selector.py`): Keyword-based tool selection from a registry of 10 tools.
- **Main** (`main.py`): CLI entry point using `rich` and `prompt_toolkit`. Registers all tools, manages user sessions.

### Tools (`tools/`)
| Tool | Purpose | Implementation |
|------|---------|----------------|
| `ShellTool` | Shell commands + code execution | Security blocklists, run_code() for Python/Node/Bash/Ruby/PHP, concurrent process limits, timeout handling |
| `FileTool` | File CRUD + multimodal analysis | Read/write/edit + analyze_file (PDF/image/audio/code/data), extract_pdf_text, get_image_info/base64, search_files, directory_tree |
| `BrowserTool` | Full browser automation | Playwright/Chromium: navigate, screenshot, click, fill, type, extract_text, extract_links, execute_js, scroll, go_back/forward, wait_for_element, cookie management |
| `SearchTool` | Web search + page fetching | DuckDuckGo HTML/Lite scraping, result caching (1hr TTL), fetch_page_content with BeautifulSoup, multi_search |
| `GenerateTool` | Multimodal media generation | Image (Pillow), SVG, charts (bar/pie/line), audio (WAV synthesis), video (frame animation), documents (HTML/MD/TXT) |
| `SlidesTool` | Presentation creation | Slide/layout models with content management |
| `WebDevTool` | Project scaffolding | React, Vue, Flask, Express, Next.js, FastAPI templates + install_dependencies, add_dependency, build_project |
| `ScheduleTool` | Task scheduling & automation | CronParser (5-field cron), interval/once/cron tasks, pause/resume/cancel, notification callbacks, history tracking, JSON persistence |
| `MessageTool` | User communication | Typed messages (info/warning/success/error) |
| `SkillManager` | Dynamic skill management | Discover/load/execute skills, use tracking, skill listing, config-driven metadata |

### Skills System (`skills/`)
- Skills are modular directories with `SKILL.md` (documentation), `config.json` (metadata: name, description, version, capabilities, scripts), and `scripts/` folder
- SkillManager discovers and loads skills dynamically from the `skills/` directory
- Built-in skills: `skill_creator` (meta-skill), `code_analyzer`, `system_monitor`
- Skills track usage count and last-used timestamp

### Sandbox Environment (`sandbox_env/`)
- **RuntimeExecutor**: Code execution in Python, Node.js, Bash, Ruby, PHP with timeouts.
- **PackageManager**: Package installation via pip, npm, yarn.
- **VMManager**: VM lifecycle management (start, stop, pause, snapshot, restore).

### Web UI (`web/`)
- FastAPI server on port 5000 with Jinja2 templates
- PostgreSQL-backed session/message/tool_execution persistence
- Right panel tabs: Activity, Files, Tools, Schedule, Skills
- Schedule tab: stats display, task list with pause/resume/cancel controls
- Skills tab: skill cards with capabilities, scripts, version, usage stats
- REST API endpoints for all agent, session, schedule, and skill operations

### Key Design Patterns
- **Async throughout**: All tools and agent loop use `async/await`.
- **Safety-first**: Blocked commands/paths, execution timeouts, file size limits, dangerous pattern detection.
- **Modular tools**: Consistent interface, independently testable.
- **Configuration-driven**: YAML/JSON config files control behavior.
- **Auto-cleanup**: Browser and shell processes cleaned up on agent shutdown.
- **Extensible skills**: Drop-in skill directories with standard structure.

## External Dependencies

### Python Packages
- `pyyaml` -- YAML configuration parsing
- `aiohttp` -- Async HTTP client (search, LLM API)
- `aiofiles` -- Async file operations
- `rich` -- Terminal formatting
- `prompt-toolkit` -- Interactive CLI input
- `playwright` -- Browser automation (Chromium)
- `beautifulsoup4` -- HTML parsing for search results
- `Pillow` -- Image generation and analysis
- `PyPDF2` -- PDF text extraction and metadata
- `mutagen` -- Audio file metadata analysis

### System Dependencies (Nix)
- `nspr`, `nss`, `atk`, `cups`, `mesa`, `pango`, `alsa-lib`, `libdrm`, `libxkbcommon` -- Required for Playwright Chromium
- Various Xorg libraries for headless browser

### Data Storage
- SQLite (`data/knowledge_base.db`) -- Agent knowledge base
- JSON (`data/user_profiles.json`) -- User profiles
- JSON (`data/scheduled_tasks.json`) -- Scheduled tasks persistence
- PostgreSQL -- Web UI session/message/tool_execution storage

## Running

The agent runs as a console application:
```
python3 -m agent_core.main
```

Commands: `help`, `status`, `tools`, `history`, `clear`, `plan`, `exit`
