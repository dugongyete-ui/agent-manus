# Skill Creator

## Deskripsi
Skill untuk membuat dan memperbarui skill lain dalam sistem Manus Agent.

## Kemampuan
- Membuat skill baru dengan struktur direktori yang benar
- Memperbarui skill yang sudah ada
- Mengelola dependensi antar skill
- Validasi konfigurasi skill

## Struktur Skill
Setiap skill harus memiliki:
1. `SKILL.md` - File deskripsi dan instruksi
2. `scripts/` - Direktori untuk skrip terkait (opsional)
3. Dependensi dan konfigurasi yang diperlukan

## Penggunaan
```python
from skills.skill_creator import create_skill, update_skill

# Membuat skill baru
create_skill(
    name="my_new_skill",
    description="Deskripsi skill",
    capabilities=["kemampuan_1", "kemampuan_2"]
)

# Memperbarui skill
update_skill(
    name="my_new_skill",
    changes={"description": "Deskripsi baru"}
)
```

## Instruksi
1. Tentukan nama dan deskripsi skill
2. Definisikan kemampuan yang dimiliki skill
3. Buat skrip pendukung jika diperlukan
4. Daftarkan skill ke sistem agen
