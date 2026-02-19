"""Main - Titik masuk utama, menginisialisasi Agent Loop."""

import asyncio
import logging
import os
import sys
import uuid
import yaml

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table
from rich.live import Live
from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory

from agent_core.agent_loop import AgentLoop
from agent_core.user_manager import UserManager

console = Console()
logger = logging.getLogger("manus_agent")


def load_config(config_path: str = "config/settings.yaml") -> dict:
    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        console.print(f"[yellow]Konfigurasi tidak ditemukan di {config_path}, menggunakan default.[/yellow]")
        return {
            "agent": {"name": "Manus Agent", "version": "1.0.0", "max_iterations": 10},
            "context": {"max_tokens": 128000, "memory_window": 20, "summarization_threshold": 15},
        }


def setup_logging(config: dict):
    log_config = config.get("logging", {})
    log_dir = log_config.get("directory", "logs")
    os.makedirs(log_dir, exist_ok=True)

    log_format = log_config.get("format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    log_level = config.get("agent", {}).get("log_level", "INFO")

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format=log_format,
        handlers=[
            logging.FileHandler(os.path.join(log_dir, "agent_activity.log")),
        ],
    )

    error_handler = logging.FileHandler(os.path.join(log_dir, "error.log"))
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(log_format))
    logging.getLogger().addHandler(error_handler)


def display_banner(config: dict):
    agent_name = config.get("agent", {}).get("name", "Manus Agent")
    version = config.get("agent", {}).get("version", "1.0.0")

    banner_text = f"""# {agent_name} v{version}

Agen AI otonom dengan kemampuan:
- **Shell**: Eksekusi perintah terminal
- **File**: Baca, tulis, edit, lihat file
- **Browser**: Navigasi dan interaksi web
- **Search**: Pencarian informasi
- **Generate**: Generasi media
- **Slides**: Pembuatan presentasi
- **WebDev**: Pengembangan web/mobile
- **Schedule**: Penjadwalan tugas
- **Message**: Komunikasi pengguna

Powered by Dzeck AI API
Ketik `help` untuk bantuan, `exit` untuk keluar."""
    console.print(Panel(Markdown(banner_text), border_style="blue", title="Manus Agent"))


def display_help():
    table = Table(title="Perintah Tersedia", border_style="cyan")
    table.add_column("Perintah", style="green")
    table.add_column("Deskripsi", style="white")

    commands = [
        ("help", "Tampilkan daftar perintah"),
        ("status", "Tampilkan status agen"),
        ("tools", "Tampilkan daftar alat yang tersedia"),
        ("history", "Tampilkan riwayat percakapan"),
        ("knowledge", "Tampilkan statistik knowledge base"),
        ("clear", "Bersihkan konteks percakapan"),
        ("plan", "Tampilkan rencana tugas saat ini"),
        ("exit / quit", "Keluar dari agen"),
    ]
    for cmd, desc in commands:
        table.add_row(cmd, desc)
    console.print(table)


def display_tools(agent: AgentLoop):
    table = Table(title="Alat Tersedia", border_style="green")
    table.add_column("Nama", style="cyan")
    table.add_column("Deskripsi", style="white")
    table.add_column("Status", style="green")

    for tool_dict in agent.tool_selector.list_tools():
        status = "Aktif" if tool_dict["enabled"] else "Nonaktif"
        table.add_row(tool_dict["name"], tool_dict["description"], status)
    console.print(table)


def display_status(agent: AgentLoop):
    table = Table(title="Status Agen", border_style="yellow")
    table.add_column("Parameter", style="cyan")
    table.add_column("Nilai", style="white")

    table.add_row("State", agent.state)
    table.add_row("Iterasi terakhir", str(agent.iteration_count))
    table.add_row("Pesan dalam konteks", str(len(agent.context_manager.messages)))
    table.add_row("Estimasi token", str(agent.context_manager.get_token_estimate()))

    kb_stats = agent.knowledge_base.get_stats()
    table.add_row("Knowledge base entries", str(kb_stats["knowledge_entries"]))
    table.add_row("Tool usage logs", str(kb_stats["tool_usage_logs"]))

    console.print(table)


def display_knowledge(agent: AgentLoop):
    stats = agent.knowledge_base.get_stats()
    table = Table(title="Knowledge Base", border_style="magenta")
    table.add_column("Metrik", style="cyan")
    table.add_column("Nilai", style="white")

    table.add_row("Total entries", str(stats["knowledge_entries"]))
    table.add_row("Kategori", ", ".join(stats["categories"]) if stats["categories"] else "-")
    table.add_row("Ringkasan percakapan", str(stats["conversation_summaries"]))
    table.add_row("Log penggunaan tool", str(stats["tool_usage_logs"]))

    console.print(table)

    tool_stats = agent.knowledge_base.get_tool_usage_stats()
    if tool_stats:
        tool_table = Table(title="Statistik Penggunaan Tool", border_style="cyan")
        tool_table.add_column("Tool", style="green")
        tool_table.add_column("Total", style="white")
        tool_table.add_column("Sukses", style="white")
        tool_table.add_column("Avg Duration", style="white")

        for ts in tool_stats:
            tool_table.add_row(
                ts["tool_name"],
                str(ts["total_calls"]),
                str(ts["success_count"]),
                f"{ts['avg_duration_ms']:.0f}ms",
            )
        console.print(tool_table)


async def interactive_loop(agent: AgentLoop):
    session = PromptSession(history=InMemoryHistory())

    while True:
        try:
            user_input = await asyncio.get_event_loop().run_in_executor(
                None, lambda: session.prompt("\nManus > ")
            )
            user_input = user_input.strip()

            if not user_input:
                continue

            command = user_input.lower()

            if command in ("exit", "quit", "keluar"):
                console.print("[yellow]Sampai jumpa![/yellow]")
                break
            elif command == "help":
                display_help()
                continue
            elif command == "status":
                display_status(agent)
                continue
            elif command == "tools":
                display_tools(agent)
                continue
            elif command == "knowledge":
                display_knowledge(agent)
                continue
            elif command == "history":
                history = agent.context_manager.export_history()
                if not history:
                    console.print("[dim]Belum ada riwayat percakapan.[/dim]")
                else:
                    for msg in history[-10:]:
                        role_color = "green" if msg["role"] == "user" else "blue"
                        console.print(f"[{role_color}][{msg['role']}][/{role_color}]: {msg['content'][:200]}")
                continue
            elif command == "clear":
                agent.context_manager.clear()
                console.print("[green]Konteks percakapan dibersihkan.[/green]")
                continue
            elif command == "plan":
                if agent.planner.tasks:
                    console.print(agent.planner.get_plan_summary())
                else:
                    console.print("[dim]Belum ada rencana tugas.[/dim]")
                continue

            console.print("[bold cyan]Memproses...[/bold cyan]")
            response = await agent.process_request(user_input)
            console.print()
            console.print(Panel(Markdown(response), border_style="green", title="Manus"))

        except KeyboardInterrupt:
            console.print("\n[yellow]Tekan Ctrl+C lagi atau ketik 'exit' untuk keluar.[/yellow]")
        except EOFError:
            break


async def main():
    config = load_config()
    setup_logging(config)
    display_banner(config)

    agent = AgentLoop(config)

    from tools.shell_tool import ShellTool
    from tools.file_tool import FileTool
    from tools.browser_tool import BrowserTool
    from tools.search_tool import SearchTool
    from tools.generate_tool import GenerateTool
    from tools.slides_tool import SlidesTool
    from tools.webdev_tool import WebDevTool
    from tools.schedule_tool import ScheduleTool
    from tools.message_tool import MessageTool

    tool_instances = {
        "shell_tool": ShellTool(),
        "file_tool": FileTool(),
        "browser_tool": BrowserTool(),
        "search_tool": SearchTool(),
        "generate_tool": GenerateTool(),
        "slides_tool": SlidesTool(),
        "webdev_tool": WebDevTool(),
        "schedule_tool": ScheduleTool(),
        "message_tool": MessageTool(),
    }

    for name, instance in tool_instances.items():
        agent.register_tool(name, instance)

    user_manager = UserManager()
    session_user = user_manager.get_or_create_profile("default_user", "User")

    logger.info("Manus Agent dimulai.")

    try:
        await interactive_loop(agent)
    finally:
        user_manager.save()
        await agent.cleanup()
        logger.info("Manus Agent dihentikan.")


def run():
    asyncio.run(main())


if __name__ == "__main__":
    run()
