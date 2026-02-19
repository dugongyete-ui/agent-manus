"""Security Manager - Audit keamanan, deteksi ancaman, dan logging keamanan."""

import hashlib
import json
import logging
import os
import re
import time
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class ThreatLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SecurityEventType(Enum):
    COMMAND_BLOCKED = "command_blocked"
    PATH_VIOLATION = "path_violation"
    RATE_LIMIT = "rate_limit"
    AUTH_FAILURE = "auth_failure"
    DATA_ACCESS = "data_access"
    INJECTION_ATTEMPT = "injection_attempt"
    FILE_PERMISSION = "file_permission"
    SANDBOX_VIOLATION = "sandbox_violation"
    SUSPICIOUS_PATTERN = "suspicious_pattern"
    POLICY_VIOLATION = "policy_violation"


class SecurityEvent:
    def __init__(self, event_type: SecurityEventType, threat_level: ThreatLevel,
                 description: str, source: str = "", user_id: str = "",
                 details: dict = None):
        self.event_id = f"sec_{int(time.time() * 1000)}_{id(self) % 10000}"
        self.event_type = event_type
        self.threat_level = threat_level
        self.description = description
        self.source = source
        self.user_id = user_id
        self.details = details or {}
        self.timestamp = time.time()
        self.resolved = False

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "threat_level": self.threat_level.value,
            "description": self.description,
            "source": self.source,
            "user_id": self.user_id,
            "details": self.details,
            "timestamp": self.timestamp,
            "resolved": self.resolved,
        }


class SecurityPolicy:
    def __init__(self):
        self.blocked_commands = [
            "rm -rf /", "mkfs", "dd if=/dev/zero", ":(){ :|:& };:",
            "chmod -R 777 /", "wget.*\\|.*sh", "curl.*\\|.*bash",
            "> /dev/sda", "mv /* /dev/null", "shutdown", "reboot",
            "kill -9 -1", "passwd", "useradd", "userdel",
            "iptables -F", "systemctl stop",
        ]
        self.blocked_paths = [
            "/etc/shadow", "/etc/passwd", "/etc/sudoers",
            "/root", "/proc/kcore", "/dev/mem",
            "/boot", "/sys/firmware",
        ]
        self.dangerous_patterns = [
            r"eval\s*\(", r"exec\s*\(", r"__import__\s*\(",
            r"subprocess\.call", r"os\.system\s*\(",
            r"<script>", r"javascript:", r"onerror=",
            r";\s*DROP\s+TABLE", r";\s*DELETE\s+FROM", r"UNION\s+SELECT",
            r"1\s*=\s*1", r"OR\s+1\s*=\s*1",
        ]
        self.max_file_size_mb = 100
        self.max_command_length = 5000
        self.rate_limit_per_minute = 60
        self.session_timeout_minutes = 60
        self.allowed_file_extensions = [
            ".py", ".js", ".ts", ".html", ".css", ".json", ".yaml", ".yml",
            ".md", ".txt", ".csv", ".xml", ".sh", ".bash", ".sql",
            ".jsx", ".tsx", ".vue", ".svelte", ".go", ".rs", ".rb", ".php",
            ".toml", ".ini", ".cfg", ".env", ".gitignore",
        ]
        self.max_upload_size_mb = 50

    def to_dict(self) -> dict:
        return {
            "blocked_commands_count": len(self.blocked_commands),
            "blocked_paths_count": len(self.blocked_paths),
            "dangerous_patterns_count": len(self.dangerous_patterns),
            "max_file_size_mb": self.max_file_size_mb,
            "max_command_length": self.max_command_length,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "session_timeout_minutes": self.session_timeout_minutes,
        }


class RateLimiter:
    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = {}

    def check(self, identifier: str) -> bool:
        now = time.time()
        if identifier not in self.requests:
            self.requests[identifier] = []

        self.requests[identifier] = [
            t for t in self.requests[identifier]
            if now - t < self.window_seconds
        ]

        if len(self.requests[identifier]) >= self.max_requests:
            return False

        self.requests[identifier].append(now)
        return True

    def get_remaining(self, identifier: str) -> int:
        now = time.time()
        if identifier not in self.requests:
            return self.max_requests
        active = [t for t in self.requests[identifier] if now - t < self.window_seconds]
        return max(0, self.max_requests - len(active))


class SecurityManager:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.log_file = os.path.join(data_dir, "security_log.json")
        self.policy = SecurityPolicy()
        self.rate_limiter = RateLimiter(
            max_requests=self.policy.rate_limit_per_minute,
            window_seconds=60,
        )
        self.security_events: list[SecurityEvent] = []
        self.active_sessions: dict[str, dict] = {}
        self.max_events = 1000
        self._load_events()
        logger.info("Security Manager diinisialisasi")

    def _load_events(self):
        os.makedirs(self.data_dir, exist_ok=True)
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file, "r") as f:
                    data = json.load(f)
                for ed in data.get("events", []):
                    event = SecurityEvent(
                        event_type=SecurityEventType(ed["event_type"]),
                        threat_level=ThreatLevel(ed["threat_level"]),
                        description=ed["description"],
                        source=ed.get("source", ""),
                        user_id=ed.get("user_id", ""),
                        details=ed.get("details", {}),
                    )
                    event.event_id = ed["event_id"]
                    event.timestamp = ed["timestamp"]
                    event.resolved = ed.get("resolved", False)
                    self.security_events.append(event)
                logger.info(f"Security events dimuat: {len(self.security_events)}")
            except Exception as e:
                logger.warning(f"Gagal memuat security events: {e}")

    def _save_events(self):
        os.makedirs(self.data_dir, exist_ok=True)
        data = {
            "events": [e.to_dict() for e in self.security_events[-self.max_events:]],
            "metadata": {
                "last_updated": time.time(),
                "total_events": len(self.security_events),
            },
        }
        with open(self.log_file, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def validate_command(self, command: str, user_id: str = "") -> dict:
        if len(command) > self.policy.max_command_length:
            event = self._log_event(
                SecurityEventType.POLICY_VIOLATION, ThreatLevel.MEDIUM,
                f"Perintah terlalu panjang: {len(command)} karakter",
                source="shell_tool", user_id=user_id,
                details={"command_length": len(command)},
            )
            return {"allowed": False, "reason": "Perintah terlalu panjang", "event_id": event.event_id}

        cmd_lower = command.lower().strip()
        for blocked in self.policy.blocked_commands:
            if re.search(blocked, cmd_lower):
                event = self._log_event(
                    SecurityEventType.COMMAND_BLOCKED, ThreatLevel.HIGH,
                    f"Perintah berbahaya diblokir: {command[:100]}",
                    source="shell_tool", user_id=user_id,
                    details={"command": command[:200], "matched_rule": blocked},
                )
                return {"allowed": False, "reason": f"Perintah diblokir (rule: {blocked})", "event_id": event.event_id}

        return {"allowed": True, "reason": "OK"}

    def validate_file_path(self, path: str, operation: str = "read", user_id: str = "") -> dict:
        normalized = os.path.normpath(path)

        for blocked in self.policy.blocked_paths:
            if normalized.startswith(blocked):
                event = self._log_event(
                    SecurityEventType.PATH_VIOLATION, ThreatLevel.HIGH,
                    f"Akses path terlarang: {path}",
                    source="file_tool", user_id=user_id,
                    details={"path": path, "operation": operation, "matched_rule": blocked},
                )
                return {"allowed": False, "reason": f"Path terlarang: {blocked}", "event_id": event.event_id}

        if ".." in path:
            event = self._log_event(
                SecurityEventType.PATH_VIOLATION, ThreatLevel.MEDIUM,
                f"Path traversal terdeteksi: {path}",
                source="file_tool", user_id=user_id,
                details={"path": path, "operation": operation},
            )
            return {"allowed": False, "reason": "Path traversal tidak diizinkan", "event_id": event.event_id}

        return {"allowed": True, "reason": "OK"}

    def validate_input(self, text: str, input_type: str = "general", user_id: str = "") -> dict:
        for pattern in self.policy.dangerous_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                event = self._log_event(
                    SecurityEventType.INJECTION_ATTEMPT, ThreatLevel.HIGH,
                    f"Pola berbahaya terdeteksi dalam {input_type}",
                    source=input_type, user_id=user_id,
                    details={"pattern": pattern, "input_preview": text[:200]},
                )
                return {
                    "safe": False,
                    "reason": f"Pola berbahaya terdeteksi",
                    "event_id": event.event_id,
                    "threat_level": "high",
                }

        return {"safe": True, "reason": "OK"}

    def check_rate_limit(self, user_id: str) -> dict:
        allowed = self.rate_limiter.check(user_id)
        remaining = self.rate_limiter.get_remaining(user_id)

        if not allowed:
            self._log_event(
                SecurityEventType.RATE_LIMIT, ThreatLevel.MEDIUM,
                f"Rate limit tercapai untuk user: {user_id}",
                source="api", user_id=user_id,
            )

        return {
            "allowed": allowed,
            "remaining": remaining,
            "limit": self.rate_limiter.max_requests,
            "window_seconds": self.rate_limiter.window_seconds,
        }

    def _log_event(self, event_type: SecurityEventType, threat_level: ThreatLevel,
                   description: str, source: str = "", user_id: str = "",
                   details: dict = None) -> SecurityEvent:
        event = SecurityEvent(
            event_type=event_type,
            threat_level=threat_level,
            description=description,
            source=source,
            user_id=user_id,
            details=details,
        )
        self.security_events.append(event)

        if len(self.security_events) > self.max_events:
            self.security_events = self.security_events[-self.max_events:]

        self._save_events()

        log_msg = f"[SECURITY] {threat_level.value.upper()}: {description}"
        if threat_level in (ThreatLevel.HIGH, ThreatLevel.CRITICAL):
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

        return event

    def run_audit(self) -> dict:
        findings = []
        score = 100

        sandbox_dir = os.path.join(os.path.dirname(self.data_dir), "sandbox_env")
        if os.path.exists(sandbox_dir):
            findings.append({"check": "Sandbox directory exists", "status": "pass", "severity": "info"})
        else:
            findings.append({"check": "Sandbox directory missing", "status": "warning", "severity": "medium"})
            score -= 10

        config_dir = os.path.join(os.path.dirname(self.data_dir), "config")
        settings_file = os.path.join(config_dir, "settings.yaml")
        if os.path.exists(settings_file):
            try:
                import yaml
                with open(settings_file) as f:
                    config = yaml.safe_load(f)
                if config:
                    findings.append({"check": "Configuration file valid", "status": "pass", "severity": "info"})
                else:
                    findings.append({"check": "Configuration file empty", "status": "warning", "severity": "low"})
                    score -= 5
            except Exception:
                findings.append({"check": "Configuration file invalid", "status": "fail", "severity": "medium"})
                score -= 10

        if self.policy.blocked_commands:
            findings.append({
                "check": f"Command blocklist active ({len(self.policy.blocked_commands)} rules)",
                "status": "pass", "severity": "info",
            })
        else:
            findings.append({"check": "No command blocklist", "status": "fail", "severity": "high"})
            score -= 20

        if self.policy.blocked_paths:
            findings.append({
                "check": f"Path blocklist active ({len(self.policy.blocked_paths)} rules)",
                "status": "pass", "severity": "info",
            })
        else:
            findings.append({"check": "No path blocklist", "status": "fail", "severity": "high"})
            score -= 20

        if self.policy.dangerous_patterns:
            findings.append({
                "check": f"Input validation active ({len(self.policy.dangerous_patterns)} patterns)",
                "status": "pass", "severity": "info",
            })
        else:
            findings.append({"check": "No input validation", "status": "fail", "severity": "critical"})
            score -= 30

        if self.policy.rate_limit_per_minute > 0:
            findings.append({
                "check": f"Rate limiting active ({self.policy.rate_limit_per_minute}/min)",
                "status": "pass", "severity": "info",
            })
        else:
            findings.append({"check": "No rate limiting", "status": "fail", "severity": "high"})
            score -= 15

        recent_events = [e for e in self.security_events if time.time() - e.timestamp < 86400]
        high_severity = [e for e in recent_events if e.threat_level in (ThreatLevel.HIGH, ThreatLevel.CRITICAL)]
        if high_severity:
            findings.append({
                "check": f"{len(high_severity)} high/critical events in last 24h",
                "status": "warning", "severity": "high",
            })
            score -= min(20, len(high_severity) * 5)

        score = max(0, min(100, score))
        if score >= 80:
            grade = "A"
        elif score >= 60:
            grade = "B"
        elif score >= 40:
            grade = "C"
        else:
            grade = "D"

        return {
            "score": score,
            "grade": grade,
            "findings": findings,
            "total_checks": len(findings),
            "passed": sum(1 for f in findings if f["status"] == "pass"),
            "warnings": sum(1 for f in findings if f["status"] == "warning"),
            "failed": sum(1 for f in findings if f["status"] == "fail"),
            "timestamp": time.time(),
            "policy": self.policy.to_dict(),
        }

    def get_security_stats(self) -> dict:
        total = len(self.security_events)
        if total == 0:
            return {
                "total_events": 0,
                "by_type": {},
                "by_level": {},
                "recent_24h": 0,
                "unresolved": 0,
                "policy": self.policy.to_dict(),
            }

        by_type = {}
        by_level = {}
        recent_24h = 0
        unresolved = 0
        now = time.time()

        for event in self.security_events:
            et = event.event_type.value
            tl = event.threat_level.value
            by_type[et] = by_type.get(et, 0) + 1
            by_level[tl] = by_level.get(tl, 0) + 1
            if now - event.timestamp < 86400:
                recent_24h += 1
            if not event.resolved:
                unresolved += 1

        return {
            "total_events": total,
            "by_type": by_type,
            "by_level": by_level,
            "recent_24h": recent_24h,
            "unresolved": unresolved,
            "policy": self.policy.to_dict(),
        }

    def get_recent_events(self, limit: int = 50, threat_level: Optional[str] = None) -> list[dict]:
        events = self.security_events[-limit:]
        if threat_level:
            try:
                level = ThreatLevel(threat_level)
                events = [e for e in events if e.threat_level == level]
            except ValueError:
                pass
        return [e.to_dict() for e in reversed(events)]

    def resolve_event(self, event_id: str) -> bool:
        for event in self.security_events:
            if event.event_id == event_id:
                event.resolved = True
                self._save_events()
                return True
        return False
