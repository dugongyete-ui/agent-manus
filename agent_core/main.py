"""Main - Titik masuk utama, menginisialisasi Agent Loop."""

import asyncio
import logging
import os
import sys
import yaml

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table
from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory

from agent_core.agent_loop import AgentLoop
from agent_core.planner import TaskStatus

console = Console()
logger = logging.getLogger("manus_agent")


def load_config(config_path: str = "config/settings.yaml") -> dict:
    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        console.print(f"[yellow]Konfigurasi tidak ditemukan di {config_path}, menggunakan default.[/yellow]")
        return {
            "agent": {"name": "Manus Agent", "version": "1.0.0", "max_iterations": 50},
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
            logging.StreamHandler(sys.stdout),
        ],
    )

    error_handler = logging.FileHandler(os.path.join(log_dir, "error.log"))
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(log_format))
    logging.getLogger().addHandler(error_handler)


def display_banner(config: dict):
    agent_name = config.get("agent", {}).get("name", "Manus Agent")
    version = config.get("agent", {}).get("version", "1.0.0")

    banner_text = f"""
# {agent_name} v{version}

Agen AI otonom dengan kemampuan:
- **Shell**: Eksekusi perintah terminal
- **File**: Operasi sistem file
- **Browser**: Navigasi dan interaksi web
- **Search**: Pencarian informasi
- **Generate**: Generasi media (gambar, video, audio)
- **Slides**: Pembuatan presentasi
- **WebDev**: Pengembangan web/mobile
- **Schedule**: Penjadwalan tugas
- **Message**: Komunikasi pengguna

Ketik `help` untuk bantuan, `status` untuk status, `exit` untuk keluar.
"""
    console.print(Panel(Markdown(banner_text), border_style="blue", title="🤖 Manus Agent"))


def display_help():
    table = Table(title="Perintah Tersedia", border_style="cyan")
    table.add_column("Perintah", style="green")
    table.add_column("Deskripsi", style="white")

    commands = [
        ("help", "Tampilkan daftar perintah"),
        ("status", "Tampilkan status agen dan rencana tugas"),
        ("tools", "Tampilkan daftar alat yang tersedia"),
        ("history", "Tampilkan riwayat percakapan"),
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
        status = "✅ Aktif" if tool_dict["enabled"] else "❌ Nonaktif"
        table.add_row(tool_dict["name"], tool_dict["description"], status)
    console.print(table)


def display_status(agent: AgentLoop):
    table = Table(title="Status Agen", border_style="yellow")
    table.add_column("Parameter", style="cyan")
    table.add_column("Nilai", style="white")

    table.add_row("State", agent.state)
    table.add_row("Iterasi", str(agent.iteration_count))
    table.add_row("Pesan dalam konteks", str(len(agent.context_manager.messages)))
    table.add_row("Estimasi token", str(agent.context_manager.get_token_estimate()))
    table.add_row("Tugas aktif", str(len(agent.planner.tasks)))

    progress = agent.planner.get_progress()
    table.add_row("Progres tugas", f"{progress['completed']}/{progress['total']} ({progress['percentage']:.0f}%)")

    console.print(table)


async def interactive_loop(agent: AgentLoop):
    session = PromptSession(history=InMemoryHistory())

    while True:
        try:
            user_input = await asyncio.get_event_loop().run_in_executor(
                None, lambda: session.prompt("\n🤖 Manus > ")
            )
            user_input = user_input.strip()

            if not user_input:
                continue

            command = user_input.lower()

            if command in ("exit", "quit", "keluar"):
                console.print("[yellow]Sampai jumpa! 👋[/yellow]")
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

            with console.status("[bold cyan]Memproses...[/bold cyan]"):
                response = await agent.process_request(user_input)

            console.print(Panel(response, border_style="green", title="Respons"))

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
        agent.register_tool_executor(name, instance.execute)

    logger.info("Manus Agent dimulai.")
    await interactive_loop(agent)
    logger.info("Manus Agent dihentikan.")


def run():
    asyncio.run(main())


if __name__ == "__main__":
    run()
