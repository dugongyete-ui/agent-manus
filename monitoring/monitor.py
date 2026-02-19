"""Monitoring & Logging System - Metrik, health check, dan performance tracking."""

import json
import logging
import os
import time
import threading
from typing import Optional
from collections import defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class MetricPoint:
    name: str
    value: float
    timestamp: float
    tags: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "timestamp": self.timestamp,
            "tags": self.tags,
        }


class MetricsCollector:
    def __init__(self, max_points: int = 10000):
        self.max_points = max_points
        self._metrics: dict[str, list[MetricPoint]] = defaultdict(list)
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def record(self, name: str, value: float, tags: Optional[dict] = None):
        with self._lock:
            point = MetricPoint(name=name, value=value, timestamp=time.time(), tags=tags or {})
            self._metrics[name].append(point)
            if len(self._metrics[name]) > self.max_points:
                self._metrics[name] = self._metrics[name][-self.max_points:]

    def increment(self, name: str, value: float = 1.0):
        with self._lock:
            self._counters[name] += value

    def gauge(self, name: str, value: float):
        with self._lock:
            self._gauges[name] = value

    def histogram(self, name: str, value: float):
        with self._lock:
            self._histograms[name].append(value)
            if len(self._histograms[name]) > self.max_points:
                self._histograms[name] = self._histograms[name][-self.max_points:]

    def get_metric(self, name: str, last_n: int = 100) -> list[dict]:
        with self._lock:
            points = self._metrics.get(name, [])[-last_n:]
            return [p.to_dict() for p in points]

    def get_counter(self, name: str) -> float:
        return self._counters.get(name, 0)

    def get_gauge(self, name: str) -> Optional[float]:
        return self._gauges.get(name)

    def get_histogram_stats(self, name: str) -> dict:
        with self._lock:
            values = self._histograms.get(name, [])
            if not values:
                return {"count": 0}

            sorted_vals = sorted(values)
            n = len(sorted_vals)
            return {
                "count": n,
                "min": sorted_vals[0],
                "max": sorted_vals[-1],
                "mean": round(sum(sorted_vals) / n, 4),
                "median": sorted_vals[n // 2],
                "p95": sorted_vals[int(n * 0.95)] if n >= 20 else sorted_vals[-1],
                "p99": sorted_vals[int(n * 0.99)] if n >= 100 else sorted_vals[-1],
            }

    def get_all_counters(self) -> dict:
        return dict(self._counters)

    def get_all_gauges(self) -> dict:
        return dict(self._gauges)

    def get_summary(self) -> dict:
        return {
            "metric_series": len(self._metrics),
            "counters": len(self._counters),
            "gauges": len(self._gauges),
            "histograms": len(self._histograms),
            "total_points": sum(len(v) for v in self._metrics.values()),
        }


class HealthChecker:
    def __init__(self):
        self._checks: dict[str, dict] = {}
        self._results: dict[str, dict] = {}

    def register_check(self, name: str, check_fn, critical: bool = False):
        self._checks[name] = {"fn": check_fn, "critical": critical}

    async def run_checks(self) -> dict:
        results = {}
        overall = "healthy"

        for name, check in self._checks.items():
            start = time.time()
            try:
                result = check["fn"]()
                if hasattr(result, "__await__"):
                    result = await result
                results[name] = {
                    "status": "healthy",
                    "duration": round(time.time() - start, 3),
                    "details": result,
                }
            except Exception as e:
                status = "critical" if check["critical"] else "degraded"
                results[name] = {
                    "status": status,
                    "duration": round(time.time() - start, 3),
                    "error": str(e),
                }
                if check["critical"]:
                    overall = "critical"
                elif overall != "critical":
                    overall = "degraded"

        self._results = results
        return {
            "status": overall,
            "checks": results,
            "timestamp": time.time(),
        }

    def get_last_results(self) -> dict:
        return {"checks": self._results}


class PerformanceTracker:
    def __init__(self):
        self._timings: dict[str, list[dict]] = defaultdict(list)
        self._active_timers: dict[str, float] = {}
        self._max_entries = 1000

    def start_timer(self, operation: str) -> str:
        timer_id = f"{operation}_{time.time()}"
        self._active_timers[timer_id] = time.time()
        return timer_id

    def stop_timer(self, timer_id: str, metadata: Optional[dict] = None) -> Optional[dict]:
        start_time = self._active_timers.pop(timer_id, None)
        if start_time is None:
            return None

        duration = time.time() - start_time
        operation = timer_id.rsplit("_", 1)[0]

        entry = {
            "operation": operation,
            "duration": round(duration, 4),
            "timestamp": time.time(),
            "metadata": metadata or {},
        }

        self._timings[operation].append(entry)
        if len(self._timings[operation]) > self._max_entries:
            self._timings[operation] = self._timings[operation][-self._max_entries:]

        return entry

    def record_timing(self, operation: str, duration: float, metadata: Optional[dict] = None):
        entry = {
            "operation": operation,
            "duration": round(duration, 4),
            "timestamp": time.time(),
            "metadata": metadata or {},
        }
        self._timings[operation].append(entry)
        if len(self._timings[operation]) > self._max_entries:
            self._timings[operation] = self._timings[operation][-self._max_entries:]

    def get_stats(self, operation: Optional[str] = None) -> dict:
        if operation:
            entries = self._timings.get(operation, [])
            if not entries:
                return {"operation": operation, "count": 0}
            durations = [e["duration"] for e in entries]
            return {
                "operation": operation,
                "count": len(durations),
                "min": round(min(durations), 4),
                "max": round(max(durations), 4),
                "mean": round(sum(durations) / len(durations), 4),
                "total": round(sum(durations), 4),
            }

        all_stats = {}
        for op in self._timings:
            all_stats[op] = self.get_stats(op)
        return all_stats

    def get_recent(self, operation: Optional[str] = None, limit: int = 20) -> list[dict]:
        if operation:
            return self._timings.get(operation, [])[-limit:]
        all_recent = []
        for entries in self._timings.values():
            all_recent.extend(entries[-limit:])
        all_recent.sort(key=lambda x: x["timestamp"], reverse=True)
        return all_recent[:limit]

    def get_slow_operations(self, threshold: float = 5.0, limit: int = 20) -> list[dict]:
        slow = []
        for entries in self._timings.values():
            for e in entries:
                if e["duration"] >= threshold:
                    slow.append(e)
        slow.sort(key=lambda x: x["duration"], reverse=True)
        return slow[:limit]


class RequestLogger:
    def __init__(self, max_entries: int = 500):
        self.max_entries = max_entries
        self._entries: list[dict] = []
        self._error_entries: list[dict] = []

    def log_request(self, method: str, path: str, status_code: int,
                    duration: float, user_id: Optional[str] = None,
                    error: Optional[str] = None):
        entry = {
            "method": method,
            "path": path,
            "status_code": status_code,
            "duration": round(duration, 4),
            "timestamp": time.time(),
            "user_id": user_id,
        }
        self._entries.append(entry)
        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries:]

        if error or status_code >= 400:
            entry["error"] = error
            self._error_entries.append(entry)
            if len(self._error_entries) > self.max_entries:
                self._error_entries = self._error_entries[-self.max_entries:]

    def get_recent(self, limit: int = 50) -> list[dict]:
        return self._entries[-limit:]

    def get_errors(self, limit: int = 50) -> list[dict]:
        return self._error_entries[-limit:]

    def get_stats(self) -> dict:
        if not self._entries:
            return {"total": 0}

        total = len(self._entries)
        errors = len(self._error_entries)
        durations = [e["duration"] for e in self._entries]

        status_codes = defaultdict(int)
        paths = defaultdict(int)
        for e in self._entries:
            status_codes[str(e["status_code"])] += 1
            paths[e["path"]] += 1

        return {
            "total_requests": total,
            "error_count": errors,
            "error_rate": round(errors / total * 100, 2) if total > 0 else 0,
            "avg_duration": round(sum(durations) / len(durations), 4),
            "p95_duration": round(sorted(durations)[int(len(durations) * 0.95)], 4) if len(durations) >= 20 else round(max(durations), 4),
            "status_codes": dict(status_codes),
            "top_paths": dict(sorted(paths.items(), key=lambda x: x[1], reverse=True)[:10]),
        }


class SystemMonitor:
    def __init__(self):
        self.metrics = MetricsCollector()
        self.health = HealthChecker()
        self.performance = PerformanceTracker()
        self.request_logger = RequestLogger()
        self._start_time = time.time()

    def get_system_info(self) -> dict:
        import platform
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            return {
                "platform": platform.system(),
                "python_version": platform.python_version(),
                "uptime": round(time.time() - self._start_time, 2),
                "cpu_percent": cpu,
                "memory_used_mb": round(mem.used / (1024 * 1024)),
                "memory_total_mb": round(mem.total / (1024 * 1024)),
                "memory_percent": mem.percent,
                "disk_used_gb": round(disk.used / (1024 * 1024 * 1024), 2),
                "disk_total_gb": round(disk.total / (1024 * 1024 * 1024), 2),
            }
        except ImportError:
            return {
                "platform": platform.system(),
                "python_version": platform.python_version(),
                "uptime": round(time.time() - self._start_time, 2),
            }

    def get_dashboard(self) -> dict:
        return {
            "system": self.get_system_info(),
            "metrics_summary": self.metrics.get_summary(),
            "counters": self.metrics.get_all_counters(),
            "gauges": self.metrics.get_all_gauges(),
            "performance": self.performance.get_stats(),
            "requests": self.request_logger.get_stats(),
            "timestamp": time.time(),
        }


monitor = SystemMonitor()
