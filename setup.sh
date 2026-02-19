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

echo "--- Step 1: Python Dependencies (parallel install) ---"

ALL_PACKAGES="pyyaml aiohttp aiofiles rich prompt-toolkit beautifulsoup4 playwright Pillow PyPDF2 mutagen fastapi uvicorn psycopg2-binary jinja2 python-multipart"

pip install --quiet --no-warn-script-location $ALL_PACKAGES 2>/dev/null && \
    log_ok "All Python packages installed" || {
    log_warn "Batch install had issues, trying individually..."
    for pkg in $ALL_PACKAGES; do
        pip install --quiet --no-warn-script-location "$pkg" 2>/dev/null && \
            log_ok "$pkg" || log_warn "$pkg skipped"
    done
}

echo ""
echo "--- Step 2: Auto-detect & Install Missing Modules ---"
python3 -c "
import importlib, subprocess, sys

checks = {
    'yaml': 'pyyaml',
    'aiohttp': 'aiohttp',
    'aiofiles': 'aiofiles',
    'rich': 'rich',
    'prompt_toolkit': 'prompt-toolkit',
    'bs4': 'beautifulsoup4',
    'playwright': 'playwright',
    'PIL': 'Pillow',
    'PyPDF2': 'PyPDF2',
    'mutagen': 'mutagen',
    'fastapi': 'fastapi',
    'uvicorn': 'uvicorn',
    'psycopg2': 'psycopg2-binary',
    'jinja2': 'jinja2',
}

missing = []
for mod, pkg in checks.items():
    try:
        importlib.import_module(mod)
    except ImportError:
        missing.append(pkg)

if missing:
    print(f'  Installing missing: {', '.join(missing)}')
    subprocess.check_call(
        [sys.executable, '-m', 'pip', 'install', '--quiet', '--no-warn-script-location'] + missing,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    print(f'  Installed {len(missing)} missing packages')
else:
    print('  All modules present')
" 2>&1

echo ""
echo "--- Step 3: Playwright Browser ---"
if python3 -c "from playwright.sync_api import sync_playwright" 2>/dev/null; then
    log_ok "Playwright already available"
else
    python3 -m playwright install chromium 2>/dev/null && \
        log_ok "Playwright Chromium installed" || log_warn "Playwright Chromium skipped (optional)"
fi

echo ""
echo "--- Step 4: Directory Structure ---"
mkdir -p data logs config skills sandbox_env agent_core tools web/static/css web/static/js web/templates mcp
log_ok "Directories verified"

echo ""
echo "--- Step 5: Data Files ---"
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

if [ ! -f "config/tool_configs.json" ]; then
    echo '{}' > config/tool_configs.json
    log_ok "Tool configs created"
else
    log_ok "Tool configs exists"
fi

if [ ! -f "config/settings.yaml" ]; then
    cat > config/settings.yaml << 'YAML'
agent:
  max_iterations: 10
context:
  max_tokens: 128000
  memory_window: 20
  summarization_threshold: 15
YAML
    log_ok "Settings created"
else
    log_ok "Settings exists"
fi

echo ""
echo "--- Step 6: Verify Core Modules ---"
python3 -c "
modules = [
    ('agent_core.agent_loop', 'AgentLoop'),
    ('agent_core.context_manager', 'ContextManager'),
    ('agent_core.knowledge_base', 'KnowledgeBase'),
    ('agent_core.llm_client', 'LLMClient'),
    ('agent_core.planner', 'Planner'),
    ('agent_core.tool_selector', 'ToolSelector'),
    ('agent_core.user_manager', 'UserManager'),
    ('agent_core.rlhf_engine', 'RLHFEngine'),
    ('agent_core.meta_learner', 'MetaLearner'),
    ('agent_core.security_manager', 'SecurityManager'),
    ('agent_core.access_control', 'AccessControl'),
    ('agent_core.data_privacy', 'DataPrivacyManager'),
    ('tools.shell_tool', 'ShellTool'),
    ('tools.file_tool', 'FileTool'),
    ('tools.browser_tool', 'BrowserTool'),
    ('tools.search_tool', 'SearchTool'),
    ('tools.generate_tool', 'GenerateTool'),
    ('tools.slides_tool', 'SlidesTool'),
    ('tools.webdev_tool', 'WebDevTool'),
    ('tools.schedule_tool', 'ScheduleTool'),
    ('tools.message_tool', 'MessageTool'),
    ('tools.skill_manager', 'SkillManager'),
    ('sandbox_env.runtime_executor', 'RuntimeExecutor'),
    ('sandbox_env.package_manager', 'PackageManager'),
    ('sandbox_env.vm_manager', 'VMManager'),
    ('mcp.client', 'MCPClient'),
    ('mcp.server', 'MCPServer'),
    ('mcp.registry', 'create_default_registry'),
    ('mcp.protocol', 'MCPMessage'),
    ('mcp.providers', 'MCPProviderAdapter'),
    ('mcp.transport', 'StdioTransport'),
]
ok = 0
fail = 0
for mod, cls in modules:
    try:
        m = __import__(mod, fromlist=[cls])
        getattr(m, cls)
        ok += 1
    except Exception as e:
        fail += 1
        print(f'  FAIL: {mod}.{cls} - {e}')
print(f'  Modules: {ok}/{len(modules)} verified ({fail} failed)')
" 2>&1

echo ""
echo "--- Step 7: Quick Server Test ---"
python3 -c "
from web.server import app
print('  FastAPI app loaded successfully')
print(f'  Routes: {len(app.routes)} endpoints')
" 2>&1 && log_ok "Server verified" || log_warn "Server check skipped"

echo ""
echo "============================================"
echo "  Setup Complete!"
echo "============================================"
echo ""
echo "  Run the agent:  python3 -m agent_core.main"
echo "  Run the web UI:  python3 web/server.py"
echo ""
