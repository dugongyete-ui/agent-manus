# Manus Agent

## Overview

Manus Agent is an AI agent framework built in Python that follows an iterative agent loop pattern (Analyze → Think → Select → Execute → Observe). It provides a modular architecture where the agent can use various tools (shell, file operations, browser automation, web search, media generation, presentations, web development scaffolding, task scheduling, and user messaging) to accomplish tasks requested by users. The project includes a sandbox environment for safe code execution and VM lifecycle management.

The codebase is primarily in Indonesian (variable names, comments, log messages), reflecting its origin. All modules are fully implemented with working logic.

## User Preferences

Preferred communication style: Simple, everyday language.

## Project Structure

```
/home/runner/workspace/
├── agent_core/                   # Core Agent Loop logic and context management
│   ├── __init__.py
│   ├── main.py                   # Entry point, initializes Agent Loop with CLI
│   ├── agent_loop.py             # Agent Loop (Analyze, Think, Select, Execute, Observe)
│   ├── context_manager.py        # Conversation context and memory management
│   ├── tool_selector.py          # Tool selection based on intent and keywords
│   └── planner.py                # Task plan creation and management
├── tools/                        # Tool implementations callable by agent
│   ├── __init__.py
│   ├── shell_tool.py             # Shell command execution wrapper
│   ├── file_tool.py              # File system operations wrapper
│   ├── browser_tool.py           # Browser interaction wrapper (Chromium)
│   ├── search_tool.py            # External search API wrapper
│   ├── generate_tool.py          # Media generation wrapper (image, video, audio)
│   ├── slides_tool.py            # Presentation creation logic
│   ├── webdev_tool.py            # Web/mobile project scaffolding
│   ├── schedule_tool.py          # Task scheduling logic
│   └── message_tool.py           # User communication logic
├── skills/                       # Extensible skills directory
│   ├── skill_creator/            # Skill for creating/updating other skills
│   │   ├── SKILL.md
│   │   └── scripts/create_skill.py
│   └── another_skill/            # Example additional skill
│       └── SKILL.md
├── sandbox_env/                  # Sandbox environment management
│   ├── __init__.py
│   ├── vm_manager.py             # VM lifecycle management (start, stop, snapshot)
│   ├── package_manager.py        # Package installation (pip, npm, yarn)
│   └── runtime_executor.py       # Multi-runtime code execution
├── config/                       # Global configuration files
│   ├── settings.yaml             # System settings
│   └── tool_configs.json         # Per-tool configuration
├── logs/                         # System and agent activity logs
├── data/                         # Persistent data
│   ├── knowledge_base.db         # Agent knowledge base (SQLite)
│   └── user_profiles.json        # User profiles and preferences
└── pyproject.toml                # Python dependencies
```

## System Architecture

### Agent Core (`agent_core/`)
- **AgentLoop** (`agent_loop.py`): Orchestrates the main loop with LLM-powered reasoning. Sends context to Dzeck AI API, parses JSON action responses, executes tools, and observes results iteratively. Max iterations: 10.
- **LLMClient** (`llm_client.py`): Connects to Dzeck AI streaming API (SSE format). Supports streaming and non-streaming chat, system prompts, and multi-message context.
- **ContextManager** (`context_manager.py`): Manages conversation history with token limits (128K), sliding memory window (20 messages), and auto-summarization (threshold: 15).
- **KnowledgeBase** (`knowledge_base.py`): SQLite-based persistent memory. Stores knowledge entries (category/key/value), conversation summaries, and tool usage logs with statistics.
- **UserManager** (`user_manager.py`): JSON-based user profile management with preferences, interaction tracking, and persistence.
- **Planner** (`planner.py`): Task plans with priorities, statuses (PENDING → IN_PROGRESS → COMPLETED/FAILED/CANCELLED), hierarchical subtasks.
- **ToolSelector** (`tool_selector.py`): Keyword-based tool selection from a registry of 9 tools.
- **Main** (`main.py`): CLI entry point using `rich` and `prompt_toolkit`. Registers all tools, manages user sessions.

### Tools (`tools/`)
| Tool | Purpose |
|------|---------|
| `ShellTool` | Shell commands with safety blocklist |
| `FileTool` | File CRUD with path validation and size limits |
| `BrowserTool` | Browser automation (navigate, screenshot, click) |
| `SearchTool` | Web search with result caching |
| `GenerateTool` | Media generation (image, video, audio) |
| `SlidesTool` | Presentation creation with slide/layout models |
| `WebDevTool` | Project scaffolding (React, Vue, Flask, Express, Next.js) |
| `ScheduleTool` | Task scheduling with intervals and callbacks |
| `MessageTool` | User communication with typed messages |

### Sandbox Environment (`sandbox_env/`)
- **RuntimeExecutor**: Code execution in Python, Node.js, Bash, Ruby, PHP with timeouts.
- **PackageManager**: Package installation via pip, npm, yarn.
- **VMManager**: VM lifecycle management (start, stop, pause, snapshot, restore).

### Key Design Patterns
- **Async throughout**: All tools and agent loop use `async/await`.
- **Safety-first**: Blocked commands/paths, execution timeouts, file size limits.
- **Modular tools**: Consistent interface, independently testable.
- **Configuration-driven**: YAML/JSON config files control behavior.

## External Dependencies

### Python Packages
- `pyyaml` — YAML configuration parsing
- `aiohttp` — Async HTTP client
- `aiofiles` — Async file operations
- `rich` — Terminal formatting
- `prompt-toolkit` — Interactive CLI input

### Data Storage
- SQLite (`data/knowledge_base.db`) — Agent knowledge base
- JSON (`data/user_profiles.json`) — User profiles

## Running

The agent runs as a console application:
```
python3 -m agent_core.main
```

Commands: `help`, `status`, `tools`, `history`, `clear`, `plan`, `exit`
