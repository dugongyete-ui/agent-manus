"""Tool Selector - Logika untuk memilih alat berdasarkan niat dan konteks."""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ToolInfo:
    def __init__(self, name: str, description: str, keywords: list[str], enabled: bool = True):
        self.name = name
        self.description = description
        self.keywords = keywords
        self.enabled = enabled

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "keywords": self.keywords,
            "enabled": self.enabled,
        }


TOOL_REGISTRY: list[ToolInfo] = [
    ToolInfo(
        name="shell_tool",
        description="Menjalankan perintah shell di lingkungan sandbox",
        keywords=["shell", "terminal", "command", "bash", "execute", "run", "install", "pip", "npm"],
    ),
    ToolInfo(
        name="file_tool",
        description="Operasi sistem file: baca, tulis, hapus, daftar file",
        keywords=["file", "read", "write", "create", "delete", "directory", "folder", "path"],
    ),
    ToolInfo(
        name="browser_tool",
        description="Interaksi browser web: navigasi, screenshot, klik, formulir",
        keywords=["browser", "web", "url", "navigate", "screenshot", "click", "scrape", "page"],
    ),
    ToolInfo(
        name="search_tool",
        description="Pencarian informasi dari internet",
        keywords=["search", "find", "query", "google", "lookup", "information", "internet"],
    ),
    ToolInfo(
        name="generate_tool",
        description="Generasi media: gambar, video, audio",
        keywords=["generate", "image", "video", "audio", "create", "media", "picture", "photo"],
    ),
    ToolInfo(
        name="slides_tool",
        description="Pembuatan presentasi dan slide",
        keywords=["slides", "presentation", "powerpoint", "pptx", "slide", "deck"],
    ),
    ToolInfo(
        name="webdev_tool",
        description="Inisialisasi dan pengembangan proyek web/mobile",
        keywords=["web", "website", "app", "react", "vue", "flask", "express", "frontend", "backend"],
    ),
    ToolInfo(
        name="schedule_tool",
        description="Penjadwalan dan pengaturan tugas terjadwal",
        keywords=["schedule", "cron", "timer", "recurring", "periodic", "automate"],
    ),
    ToolInfo(
        name="message_tool",
        description="Komunikasi dan pengiriman pesan kepada pengguna",
        keywords=["message", "notify", "send", "communicate", "reply", "respond", "tell"],
    ),
]


class ToolSelector:
    def __init__(self, config_path: Optional[str] = None):
        self.tools = {tool.name: tool for tool in TOOL_REGISTRY}
        self.usage_history: list[dict] = []
        if config_path:
            self._load_config(config_path)

    def _load_config(self, config_path: str):
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
            tool_configs = config.get("tools", {})
            for name, cfg in tool_configs.items():
                if name in self.tools:
                    self.tools[name].enabled = cfg.get("enabled", True)
            logger.info(f"Konfigurasi alat dimuat dari {config_path}")
        except Exception as e:
            logger.warning(f"Gagal memuat konfigurasi alat: {e}")

    def select_tools(self, intent: str, context: Optional[dict] = None, top_k: int = 3) -> list[ToolInfo]:
        intent_lower = intent.lower()
        scored: list[tuple[ToolInfo, float]] = []
        for tool in self.tools.values():
            if not tool.enabled:
                continue
            score = 0.0
            for keyword in tool.keywords:
                if keyword in intent_lower:
                    score += 1.0
            if context:
                context_str = json.dumps(context).lower()
                for keyword in tool.keywords:
                    if keyword in context_str:
                        score += 0.3
            if score > 0:
                scored.append((tool, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        selected = [tool for tool, _ in scored[:top_k]]
        if selected:
            logger.info(f"Alat terpilih untuk '{intent[:50]}': {[t.name for t in selected]}")
        else:
            logger.warning(f"Tidak ada alat cocok untuk: '{intent[:50]}'")
        return selected

    def get_tool(self, name: str) -> Optional[ToolInfo]:
        return self.tools.get(name)

    def list_tools(self) -> list[dict]:
        return [tool.to_dict() for tool in self.tools.values() if tool.enabled]

    def record_usage(self, tool_name: str, success: bool, context: Optional[str] = None):
        import time
        self.usage_history.append({
            "tool": tool_name,
            "success": success,
            "context": context,
            "timestamp": time.time(),
        })
