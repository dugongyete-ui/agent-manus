"""Skill Manager - Sistem untuk membuat, mengelola, dan mengeksekusi skill modular."""

import asyncio
import importlib
import importlib.util
import json
import logging
import os
import re
import time
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class Skill:
    def __init__(self, name: str, skill_dir: str):
        self.name = name
        self.skill_dir = skill_dir
        self.description = ""
        self.capabilities: list[str] = []
        self.instructions: list[str] = []
        self.usage = ""
        self.version = "1.0.0"
        self.author = ""
        self.config: dict = {}
        self.scripts: dict[str, str] = {}
        self.loaded = False
        self.last_used: Optional[float] = None
        self.use_count = 0

    def load(self) -> bool:
        try:
            skill_md_path = os.path.join(self.skill_dir, "SKILL.md")
            if os.path.exists(skill_md_path):
                self._parse_skill_md(skill_md_path)

            config_path = os.path.join(self.skill_dir, "config.json")
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    self.config = json.load(f)
                self.version = self.config.get("version", self.version)
                self.author = self.config.get("author", self.author)
                if not self.description and self.config.get("description"):
                    self.description = self.config["description"]
                if not self.capabilities and self.config.get("capabilities"):
                    self.capabilities = self.config["capabilities"]

            scripts_dir = os.path.join(self.skill_dir, "scripts")
            if os.path.isdir(scripts_dir):
                for fname in os.listdir(scripts_dir):
                    if fname.endswith(".py"):
                        script_path = os.path.join(scripts_dir, fname)
                        self.scripts[fname] = script_path

            self.loaded = True
            logger.info(f"Skill dimuat: {self.name} (v{self.version})")
            return True

        except Exception as e:
            logger.error(f"Gagal memuat skill '{self.name}': {e}")
            return False

    def _parse_skill_md(self, path: str):
        with open(path, "r") as f:
            content = f.read()

        sections = re.split(r'^## ', content, flags=re.MULTILINE)

        for section in sections:
            lines = section.strip().split("\n")
            if not lines:
                continue
            header = lines[0].strip().lower()
            body = "\n".join(lines[1:]).strip()

            if header.startswith("deskripsi") or header.startswith("description"):
                self.description = body
            elif header.startswith("kemampuan") or header.startswith("capabilities"):
                self.capabilities = [
                    line.lstrip("- ").strip()
                    for line in body.split("\n")
                    if line.strip().startswith("-")
                ]
            elif header.startswith("instruksi") or header.startswith("instructions"):
                self.instructions = [
                    re.sub(r'^\d+\.\s*', '', line).strip()
                    for line in body.split("\n")
                    if re.match(r'^\d+\.', line.strip())
                ]
            elif header.startswith("penggunaan") or header.startswith("usage"):
                self.usage = body

        title_match = re.match(r'^#\s+(.+)', content)
        if title_match and not self.description:
            pass

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "capabilities": self.capabilities,
            "instructions": self.instructions,
            "version": self.version,
            "author": self.author,
            "scripts": list(self.scripts.keys()),
            "loaded": self.loaded,
            "use_count": self.use_count,
            "last_used": self.last_used,
            "skill_dir": self.skill_dir,
        }

    def get_context(self) -> str:
        parts = [f"# Skill: {self.name}"]
        if self.description:
            parts.append(f"\n## Deskripsi\n{self.description}")
        if self.capabilities:
            parts.append("\n## Kemampuan")
            for cap in self.capabilities:
                parts.append(f"- {cap}")
        if self.instructions:
            parts.append("\n## Instruksi")
            for i, inst in enumerate(self.instructions, 1):
                parts.append(f"{i}. {inst}")
        if self.usage:
            parts.append(f"\n## Penggunaan\n{self.usage}")
        return "\n".join(parts)


class SkillManager:
    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = skills_dir
        self.skills: dict[str, Skill] = {}
        self._script_modules: dict[str, Any] = {}
        self.discover_skills()

    async def execute(self, plan: dict) -> str:
        action = plan.get("action", plan.get("intent", ""))
        params = plan.get("params", plan)

        if action in ("list", "list_skills"):
            return json.dumps({"skills": self.list_skills()}, ensure_ascii=False)
        elif action in ("info", "get_info", "detail"):
            name = params.get("name", params.get("skill", ""))
            return json.dumps(self.get_skill_info(name), ensure_ascii=False)
        elif action in ("create", "create_skill", "new"):
            return json.dumps(self.create_skill(
                name=params.get("name", ""),
                description=params.get("description", ""),
                capabilities=params.get("capabilities", []),
            ), ensure_ascii=False)
        elif action in ("update", "update_skill"):
            return json.dumps(self.update_skill(
                name=params.get("name", ""),
                changes=params.get("changes", {}),
            ), ensure_ascii=False)
        elif action in ("delete", "remove", "delete_skill"):
            name = params.get("name", params.get("skill", ""))
            return json.dumps(self.delete_skill(name), ensure_ascii=False)
        elif action in ("run_script", "execute_script"):
            skill_name = params.get("skill", params.get("name", ""))
            script_name = params.get("script", "")
            args = params.get("args", {})
            return json.dumps(await self.run_script(skill_name, script_name, args), ensure_ascii=False)
        elif action in ("context", "get_context"):
            name = params.get("name", params.get("skill", ""))
            return self.get_skill_context(name)
        elif action in ("search", "find"):
            query = params.get("query", "")
            return json.dumps({"results": self.search_skills(query)}, ensure_ascii=False)
        elif action in ("reload", "refresh"):
            self.discover_skills()
            return json.dumps({"success": True, "skills_count": len(self.skills)}, ensure_ascii=False)
        else:
            return json.dumps({
                "info": "Skill Manager - Manajemen Skill Modular",
                "total_skills": len(self.skills),
                "skills": list(self.skills.keys()),
                "actions": [
                    "list - Daftar semua skill",
                    "info - Detail skill (name)",
                    "create - Buat skill baru (name, description, capabilities)",
                    "update - Perbarui skill (name, changes)",
                    "delete - Hapus skill (name)",
                    "run_script - Jalankan skrip skill (skill, script, args)",
                    "context - Ambil konteks skill untuk LLM (name)",
                    "search - Cari skill (query)",
                    "reload - Muat ulang semua skill",
                ],
            }, ensure_ascii=False)

    def discover_skills(self):
        self.skills.clear()
        if not os.path.isdir(self.skills_dir):
            os.makedirs(self.skills_dir, exist_ok=True)
            return

        for entry in os.listdir(self.skills_dir):
            skill_dir = os.path.join(self.skills_dir, entry)
            if not os.path.isdir(skill_dir):
                continue
            skill_md = os.path.join(skill_dir, "SKILL.md")
            if not os.path.exists(skill_md):
                continue

            skill = Skill(entry, skill_dir)
            if skill.load():
                self.skills[entry] = skill

        logger.info(f"Ditemukan {len(self.skills)} skill: {list(self.skills.keys())}")

    def list_skills(self) -> list[dict]:
        return [skill.to_dict() for skill in self.skills.values()]

    def get_skill_info(self, name: str) -> dict:
        if name not in self.skills:
            return {"success": False, "error": f"Skill '{name}' tidak ditemukan"}
        return {"success": True, "skill": self.skills[name].to_dict()}

    def get_skill_context(self, name: str) -> str:
        if name not in self.skills:
            return f"Skill '{name}' tidak ditemukan."
        skill = self.skills[name]
        skill.use_count += 1
        skill.last_used = time.time()
        return skill.get_context()

    def search_skills(self, query: str) -> list[dict]:
        query_lower = query.lower()
        results = []
        for skill in self.skills.values():
            score = 0
            if query_lower in skill.name.lower():
                score += 10
            if query_lower in skill.description.lower():
                score += 5
            for cap in skill.capabilities:
                if query_lower in cap.lower():
                    score += 3
            if score > 0:
                info = skill.to_dict()
                info["relevance_score"] = score
                results.append(info)
        results.sort(key=lambda x: x["relevance_score"], reverse=True)
        return results

    def create_skill(self, name: str, description: str, capabilities: list[str],
                     author: str = "Manus Agent") -> dict:
        if not name:
            return {"success": False, "error": "Nama skill diperlukan"}
        if not re.match(r'^[a-zA-Z0-9_-]+$', name):
            return {"success": False, "error": "Nama skill hanya boleh huruf, angka, underscore, dan dash"}

        skill_dir = os.path.join(self.skills_dir, name)
        if os.path.exists(skill_dir):
            return {"success": False, "error": f"Skill '{name}' sudah ada"}

        os.makedirs(skill_dir, exist_ok=True)
        os.makedirs(os.path.join(skill_dir, "scripts"), exist_ok=True)

        caps_md = "\n".join(f"- {cap}" for cap in capabilities) if capabilities else "- Kemampuan dasar"
        title = name.replace("_", " ").replace("-", " ").title()

        skill_md = f"""# {title}

## Deskripsi
{description or 'Skill baru untuk Manus Agent.'}

## Kemampuan
{caps_md}

## Penggunaan
Dokumentasikan cara menggunakan skill ini.

## Instruksi
1. Baca dokumentasi ini untuk memahami kemampuan skill
2. Gunakan kemampuan yang tersedia sesuai kebutuhan
3. Sesuaikan dan kembangkan skill sesuai kebutuhan
"""
        with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
            f.write(skill_md)

        config = {
            "name": name,
            "description": description,
            "capabilities": capabilities,
            "version": "1.0.0",
            "author": author,
            "created_at": time.time(),
        }
        with open(os.path.join(skill_dir, "config.json"), "w") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        skill = Skill(name, skill_dir)
        skill.load()
        self.skills[name] = skill

        logger.info(f"Skill '{name}' berhasil dibuat")
        return {
            "success": True,
            "skill_dir": skill_dir,
            "files": ["SKILL.md", "config.json", "scripts/"],
            "skill": skill.to_dict(),
        }

    def update_skill(self, name: str, changes: dict) -> dict:
        if name not in self.skills:
            return {"success": False, "error": f"Skill '{name}' tidak ditemukan"}

        skill = self.skills[name]
        config_path = os.path.join(skill.skill_dir, "config.json")

        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                config = json.load(f)
        else:
            config = {}

        config.update(changes)
        config["updated_at"] = time.time()

        with open(config_path, "w") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        if "description" in changes:
            skill.description = changes["description"]
        if "capabilities" in changes:
            skill.capabilities = changes["capabilities"]
        if "version" in changes:
            skill.version = changes["version"]

        if "skill_md" in changes:
            skill_md_path = os.path.join(skill.skill_dir, "SKILL.md")
            with open(skill_md_path, "w") as f:
                f.write(changes["skill_md"])
            skill.load()

        logger.info(f"Skill '{name}' berhasil diperbarui")
        return {"success": True, "changes": changes, "skill": skill.to_dict()}

    def delete_skill(self, name: str) -> dict:
        if name not in self.skills:
            return {"success": False, "error": f"Skill '{name}' tidak ditemukan"}

        import shutil
        skill = self.skills.pop(name)
        try:
            shutil.rmtree(skill.skill_dir)
            logger.info(f"Skill '{name}' berhasil dihapus")
            return {"success": True, "message": f"Skill '{name}' dihapus"}
        except Exception as e:
            self.skills[name] = skill
            return {"success": False, "error": f"Gagal menghapus: {e}"}

    async def run_script(self, skill_name: str, script_name: str, args: dict = None) -> dict:
        if skill_name not in self.skills:
            return {"success": False, "error": f"Skill '{skill_name}' tidak ditemukan"}

        skill = self.skills[skill_name]
        if not script_name.endswith(".py"):
            script_name += ".py"

        if script_name not in skill.scripts:
            available = list(skill.scripts.keys())
            return {"success": False, "error": f"Skrip '{script_name}' tidak ditemukan. Tersedia: {available}"}

        script_path = skill.scripts[script_name]
        try:
            module_name = f"skill_{skill_name}_{script_name.replace('.py', '')}"

            if module_name in self._script_modules:
                module = self._script_modules[module_name]
                importlib.reload(module)
            else:
                spec = importlib.util.spec_from_file_location(module_name, script_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                self._script_modules[module_name] = module

            if hasattr(module, "main"):
                if asyncio.iscoroutinefunction(module.main):
                    result = await module.main(**(args or {}))
                else:
                    result = module.main(**(args or {}))
            elif hasattr(module, "run"):
                if asyncio.iscoroutinefunction(module.run):
                    result = await module.run(**(args or {}))
                else:
                    result = module.run(**(args or {}))
            else:
                return {"success": True, "message": f"Modul '{script_name}' dimuat (tidak ada fungsi main/run)"}

            skill.use_count += 1
            skill.last_used = time.time()

            return {"success": True, "result": result if isinstance(result, (dict, list, str)) else str(result)}

        except Exception as e:
            logger.error(f"Error menjalankan skrip '{script_name}' dari skill '{skill_name}': {e}")
            return {"success": False, "error": str(e)}

    def add_script_to_skill(self, skill_name: str, script_name: str, script_content: str) -> dict:
        if skill_name not in self.skills:
            return {"success": False, "error": f"Skill '{skill_name}' tidak ditemukan"}

        skill = self.skills[skill_name]
        scripts_dir = os.path.join(skill.skill_dir, "scripts")
        os.makedirs(scripts_dir, exist_ok=True)

        if not script_name.endswith(".py"):
            script_name += ".py"

        script_path = os.path.join(scripts_dir, script_name)
        with open(script_path, "w") as f:
            f.write(script_content)

        skill.scripts[script_name] = script_path
        return {"success": True, "script_path": script_path}

    def get_all_capabilities(self) -> list[str]:
        caps = []
        for skill in self.skills.values():
            for cap in skill.capabilities:
                caps.append(f"[{skill.name}] {cap}")
        return caps
