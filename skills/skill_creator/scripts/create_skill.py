"""Script untuk membuat skill baru."""

import os
import json
import logging

logger = logging.getLogger(__name__)

SKILL_TEMPLATE = """# {name}

## Deskripsi
{description}

## Kemampuan
{capabilities}

## Penggunaan
Dokumentasikan cara menggunakan skill ini.

## Instruksi
1. Langkah pertama
2. Langkah kedua
3. Langkah ketiga
"""


def create_skill(name: str, description: str, capabilities: list[str], base_dir: str = "skills") -> dict:
    skill_dir = os.path.join(base_dir, name)

    if os.path.exists(skill_dir):
        return {"success": False, "error": f"Skill '{name}' sudah ada"}

    os.makedirs(skill_dir, exist_ok=True)
    os.makedirs(os.path.join(skill_dir, "scripts"), exist_ok=True)

    capabilities_md = "\n".join(f"- {cap}" for cap in capabilities)
    skill_md = SKILL_TEMPLATE.format(
        name=name.replace("_", " ").title(),
        description=description,
        capabilities=capabilities_md,
    )

    with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
        f.write(skill_md)

    config = {
        "name": name,
        "description": description,
        "capabilities": capabilities,
        "version": "1.0.0",
        "author": "Manus Agent",
    }
    with open(os.path.join(skill_dir, "config.json"), "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    logger.info(f"Skill '{name}' berhasil dibuat di {skill_dir}")
    return {
        "success": True,
        "skill_dir": skill_dir,
        "files": ["SKILL.md", "config.json", "scripts/"],
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
            info = {"name": entry, "has_config": os.path.exists(config_path), "has_skill_md": os.path.exists(skill_md)}
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    info.update(json.load(f))
            skills.append(info)
    return skills


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        name = sys.argv[1]
        desc = sys.argv[2] if len(sys.argv) > 2 else "Skill baru"
        result = create_skill(name, desc, ["kemampuan dasar"])
        print(json.dumps(result, indent=2))
    else:
        print("Penggunaan: python create_skill.py <nama_skill> [deskripsi]")
