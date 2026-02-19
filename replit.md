# Manus Agent

## Overview

Manus Agent is an autonomous AI agent framework in Python, operating on an iterative loop of Analyze -> Think -> Select -> Execute -> Observe. It features a modular architecture supporting diverse tools for shell operations, file management, browser automation, web search, media generation, presentations, web development scaffolding, task scheduling, skill management, and user messaging. A sandbox environment ensures secure code execution and robust VM lifecycle management. The core vision is to provide an adaptable, intelligent assistant for automating complex workflows and enhancing productivity across various domains.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Agent Core
The `agent_core` module orchestrates the agent's primary functions, managing the iterative reasoning process and interacting with a Language Model for action planning. It integrates self-improvement mechanisms, security management (RBAC, data privacy, PII detection), and an `LLMClient` that supports 16 AI models across 5 categories with robust retry logic and data validation. `ContextManager` handles conversation history, and `KnowledgeBase` provides persistent memory via SQLite. `Planner` facilitates hierarchical task management, and `ToolSelector` dispatches tasks.

### Tools
The `tools` directory contains specialized tools:
- **`ShellTool`**: Secure multi-language shell command execution.
- **`FileTool`**: Comprehensive file system operations and multimodal analysis.
- **`BrowserTool`**: Full browser automation using Playwright/Chromium.
- **`SearchTool`**: Web search via DuckDuckGo with content fetching and caching.
- **`GenerateTool`**: Multimodal content generation (images, SVG, charts, audio, video, documents).
- **`SlidesTool`**: Presentation creation and management.
- **`WebDevTool`**: Web project scaffolding for multiple frameworks.
- **`ScheduleTool`**: Robust task scheduling with persistence and history.
- **`MessageTool`**: Structured user communication.
- **`SkillManager`**: Manages dynamic discovery, loading, and execution of extensible skills.

### Skills System
The `skills` system allows for dynamic extensibility. Each skill is a modular directory with documentation (`SKILL.md`), metadata (`config.json`), and implementation scripts.

### Sandbox Environment
The `sandbox_env` provides a secure, isolated environment. `RuntimeExecutor` handles code execution across runtimes, `PackageManager` manages installations, and `VMManager` controls virtual machine lifecycles.

### Web UI
The web interface uses a FastAPI backend with Jinja2 templates, served on port 5000. It features a dark theme, model selector, and panels for activity, files, tools, schedule, skills, learning insights, and security monitoring. PostgreSQL is used for persistent storage.

### LLM Integration
Supports 16 AI models accessible via public API endpoints, categorized for thinking, reasoning, general, research, and labs. Includes exponential backoff retry logic, data validation against injection, and automatic parameter generation from user input.

### MCP (Model Context Protocol) Integration
A protocol layer with dataclass-based message types, provider adapters for various LLM services (OpenAI, Anthropic, Google), and a registry for model routing. A high-level async client handles chat/complete/stream requests, and a server provides REST-compatible methods. This runs silently in the backend without requiring API keys.

### Key Design Patterns
The system emphasizes asynchronous operations, strong safety measures (command/path blocklists, timeouts, PII detection, RBAC), self-improvement through RLHF and meta-learning, modular tool design, configuration-driven behavior, auto-cleanup, and an extensible skills system.

## External Dependencies

### Python Packages
- `pyyaml`: Configuration parsing.
- `aiohttp`: Asynchronous HTTP client.
- `aiofiles`: Asynchronous file operations.
- `rich`, `prompt-toolkit`: Terminal UI enhancements.
- `playwright`: Headless browser automation.
- `beautifulsoup4`: HTML parsing.
- `Pillow`: Image processing.
- `PyPDF2`: PDF text extraction.
- `mutagen`: Audio file metadata analysis.

### System Dependencies
- **Playwright Chromium dependencies**: Required `nspr`, `nss`, `atk`, `cups`, `mesa`, `pango`, `alsa-lib`, `libdrm`, `libxkbcommon`, and Xorg libraries for headless browser functionality.

### Data Storage
- **SQLite**: For the agent's knowledge base (`knowledge_base.db`).
- **JSON files**: For user profiles (`user_profiles.json`) and scheduled tasks (`scheduled_tasks.json`).
- **PostgreSQL**: Backend database for the web UI, storing sessions, messages, and tool execution logs.