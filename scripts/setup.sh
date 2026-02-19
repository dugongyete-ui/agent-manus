#!/bin/bash
set -e

echo "=== Manus Agent - Setup Cepat ==="
echo ""

check_cmd() {
    command -v "$1" >/dev/null 2>&1
}

install_python_deps() {
    echo "[1/3] Menginstall Python dependencies..."
    if check_cmd uv; then
        uv pip install --system --quiet \
            aiofiles aiohttp beautifulsoup4 fastapi uvicorn \
            Pillow PyPDF2 mutagen pyyaml rich prompt-toolkit \
            psycopg2-binary 2>/dev/null || \
        uv sync --quiet 2>/dev/null || \
        pip install --quiet --no-warn-script-location \
            aiofiles aiohttp beautifulsoup4 fastapi uvicorn \
            Pillow PyPDF2 mutagen pyyaml rich prompt-toolkit \
            psycopg2-binary
    else
        pip install --quiet --no-warn-script-location \
            aiofiles aiohttp beautifulsoup4 fastapi uvicorn \
            Pillow PyPDF2 mutagen pyyaml rich prompt-toolkit \
            psycopg2-binary
    fi
    echo "    Python dependencies terinstall."
}

install_playwright() {
    echo "[2/3] Memeriksa Playwright..."
    if python3 -c "import playwright" 2>/dev/null; then
        if [ -d "$HOME/.cache/ms-playwright" ] && [ "$(ls -A $HOME/.cache/ms-playwright 2>/dev/null)" ]; then
            echo "    Playwright sudah terinstall, skip."
            return
        fi
    fi
    pip install --quiet --no-warn-script-location playwright
    python3 -m playwright install chromium 2>/dev/null || echo "    Playwright chromium skip (opsional)"
    echo "    Playwright siap."
}

verify_setup() {
    echo "[3/3] Verifikasi..."
    python3 -c "
import sys
modules = {
    'aiohttp': 'aiohttp',
    'aiofiles': 'aiofiles',
    'bs4': 'beautifulsoup4',
    'fastapi': 'fastapi',
    'uvicorn': 'uvicorn',
    'PIL': 'Pillow',
    'PyPDF2': 'PyPDF2',
    'mutagen': 'mutagen',
    'yaml': 'pyyaml',
    'rich': 'rich',
}
ok = 0
fail = 0
for mod, name in modules.items():
    try:
        __import__(mod)
        ok += 1
    except ImportError:
        print(f'    MISSING: {name}')
        fail += 1
print(f'    {ok}/{ok+fail} packages OK')
if fail > 0:
    sys.exit(1)
"
    echo ""
    echo "=== Setup selesai! ==="
    echo "Jalankan: python3 web/server.py"
}

install_python_deps
install_playwright
verify_setup
