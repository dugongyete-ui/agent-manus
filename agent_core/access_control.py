"""Access Control - Kontrol akses berbasis peran (RBAC) untuk Manus Agent."""

import hashlib
import json
import logging
import os
import secrets
import time
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class Role(Enum):
    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"


class Permission(Enum):
    EXECUTE_TOOL = "execute_tool"
    READ_FILE = "read_file"
    WRITE_FILE = "write_file"
    DELETE_FILE = "delete_file"
    SHELL_COMMAND = "shell_command"
    BROWSER_ACCESS = "browser_access"
    WEB_SEARCH = "web_search"
    MANAGE_USERS = "manage_users"
    VIEW_LOGS = "view_logs"
    MANAGE_SECURITY = "manage_security"
    MANAGE_SCHEDULE = "manage_schedule"
    MANAGE_SKILLS = "manage_skills"
    VIEW_ACTIVITY = "view_activity"
    SEND_MESSAGE = "send_message"
    GENERATE_MEDIA = "generate_media"
    VIEW_ANALYTICS = "view_analytics"
    MANAGE_SETTINGS = "manage_settings"


ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.ADMIN: set(Permission),
    Role.USER: {
        Permission.EXECUTE_TOOL,
        Permission.READ_FILE,
        Permission.WRITE_FILE,
        Permission.SHELL_COMMAND,
        Permission.BROWSER_ACCESS,
        Permission.WEB_SEARCH,
        Permission.VIEW_LOGS,
        Permission.MANAGE_SCHEDULE,
        Permission.MANAGE_SKILLS,
        Permission.VIEW_ACTIVITY,
        Permission.SEND_MESSAGE,
        Permission.GENERATE_MEDIA,
        Permission.VIEW_ANALYTICS,
    },
    Role.VIEWER: {
        Permission.READ_FILE,
        Permission.VIEW_LOGS,
        Permission.VIEW_ACTIVITY,
        Permission.VIEW_ANALYTICS,
    },
}


class UserAccount:
    def __init__(self, user_id: str, username: str, role: Role,
                 password_hash: str = "", api_key: str = ""):
        self.user_id = user_id
        self.username = username
        self.role = role
        self.password_hash = password_hash
        self.api_key = api_key or secrets.token_hex(32)
        self.is_active = True
        self.created_at = time.time()
        self.last_login = 0.0
        self.login_count = 0
        self.failed_attempts = 0
        self.locked_until = 0.0
        self.custom_permissions: set[str] = set()
        self.denied_permissions: set[str] = set()

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "role": self.role.value,
            "api_key": self.api_key,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "last_login": self.last_login,
            "login_count": self.login_count,
            "failed_attempts": self.failed_attempts,
            "locked_until": self.locked_until,
            "custom_permissions": list(self.custom_permissions),
            "denied_permissions": list(self.denied_permissions),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UserAccount":
        account = cls(
            user_id=data["user_id"],
            username=data["username"],
            role=Role(data.get("role", "user")),
            password_hash=data.get("password_hash", ""),
            api_key=data.get("api_key", ""),
        )
        account.is_active = data.get("is_active", True)
        account.created_at = data.get("created_at", time.time())
        account.last_login = data.get("last_login", 0)
        account.login_count = data.get("login_count", 0)
        account.failed_attempts = data.get("failed_attempts", 0)
        account.locked_until = data.get("locked_until", 0)
        account.custom_permissions = set(data.get("custom_permissions", []))
        account.denied_permissions = set(data.get("denied_permissions", []))
        return account


class Session:
    def __init__(self, session_id: str, user_id: str, token: str):
        self.session_id = session_id
        self.user_id = user_id
        self.token = token
        self.created_at = time.time()
        self.expires_at = time.time() + 3600
        self.last_activity = time.time()
        self.is_valid = True

    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    def refresh(self, duration: int = 3600):
        self.expires_at = time.time() + duration
        self.last_activity = time.time()

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "last_activity": self.last_activity,
            "is_valid": self.is_valid,
        }


class AccessControl:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.accounts_file = os.path.join(data_dir, "access_accounts.json")
        self.accounts: dict[str, UserAccount] = {}
        self.sessions: dict[str, Session] = {}
        self.max_failed_attempts = 5
        self.lockout_duration = 300
        self.session_duration = 3600
        self._load_accounts()
        self._ensure_default_admin()
        logger.info("Access Control diinisialisasi")

    def _load_accounts(self):
        os.makedirs(self.data_dir, exist_ok=True)
        if os.path.exists(self.accounts_file):
            try:
                with open(self.accounts_file, "r") as f:
                    data = json.load(f)
                for acc_data in data.get("accounts", []):
                    account = UserAccount.from_dict(acc_data)
                    account.password_hash = acc_data.get("password_hash", "")
                    self.accounts[account.user_id] = account
                logger.info(f"{len(self.accounts)} akun dimuat")
            except Exception as e:
                logger.warning(f"Gagal memuat akun: {e}")

    def _save_accounts(self):
        os.makedirs(self.data_dir, exist_ok=True)
        data = {
            "accounts": [],
            "metadata": {"last_updated": time.time(), "total_accounts": len(self.accounts)},
        }
        for acc in self.accounts.values():
            acc_dict = acc.to_dict()
            acc_dict["password_hash"] = acc.password_hash
            data["accounts"].append(acc_dict)
        with open(self.accounts_file, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _ensure_default_admin(self):
        if not self.accounts:
            admin = UserAccount(
                user_id="admin_001",
                username="admin",
                role=Role.ADMIN,
                password_hash=self._hash_password("admin"),
            )
            self.accounts[admin.user_id] = admin
            default_user = UserAccount(
                user_id="user_001",
                username="user",
                role=Role.USER,
                password_hash=self._hash_password("user"),
            )
            self.accounts[default_user.user_id] = default_user
            self._save_accounts()
            logger.info("Default admin dan user dibuat")

    def _hash_password(self, password: str) -> str:
        salt = "manus_agent_salt_2026"
        return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()

    def authenticate(self, username: str, password: str) -> Optional[dict]:
        account = None
        for acc in self.accounts.values():
            if acc.username == username:
                account = acc
                break

        if not account:
            return None

        if not account.is_active:
            return None

        if account.locked_until > time.time():
            remaining = int(account.locked_until - time.time())
            return {"error": f"Akun terkunci. Coba lagi dalam {remaining} detik.", "locked": True}

        if account.password_hash != self._hash_password(password):
            account.failed_attempts += 1
            if account.failed_attempts >= self.max_failed_attempts:
                account.locked_until = time.time() + self.lockout_duration
                logger.warning(f"Akun {username} dikunci setelah {self.max_failed_attempts} percobaan gagal")
            self._save_accounts()
            return None

        account.failed_attempts = 0
        account.locked_until = 0
        account.last_login = time.time()
        account.login_count += 1

        token = secrets.token_hex(32)
        session_id = f"sess_{int(time.time())}_{secrets.token_hex(4)}"
        session = Session(session_id, account.user_id, token)
        self.sessions[token] = session

        self._save_accounts()
        logger.info(f"Login berhasil: {username}")

        return {
            "token": token,
            "session_id": session_id,
            "user_id": account.user_id,
            "username": account.username,
            "role": account.role.value,
            "expires_at": session.expires_at,
        }

    def authenticate_api_key(self, api_key: str) -> Optional[dict]:
        for acc in self.accounts.values():
            if acc.api_key == api_key and acc.is_active:
                token = secrets.token_hex(32)
                session_id = f"api_{int(time.time())}_{secrets.token_hex(4)}"
                session = Session(session_id, acc.user_id, token)
                self.sessions[token] = session
                return {
                    "token": token,
                    "session_id": session_id,
                    "user_id": acc.user_id,
                    "username": acc.username,
                    "role": acc.role.value,
                }
        return None

    def validate_session(self, token: str) -> Optional[dict]:
        session = self.sessions.get(token)
        if not session or not session.is_valid or session.is_expired():
            if session:
                del self.sessions[token]
            return None

        session.refresh(self.session_duration)
        account = self.accounts.get(session.user_id)
        if not account or not account.is_active:
            return None

        return {
            "user_id": account.user_id,
            "username": account.username,
            "role": account.role.value,
            "session_id": session.session_id,
        }

    def check_permission(self, user_id: str, permission: str) -> bool:
        account = self.accounts.get(user_id)
        if not account or not account.is_active:
            return False

        if permission in account.denied_permissions:
            return False

        if permission in account.custom_permissions:
            return True

        try:
            perm = Permission(permission)
        except ValueError:
            return False

        role_perms = ROLE_PERMISSIONS.get(account.role, set())
        return perm in role_perms

    def create_account(self, username: str, password: str, role: str = "user",
                       created_by: str = "") -> dict:
        for acc in self.accounts.values():
            if acc.username == username:
                return {"success": False, "error": "Username sudah digunakan"}

        try:
            role_enum = Role(role)
        except ValueError:
            return {"success": False, "error": f"Role tidak valid: {role}"}

        user_id = f"{role}_{int(time.time())}_{secrets.token_hex(2)}"
        account = UserAccount(
            user_id=user_id,
            username=username,
            role=role_enum,
            password_hash=self._hash_password(password),
        )
        self.accounts[user_id] = account
        self._save_accounts()
        logger.info(f"Akun baru dibuat: {username} (role: {role}) oleh {created_by}")

        return {
            "success": True,
            "user_id": user_id,
            "username": username,
            "role": role,
            "api_key": account.api_key,
        }

    def update_role(self, user_id: str, new_role: str, updated_by: str = "") -> dict:
        account = self.accounts.get(user_id)
        if not account:
            return {"success": False, "error": "Akun tidak ditemukan"}

        try:
            role_enum = Role(new_role)
        except ValueError:
            return {"success": False, "error": f"Role tidak valid: {new_role}"}

        old_role = account.role.value
        account.role = role_enum
        self._save_accounts()
        logger.info(f"Role diperbarui: {account.username} ({old_role} -> {new_role}) oleh {updated_by}")

        return {"success": True, "user_id": user_id, "old_role": old_role, "new_role": new_role}

    def deactivate_account(self, user_id: str, deactivated_by: str = "") -> dict:
        account = self.accounts.get(user_id)
        if not account:
            return {"success": False, "error": "Akun tidak ditemukan"}

        account.is_active = False
        tokens_to_remove = [t for t, s in self.sessions.items() if s.user_id == user_id]
        for token in tokens_to_remove:
            del self.sessions[token]

        self._save_accounts()
        logger.info(f"Akun dinonaktifkan: {account.username} oleh {deactivated_by}")
        return {"success": True, "user_id": user_id}

    def list_accounts(self) -> list[dict]:
        result = []
        for acc in self.accounts.values():
            d = acc.to_dict()
            del d["api_key"]
            result.append(d)
        return result

    def get_account_info(self, user_id: str) -> Optional[dict]:
        account = self.accounts.get(user_id)
        if not account:
            return None
        return account.to_dict()

    def logout(self, token: str) -> bool:
        if token in self.sessions:
            del self.sessions[token]
            return True
        return False

    def get_active_sessions_count(self) -> int:
        now = time.time()
        return sum(1 for s in self.sessions.values() if s.is_valid and not s.is_expired())

    def cleanup_expired_sessions(self):
        expired = [t for t, s in self.sessions.items() if s.is_expired()]
        for token in expired:
            del self.sessions[token]
        if expired:
            logger.info(f"{len(expired)} sesi kedaluwarsa dibersihkan")

    def get_rbac_stats(self) -> dict:
        role_counts = {}
        for acc in self.accounts.values():
            role = acc.role.value
            role_counts[role] = role_counts.get(role, 0) + 1

        return {
            "total_accounts": len(self.accounts),
            "active_accounts": sum(1 for a in self.accounts.values() if a.is_active),
            "role_distribution": role_counts,
            "active_sessions": self.get_active_sessions_count(),
            "roles_available": [r.value for r in Role],
            "permissions_count": len(Permission),
        }
