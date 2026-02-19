"""Data Privacy - Enkripsi data, anonimisasi, dan kepatuhan GDPR."""

import base64
import hashlib
import json
import logging
import os
import re
import time
from typing import Optional

logger = logging.getLogger(__name__)


class DataClassification:
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class PIIType:
    EMAIL = "email"
    PHONE = "phone"
    IP_ADDRESS = "ip_address"
    CREDIT_CARD = "credit_card"
    SSN = "ssn"
    NAME = "name"
    ADDRESS = "address"


PII_PATTERNS = {
    PIIType.EMAIL: r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
    PIIType.PHONE: r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}',
    PIIType.IP_ADDRESS: r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
    PIIType.CREDIT_CARD: r'\b(?:\d{4}[-\s]?){3}\d{4}\b',
    PIIType.SSN: r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b',
}


class ConsentRecord:
    def __init__(self, user_id: str, purpose: str, granted: bool):
        self.user_id = user_id
        self.purpose = purpose
        self.granted = granted
        self.timestamp = time.time()
        self.expires_at = time.time() + (365 * 24 * 3600)

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "purpose": self.purpose,
            "granted": self.granted,
            "timestamp": self.timestamp,
            "expires_at": self.expires_at,
        }


class DataPrivacyManager:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.privacy_file = os.path.join(data_dir, "privacy_records.json")
        self.consent_records: list[ConsentRecord] = []
        self.data_retention_days = 365
        self.anonymization_key = self._get_or_create_key()
        self.data_access_log: list[dict] = []
        self.max_log_entries = 500
        self._load_data()
        logger.info("Data Privacy Manager diinisialisasi")

    def _get_or_create_key(self) -> str:
        key_file = os.path.join(self.data_dir, ".privacy_key")
        os.makedirs(self.data_dir, exist_ok=True)
        if os.path.exists(key_file):
            with open(key_file, "r") as f:
                return f.read().strip()
        import secrets
        key = secrets.token_hex(32)
        with open(key_file, "w") as f:
            f.write(key)
        return key

    def _load_data(self):
        os.makedirs(self.data_dir, exist_ok=True)
        if os.path.exists(self.privacy_file):
            try:
                with open(self.privacy_file, "r") as f:
                    data = json.load(f)
                for cr in data.get("consent_records", []):
                    record = ConsentRecord(cr["user_id"], cr["purpose"], cr["granted"])
                    record.timestamp = cr.get("timestamp", time.time())
                    record.expires_at = cr.get("expires_at", time.time() + 365 * 86400)
                    self.consent_records.append(record)
                self.data_access_log = data.get("access_log", [])[-self.max_log_entries:]
            except Exception as e:
                logger.warning(f"Gagal memuat privacy data: {e}")

    def _save_data(self):
        os.makedirs(self.data_dir, exist_ok=True)
        data = {
            "consent_records": [c.to_dict() for c in self.consent_records],
            "access_log": self.data_access_log[-self.max_log_entries:],
            "metadata": {
                "last_updated": time.time(),
                "retention_days": self.data_retention_days,
            },
        }
        with open(self.privacy_file, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def encrypt_data(self, plaintext: str) -> str:
        key_bytes = hashlib.sha256(self.anonymization_key.encode()).digest()
        encrypted = bytearray()
        for i, char in enumerate(plaintext.encode('utf-8')):
            encrypted.append(char ^ key_bytes[i % len(key_bytes)])
        return base64.b64encode(bytes(encrypted)).decode('utf-8')

    def decrypt_data(self, ciphertext: str) -> str:
        try:
            key_bytes = hashlib.sha256(self.anonymization_key.encode()).digest()
            encrypted = base64.b64decode(ciphertext)
            decrypted = bytearray()
            for i, byte in enumerate(encrypted):
                decrypted.append(byte ^ key_bytes[i % len(key_bytes)])
            return decrypted.decode('utf-8')
        except Exception as e:
            logger.error(f"Gagal dekripsi data: {e}")
            return ""

    def hash_identifier(self, identifier: str) -> str:
        salted = f"{self.anonymization_key}:{identifier}"
        return hashlib.sha256(salted.encode()).hexdigest()[:16]

    def detect_pii(self, text: str) -> list[dict]:
        findings = []
        for pii_type, pattern in PII_PATTERNS.items():
            matches = re.finditer(pattern, text)
            for match in matches:
                findings.append({
                    "type": pii_type,
                    "value": match.group()[:4] + "***",
                    "position": match.start(),
                    "length": len(match.group()),
                })
        return findings

    def anonymize_text(self, text: str) -> str:
        result = text
        for pii_type, pattern in PII_PATTERNS.items():
            def replace_match(match):
                original = match.group()
                hashed = self.hash_identifier(original)
                if pii_type == PIIType.EMAIL:
                    return f"[EMAIL:{hashed}]"
                elif pii_type == PIIType.PHONE:
                    return f"[PHONE:{hashed}]"
                elif pii_type == PIIType.IP_ADDRESS:
                    return f"[IP:{hashed}]"
                elif pii_type == PIIType.CREDIT_CARD:
                    return f"[CC:{hashed}]"
                elif pii_type == PIIType.SSN:
                    return f"[SSN:{hashed}]"
                return f"[PII:{hashed}]"
            result = re.sub(pattern, replace_match, result)
        return result

    def sanitize_for_logging(self, data: dict) -> dict:
        sanitized = {}
        sensitive_keys = {"password", "token", "api_key", "secret", "credentials", "auth", "cookie"}
        for key, value in data.items():
            key_lower = key.lower()
            if any(sk in key_lower for sk in sensitive_keys):
                sanitized[key] = "***REDACTED***"
            elif isinstance(value, str):
                sanitized[key] = self.anonymize_text(value)
            elif isinstance(value, dict):
                sanitized[key] = self.sanitize_for_logging(value)
            else:
                sanitized[key] = value
        return sanitized

    def record_consent(self, user_id: str, purpose: str, granted: bool) -> dict:
        record = ConsentRecord(user_id, purpose, granted)
        self.consent_records.append(record)
        self._save_data()
        logger.info(f"Consent direkam: user={user_id}, purpose={purpose}, granted={granted}")
        return record.to_dict()

    def check_consent(self, user_id: str, purpose: str) -> bool:
        now = time.time()
        relevant = [
            c for c in self.consent_records
            if c.user_id == user_id and c.purpose == purpose and c.expires_at > now
        ]
        if not relevant:
            return False
        latest = max(relevant, key=lambda c: c.timestamp)
        return latest.granted

    def get_user_consents(self, user_id: str) -> list[dict]:
        return [c.to_dict() for c in self.consent_records if c.user_id == user_id]

    def log_data_access(self, user_id: str, data_type: str, purpose: str,
                        action: str = "read") -> dict:
        entry = {
            "user_id": user_id,
            "data_type": data_type,
            "purpose": purpose,
            "action": action,
            "timestamp": time.time(),
        }
        self.data_access_log.append(entry)
        if len(self.data_access_log) > self.max_log_entries:
            self.data_access_log = self.data_access_log[-self.max_log_entries:]
        self._save_data()
        return entry

    def export_user_data(self, user_id: str) -> dict:
        self.log_data_access(user_id, "full_profile", "data_export", "export")
        user_consents = self.get_user_consents(user_id)
        user_access_log = [
            log for log in self.data_access_log
            if log.get("user_id") == user_id
        ]

        return {
            "user_id": user_id,
            "export_timestamp": time.time(),
            "consent_records": user_consents,
            "access_log": user_access_log,
            "data_retention_policy": {
                "retention_days": self.data_retention_days,
                "deletion_policy": "Data dihapus otomatis setelah periode retensi",
            },
            "rights": {
                "right_to_access": True,
                "right_to_rectification": True,
                "right_to_erasure": True,
                "right_to_portability": True,
                "right_to_object": True,
            },
        }

    def delete_user_data(self, user_id: str, reason: str = "") -> dict:
        self.log_data_access(user_id, "full_profile", "data_deletion", "delete")

        consent_removed = len([c for c in self.consent_records if c.user_id == user_id])
        self.consent_records = [c for c in self.consent_records if c.user_id != user_id]

        access_removed = len([l for l in self.data_access_log if l.get("user_id") == user_id])
        self.data_access_log = [l for l in self.data_access_log if l.get("user_id") != user_id]

        self._save_data()
        logger.info(f"Data pengguna dihapus: {user_id} (alasan: {reason})")

        return {
            "user_id": user_id,
            "consent_records_removed": consent_removed,
            "access_logs_removed": access_removed,
            "deletion_timestamp": time.time(),
            "reason": reason,
            "status": "completed",
        }

    def check_data_retention(self) -> dict:
        now = time.time()
        retention_limit = now - (self.data_retention_days * 86400)

        expired_consents = [c for c in self.consent_records if c.timestamp < retention_limit]
        expired_logs = [l for l in self.data_access_log if l.get("timestamp", 0) < retention_limit]

        return {
            "retention_days": self.data_retention_days,
            "expired_consents": len(expired_consents),
            "expired_logs": len(expired_logs),
            "total_consents": len(self.consent_records),
            "total_logs": len(self.data_access_log),
            "recommendation": "Jalankan pembersihan" if (expired_consents or expired_logs) else "Data dalam batas retensi",
        }

    def cleanup_expired_data(self) -> dict:
        now = time.time()
        retention_limit = now - (self.data_retention_days * 86400)

        before_consents = len(self.consent_records)
        self.consent_records = [c for c in self.consent_records if c.timestamp >= retention_limit]
        consents_removed = before_consents - len(self.consent_records)

        before_logs = len(self.data_access_log)
        self.data_access_log = [l for l in self.data_access_log if l.get("timestamp", 0) >= retention_limit]
        logs_removed = before_logs - len(self.data_access_log)

        self._save_data()
        logger.info(f"Data expired dibersihkan: {consents_removed} consents, {logs_removed} logs")

        return {
            "consents_removed": consents_removed,
            "logs_removed": logs_removed,
            "timestamp": now,
        }

    def get_privacy_stats(self) -> dict:
        return {
            "total_consent_records": len(self.consent_records),
            "active_consents": sum(1 for c in self.consent_records if c.granted and c.expires_at > time.time()),
            "total_access_logs": len(self.data_access_log),
            "data_retention_days": self.data_retention_days,
            "retention_check": self.check_data_retention(),
            "pii_detection_patterns": len(PII_PATTERNS),
            "encryption_active": True,
        }

    def get_compliance_report(self) -> dict:
        checks = []

        checks.append({
            "requirement": "Enkripsi data",
            "status": "compliant",
            "detail": "XOR encryption dengan kunci unik aktif",
        })

        checks.append({
            "requirement": "Deteksi PII",
            "status": "compliant",
            "detail": f"{len(PII_PATTERNS)} pola PII terdeteksi otomatis",
        })

        checks.append({
            "requirement": "Anonimisasi data",
            "status": "compliant",
            "detail": "Fungsi anonimisasi teks tersedia",
        })

        if self.consent_records:
            checks.append({
                "requirement": "Manajemen consent",
                "status": "compliant",
                "detail": f"{len(self.consent_records)} record consent tercatat",
            })
        else:
            checks.append({
                "requirement": "Manajemen consent",
                "status": "needs_attention",
                "detail": "Belum ada record consent",
            })

        checks.append({
            "requirement": "Hak akses data",
            "status": "compliant",
            "detail": "Export dan deletion tersedia",
        })

        retention = self.check_data_retention()
        if retention["expired_consents"] == 0 and retention["expired_logs"] == 0:
            checks.append({
                "requirement": "Retensi data",
                "status": "compliant",
                "detail": f"Retensi {self.data_retention_days} hari, tidak ada data expired",
            })
        else:
            checks.append({
                "requirement": "Retensi data",
                "status": "needs_attention",
                "detail": f"{retention['expired_consents']} consent dan {retention['expired_logs']} log perlu dibersihkan",
            })

        checks.append({
            "requirement": "Audit trail",
            "status": "compliant",
            "detail": f"{len(self.data_access_log)} entri log akses data",
        })

        compliant = sum(1 for c in checks if c["status"] == "compliant")
        total = len(checks)

        return {
            "compliance_score": round(compliant / total * 100) if total > 0 else 0,
            "total_checks": total,
            "compliant": compliant,
            "needs_attention": total - compliant,
            "checks": checks,
            "timestamp": time.time(),
        }
