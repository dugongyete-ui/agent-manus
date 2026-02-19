# Skill Creator

## Deskripsi
Skill untuk membuat, mengelola, dan memperbarui skill lain dalam sistem Manus Agent. Menyediakan template otomatis, validasi, dan manajemen dependensi antar skill.

## Kemampuan
- Membuat skill baru dengan struktur direktori lengkap (SKILL.md, config.json, scripts/)
- Memperbarui konfigurasi dan dokumentasi skill yang sudah ada
- Mendaftar semua skill yang tersedia beserta statusnya
- Mengelola dependensi dan konfigurasi antar skill
- Membuat skrip default (main.py) untuk setiap skill baru
- Validasi nama dan format skill

## Penggunaan
```python
from skills.skill_creator.scripts.create_skill import create_skill, update_skill, list_skills

# Membuat skill baru
create_skill(
    name="my_new_skill",
    description="Deskripsi skill",
    capabilities=["kemampuan_1", "kemampuan_2"],
    instructions=["Langkah 1", "Langkah 2"],
)

# Memperbarui skill
update_skill(
    name="my_new_skill",
    changes={"description": "Deskripsi baru", "version": "1.1.0"}
)

# Mendaftar semua skill
skills = list_skills()
```

## Instruksi
1. Tentukan nama skill (huruf, angka, underscore, dash)
2. Berikan deskripsi dan kemampuan yang jelas
3. Skill otomatis mendapat SKILL.md, config.json, dan scripts/main.py
4. Kustomisasi skrip di folder scripts/ sesuai kebutuhan
5. Daftarkan skill ke sistem agen melalui SkillManager
