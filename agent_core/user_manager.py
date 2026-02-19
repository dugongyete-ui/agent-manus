"""User Manager - Manajemen profil pengguna dan preferensi."""

import json
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)


class UserProfile:
    def __init__(self, user_id: str, name: str = "", preferences: Optional[dict] = None):
        self.user_id = user_id
        self.name = name
        self.preferences = preferences or {
            "language": "id",
            "theme": "dark",
            "notification_level": "normal",
            "auto_save": True,
            "max_history": 100,
        }
        self.created_at = time.time()
        self.last_active = time.time()
        self.interaction_count = 0

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "preferences": self.preferences,
            "created_at": self.created_at,
            "last_active": self.last_active,
            "interaction_count": self.interaction_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UserProfile":
        profile = cls(
            user_id=data["user_id"],
            name=data.get("name", ""),
            preferences=data.get("preferences"),
        )
        profile.created_at = data.get("created_at", time.time())
        profile.last_active = data.get("last_active", time.time())
        profile.interaction_count = data.get("interaction_count", 0)
        return profile


class UserManager:
    def __init__(self, profiles_path: str = "data/user_profiles.json"):
        self.profiles_path = profiles_path
        self.profiles: dict[str, UserProfile] = {}
        self._load_profiles()

    def _load_profiles(self):
        if os.path.exists(self.profiles_path):
            try:
                with open(self.profiles_path, "r") as f:
                    data = json.load(f)
                for profile_data in data.get("profiles", []):
                    profile = UserProfile.from_dict(profile_data)
                    self.profiles[profile.user_id] = profile
                logger.info(f"{len(self.profiles)} profil pengguna dimuat")
            except Exception as e:
                logger.warning(f"Gagal memuat profil: {e}")

    def _save_profiles(self):
        os.makedirs(os.path.dirname(self.profiles_path) or ".", exist_ok=True)
        data = {
            "profiles": [p.to_dict() for p in self.profiles.values()],
            "metadata": {
                "version": "1.0.0",
                "last_updated": time.time(),
            },
        }
        with open(self.profiles_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_or_create_profile(self, user_id: str, name: str = "") -> UserProfile:
        if user_id not in self.profiles:
            self.profiles[user_id] = UserProfile(user_id=user_id, name=name)
            self._save_profiles()
            logger.info(f"Profil baru dibuat: {user_id}")
        profile = self.profiles[user_id]
        profile.last_active = time.time()
        profile.interaction_count += 1
        return profile

    def update_preference(self, user_id: str, key: str, value) -> bool:
        profile = self.profiles.get(user_id)
        if not profile:
            return False
        profile.preferences[key] = value
        self._save_profiles()
        logger.info(f"Preferensi diperbarui untuk {user_id}: {key}={value}")
        return True

    def get_preference(self, user_id: str, key: str, default=None):
        profile = self.profiles.get(user_id)
        if not profile:
            return default
        return profile.preferences.get(key, default)

    def list_profiles(self) -> list[dict]:
        return [p.to_dict() for p in self.profiles.values()]

    def delete_profile(self, user_id: str) -> bool:
        if user_id in self.profiles:
            del self.profiles[user_id]
            self._save_profiles()
            return True
        return False

    def save(self):
        self._save_profiles()
