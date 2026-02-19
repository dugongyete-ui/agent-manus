"""System Monitor - Memantau kondisi sistem."""

import os
import platform
import subprocess
import time
import logging

logger = logging.getLogger(__name__)


def get_memory_info() -> dict:
    try:
        with open("/proc/meminfo", "r") as f:
            lines = f.readlines()
        mem = {}
        for line in lines:
            parts = line.split(":")
            if len(parts) == 2:
                key = parts[0].strip()
                val = int(parts[1].strip().split()[0])
                mem[key] = val

        total = mem.get("MemTotal", 0)
        available = mem.get("MemAvailable", 0)
        used = total - available
        usage_pct = round(used / max(total, 1) * 100, 1)

        return {
            "total_mb": round(total / 1024, 1),
            "used_mb": round(used / 1024, 1),
            "available_mb": round(available / 1024, 1),
            "usage_percent": usage_pct,
        }
    except Exception as e:
        return {"error": str(e)}


def get_disk_info() -> dict:
    try:
        stat = os.statvfs("/")
        total = stat.f_blocks * stat.f_frsize
        free = stat.f_bfree * stat.f_frsize
        used = total - free
        usage_pct = round(used / max(total, 1) * 100, 1)

        return {
            "total_gb": round(total / (1024 ** 3), 2),
            "used_gb": round(used / (1024 ** 3), 2),
            "free_gb": round(free / (1024 ** 3), 2),
            "usage_percent": usage_pct,
        }
    except Exception as e:
        return {"error": str(e)}


def get_uptime() -> dict:
    try:
        with open("/proc/uptime", "r") as f:
            uptime_seconds = float(f.read().split()[0])
        hours = int(uptime_seconds // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        return {
            "seconds": round(uptime_seconds, 1),
            "formatted": f"{hours}h {minutes}m",
        }
    except Exception as e:
        return {"error": str(e)}


def get_load_average() -> dict:
    try:
        load1, load5, load15 = os.getloadavg()
        return {
            "1min": round(load1, 2),
            "5min": round(load5, 2),
            "15min": round(load15, 2),
        }
    except Exception as e:
        return {"error": str(e)}


def get_system_info() -> dict:
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "hostname": platform.node(),
        "processor": platform.processor() or "N/A",
    }


def get_top_processes(limit: int = 10) -> list[dict]:
    try:
        result = subprocess.run(
            ["ps", "aux", "--sort=-rss"],
            capture_output=True, text=True, timeout=5
        )
        lines = result.stdout.strip().split("\n")
        processes = []
        for line in lines[1:limit + 1]:
            parts = line.split(None, 10)
            if len(parts) >= 11:
                processes.append({
                    "user": parts[0],
                    "pid": parts[1],
                    "cpu_pct": parts[2],
                    "mem_pct": parts[3],
                    "rss_kb": parts[5],
                    "command": parts[10][:80],
                })
        return processes
    except Exception as e:
        return [{"error": str(e)}]


def main(**kwargs) -> dict:
    return {
        "success": True,
        "timestamp": time.time(),
        "system": get_system_info(),
        "memory": get_memory_info(),
        "disk": get_disk_info(),
        "load_average": get_load_average(),
        "uptime": get_uptime(),
        "top_processes": get_top_processes(kwargs.get("process_limit", 10)),
    }


def run(**kwargs):
    return main(**kwargs)


if __name__ == "__main__":
    import json
    result = main()
    print(json.dumps(result, indent=2, ensure_ascii=False))
