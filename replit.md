# Manus Agent

## Overview

Manus Agent is an autonomous AI agent framework in Python, operating on an iterative loop of Analyze -> Think -> Select -> Execute -> Observe. It features a modular architecture supporting diverse tools for shell operations, file management, browser automation, web search, media generation, presentations, web development scaffolding, task scheduling, skill management, spreadsheet processing, playbook automation, and user messaging. A sandbox environment ensures secure code execution with VM isolation and persistent shell sessions. The core vision is to provide an adaptable, intelligent assistant for automating complex workflows.

## User Preferences

Preferred communication style: Simple, everyday language.
Work autonomously without many questions ("jangan banyak tanya harus lakukan dengan senang hati").

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
- **`SlidesTool`**: Presentation creation with HTML/PPTX export, slide management (update/remove/duplicate/reorder), outline-based creation, and JSON import/export.
- **`WebDevTool`**: Web project scaffolding for multiple frameworks with code iteration (read/write/edit), component creation, API route addition, and ZIP export.
- **`ScheduleTool`**: Robust task scheduling with persistence and history.
- **`MessageTool`**: Structured user communication.
- **`SkillManager`**: Manages dynamic discovery, loading, and execution of extensible skills.
- **`SpreadsheetTool`**: CSV/Excel processing with filter (10+ operators), sort, statistics, pivot tables, formulas (sum/avg/multiply/divide/percentage), search, merge, and JSON conversion.
- **`PlaybookManager`**: Reusable tool execution sequences with variable substitution, dry-run mode, pattern detection from execution history, and automatic playbook generation.

### Skills System
The `skills` system allows for dynamic extensibility. Each skill is a modular directory with documentation (`SKILL.md`), metadata (`config.json`), and implementation scripts.

### Sandbox Environment
- **`VMManager`**: VM lifecycle management with 4 isolation levels (NONE/BASIC/STRICT/MAXIMUM), configurable resource limits (CPU, memory, disk, processes), network policies with domain filtering, snapshot management with automatic cleanup, and execution tracking.
- **`ShellSessionManager`**: Persistent shell sessions with command history, working directory tracking, multiple runtime support (python3, nodejs, bash, ruby, php), and async execution.

### Monitoring System
- **`MetricsCollector`**: Time-series metrics, counters, gauges, and histograms with thread-safe storage.
- **`HealthChecker`**: Registered health checks with critical/non-critical classification.
- **`PerformanceTracker`**: Operation timing with stats, slow operation detection.
- **`RequestLogger`**: HTTP request logging with error tracking and statistics.
- **`SystemMonitor`**: Unified dashboard combining all monitoring components with system info (CPU, memory, disk).

### Testing
- **`TestSuite`**: 25+ async-compatible test cases covering VM, shell, spreadsheet, playbook, webdev, and slides components with detailed result tracking and category-based organization.

### Web Interface
FastAPI server (`web/server.py`) with 50+ API endpoints, PostgreSQL storage, CORS support, streaming chat responses, and automatic request monitoring middleware.

### MCP (Model Context Protocol)
Protocol server for standardized communication with external model providers.

## API Endpoints Summary

### Core
- `GET /api/health` - System health
- `GET /` - Web UI
- `POST /api/chat` - Chat with agent (streaming)

### Sessions
- `GET/POST /api/sessions` - List/create sessions
- `DELETE/PATCH /api/sessions/{id}` - Delete/update session

### VM Management
- `GET /api/vm/list` - List VMs
- `POST /api/vm/create` - Create VM
- `POST /api/vm/{id}/start|stop` - Start/stop VM
- `POST /api/vm/{id}/execute` - Execute command
- `POST /api/vm/{id}/execute_code` - Execute code
- `POST /api/vm/{id}/snapshot` - Create snapshot
- `POST /api/vm/{id}/restore/{snap_id}` - Restore snapshot
- `GET /api/vm/{id}/logs` - VM logs
- `GET /api/vm/stats` - VM statistics

### Shell Sessions
- `POST /api/shell/create` - Create shell session
- `POST /api/shell/{id}/execute` - Execute in session
- `POST /api/shell/{id}/script` - Execute script
- `GET /api/shell/{id}/history` - Command history
- `GET /api/shell/list` - List sessions
- `GET /api/shell/stats` - Shell statistics

### Spreadsheet
- `POST /api/spreadsheet/create` - Create spreadsheet
- `POST /api/spreadsheet/read` - Read spreadsheet
- `POST /api/spreadsheet/stats` - Get statistics
- `POST /api/spreadsheet/filter` - Filter data

### Playbook
- `GET /api/playbook/list` - List playbooks
- `POST /api/playbook/create` - Create playbook
- `POST /api/playbook/{id}/execute` - Execute playbook
- `GET /api/playbook/stats` - Playbook statistics
- `GET /api/playbook/patterns` - Detected patterns

### Monitoring
- `GET /api/monitor/dashboard` - Full dashboard
- `GET /api/monitor/health` - Health checks
- `GET /api/monitor/performance` - Performance stats
- `GET /api/monitor/requests` - Request logs
- `GET /api/monitor/system` - System info

### File Download
- `GET /api/files/list` - List all generated files
- `GET /api/files/download/{filename}` - Download a single file
- `GET /api/files/download-zip` - Download multiple files as ZIP

### Testing
- `POST /api/tests/run` - Run full test suite

## Recent Changes
- 2026-02-20: Added file download API endpoints (single file, ZIP bundle, file listing)
- 2026-02-20: Added real PDF generation using fpdf2 with styled formatting
- 2026-02-20: Frontend now shows download buttons in tool result cards
- 2026-02-20: Fixed spreadsheet_tool and playbook_manager integration in agent loop
- 2026-02-20: Mounted data/generated as static directory for file preview
- 2026-02-20: All 12 tools verified working end-to-end with real execution
- 2026-02-20: Fixed critical bug: Retry-After delay capped at 30s max (was 86400s/24hr)
- 2026-02-20: Added automatic fallback mechanism - rotates through alternate AI models when provider fails
- 2026-02-20: Fixed all 31 LSP diagnostics across 5 files (server, providers, registry, database)
- 2026-02-20: Replaced deprecated FastAPI on_event with modern lifespan context manager
- 2026-02-20: Fixed type annotations, None handling, and duplicate function definitions
- 2026-02-19: Fixed chat sending bug - messages no longer get stuck on send (mobile & desktop)
- 2026-02-19: Added 3-minute timeout protection for stuck streaming requests
- 2026-02-19: Improved streaming endpoint with guaranteed done/error events and try/catch per tool
- 2026-02-19: Added mobile keyboard support (enterkeyhint, blur on send, visual feedback)
- 2026-02-19: Migrated webdev_tool project storage from local to PostgreSQL database
- 2026-02-19: WebDevTool now stores projects in /home/runner/workspace/user_workspace (isolated from main project)
- 2026-02-19: Added SpreadsheetTool with comprehensive CSV/Excel processing
- 2026-02-19: Added PlaybookManager with pattern detection and auto-generation
- 2026-02-19: Enhanced WebDevTool with file operations and ZIP export
- 2026-02-19: Enhanced SlidesTool with PPTX export and slide management
- 2026-02-19: Built testing framework with 25+ test cases (100% pass rate)
- 2026-02-19: Built monitoring system with metrics, health checks, and performance tracking
- 2026-02-19: Integrated all components into server with 50+ API endpoints and monitoring middleware
