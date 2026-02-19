#!/bin/bash
set -e

echo "============================================"
echo "  Manus Agent - Auto Setup & Dependencies"
echo "============================================"
echo ""

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_ok() { echo -e "  ${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "  ${YELLOW}[!!]${NC} $1"; }
log_fail() { echo -e "  ${RED}[XX]${NC} $1"; }

echo "--- Step 1: Python Dependencies ---"
pip install --quiet pyyaml aiohttp aiofiles rich prompt-toolkit beautifulsoup4 playwright 2>/dev/null && \
    log_ok "Python packages installed" || log_fail "Python packages failed"

pip install --quiet fastapi uvicorn psycopg2-binary 2>/dev/null && \
    log_ok "Web server packages installed" || log_fail "Web server packages failed"

echo ""
echo "--- Step 2: Playwright Browser ---"
if python3 -c "from playwright.sync_api import sync_playwright" 2>/dev/null; then
    log_ok "Playwright already available"
else
    python3 -m playwright install chromium 2>/dev/null && \
        log_ok "Playwright Chromium installed" || log_warn "Playwright Chromium skipped (optional)"
fi

echo ""
echo "--- Step 3: Directory Structure ---"
mkdir -p data logs config skills sandbox_env agent_core tools web/static web/templates
log_ok "Directories verified"

echo ""
echo "--- Step 4: Data Files ---"
if [ ! -f "data/knowledge_base.db" ]; then
    python3 -c "from agent_core.knowledge_base import KnowledgeBase; KnowledgeBase()" 2>/dev/null && \
        log_ok "Knowledge base initialized" || log_warn "Knowledge base init skipped"
else
    log_ok "Knowledge base exists"
fi

if [ ! -f "data/user_profiles.json" ]; then
    echo '{"profiles":[],"metadata":{"version":"1.0.0"}}' > data/user_profiles.json
    log_ok "User profiles created"
else
    log_ok "User profiles exists"
fi

echo ""
echo "--- Step 5: Verify Core Modules ---"
python3 -c "
modules = [
    ('agent_core.agent_loop', 'AgentLoop'),
    ('agent_core.context_manager', 'ContextManager'),
    ('agent_core.knowledge_base', 'KnowledgeBase'),
    ('agent_core.llm_client', 'LLMClient'),
    ('agent_core.planner', 'Planner'),
    ('agent_core.tool_selector', 'ToolSelector'),
    ('agent_core.user_manager', 'UserManager'),
    ('tools.shell_tool', 'ShellTool'),
    ('tools.file_tool', 'FileTool'),
    ('tools.browser_tool', 'BrowserTool'),
    ('tools.search_tool', 'SearchTool'),
    ('tools.generate_tool', 'GenerateTool'),
    ('tools.slides_tool', 'SlidesTool'),
    ('tools.webdev_tool', 'WebDevTool'),
    ('tools.schedule_tool', 'ScheduleTool'),
    ('tools.message_tool', 'MessageTool'),
    ('sandbox_env.runtime_executor', 'RuntimeExecutor'),
    ('sandbox_env.package_manager', 'PackageManager'),
    ('sandbox_env.vm_manager', 'VMManager'),
]
ok = 0
for mod, cls in modules:
    try:
        m = __import__(mod, fromlist=[cls])
        getattr(m, cls)
        ok += 1
    except Exception as e:
        print(f'  FAIL: {mod}.{cls} - {e}')
print(f'  Modules: {ok}/{len(modules)} verified')
" 2>&1

echo ""
echo "============================================"
echo "  Setup Complete!"
echo "============================================"
echo ""
echo "  Run the agent:  python3 -m agent_core.main"
echo "  Run the web UI:  python3 web/server.py"
echo ""
