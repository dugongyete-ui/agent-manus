"""Script untuk membuat skill baru - enhanced version."""

import os
import json
import logging
import time

logger = logging.getLogger(__name__)

SKILL_TEMPLATE = """# {title}

## Deskripsi
{description}

## Kemampuan
{capabilities}

## Penggunaan
{usage}

## Instruksi
{instructions}

## Contoh
{examples}
"""

DEFAULT_SCRIPT = '''"""Script utama untuk skill {name}."""

import logging

logger = logging.getLogger(__name__)


def main(**kwargs):
    """Fungsi utama skill."""
    logger.info("Skill {name} dijalankan dengan args: %s", kwargs)
    return {{"success": True, "message": "Skill {name} berhasil dijalankan", "args": kwargs}}


def run(**kwargs):
    """Alias untuk main."""
    return main(**kwargs)


if __name__ == "__main__":
    result = main()
    print(json.dumps(result, indent=2))
'''


def create_skill(name: str, description: str, capabilities: list[str],
                 usage: str = "", instructions: list[str] = None,
                 examples: list[str] = None, scripts: dict = None,
                 base_dir: str = "skills") -> dict:
    skill_dir = os.path.join(base_dir, name)

    if os.path.exists(skill_dir):
        return {"success": False, "error": f"Skill '{name}' sudah ada"}

    os.makedirs(skill_dir, exist_ok=True)
    os.makedirs(os.path.join(skill_dir, "scripts"), exist_ok=True)

    title = name.replace("_", " ").replace("-", " ").title()
    capabilities_md = "\n".join(f"- {cap}" for cap in capabilities) if capabilities else "- Kemampuan dasar"
    usage_md = usage or "Dokumentasikan cara menggunakan skill ini."

    if instructions:
        instructions_md = "\n".join(f"{i+1}. {inst}" for i, inst in enumerate(instructions))
    else:
        instructions_md = "1. Baca dokumentasi ini\n2. Gunakan kemampuan yang tersedia\n3. Sesuaikan sesuai kebutuhan"

    if examples:
        examples_md = "\n".join(f"- {ex}" for ex in examples)
    else:
        examples_md = "Tambahkan contoh penggunaan di sini."

    skill_md = SKILL_TEMPLATE.format(
        title=title,
        description=description or "Skill baru untuk Manus Agent.",
        capabilities=capabilities_md,
        usage=usage_md,
        instructions=instructions_md,
        examples=examples_md,
    )

    with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
        f.write(skill_md)

    config = {
        "name": name,
        "description": description,
        "capabilities": capabilities,
        "version": "1.0.0",
        "author": "Manus Agent",
        "created_at": time.time(),
    }
    with open(os.path.join(skill_dir, "config.json"), "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    default_script = DEFAULT_SCRIPT.format(name=name)
    with open(os.path.join(skill_dir, "scripts", "main.py"), "w") as f:
        f.write(default_script)

    if scripts:
        for script_name, script_content in scripts.items():
            if not script_name.endswith(".py"):
                script_name += ".py"
            with open(os.path.join(skill_dir, "scripts", script_name), "w") as f:
                f.write(script_content)

    logger.info(f"Skill '{name}' berhasil dibuat di {skill_dir}")
    return {
        "success": True,
        "skill_dir": skill_dir,
        "files": ["SKILL.md", "config.json", "scripts/main.py"],
    }


def update_skill(name: str, changes: dict, base_dir: str = "skills") -> dict:
    skill_dir = os.path.join(base_dir, name)

    if not os.path.exists(skill_dir):
        return {"success": False, "error": f"Skill '{name}' tidak ditemukan"}

    config_path = os.path.join(skill_dir, "config.json")
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            config = json.load(f)
        config.update(changes)
        config["updated_at"] = time.time()
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    logger.info(f"Skill '{name}' berhasil diperbarui")
    return {"success": True, "changes": changes}


def list_skills(base_dir: str = "skills") -> list[dict]:
    skills = []
    if not os.path.exists(base_dir):
        return skills

    for entry in os.listdir(base_dir):
        skill_dir = os.path.join(base_dir, entry)
        if os.path.isdir(skill_dir):
            config_path = os.path.join(skill_dir, "config.json")
            skill_md = os.path.join(skill_dir, "SKILL.md")
            info = {
                "name": entry,
                "has_config": os.path.exists(config_path),
                "has_skill_md": os.path.exists(skill_md),
            }
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    info.update(json.load(f))
            skills.append(info)
    return skills


def main(**kwargs):
    action = kwargs.get("action", "list")
    if action == "create":
        return create_skill(
            name=kwargs.get("name", "new_skill"),
            description=kwargs.get("description", "Skill baru"),
            capabilities=kwargs.get("capabilities", ["kemampuan dasar"]),
        )
    elif action == "list":
        return {"skills": list_skills(kwargs.get("base_dir", "skills"))}
    elif action == "update":
        return update_skill(
            name=kwargs.get("name", ""),
            changes=kwargs.get("changes", {}),
        )
    return {"error": "Aksi tidak dikenal. Gunakan: create, list, update"}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        name = sys.argv[1]
        desc = sys.argv[2] if len(sys.argv) > 2 else "Skill baru"
        result = create_skill(name, desc, ["kemampuan dasar"])
        print(json.dumps(result, indent=2))
    else:
        skills = list_skills()
        print(json.dumps(skills, indent=2))
