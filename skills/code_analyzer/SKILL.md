# Code Analyzer

## Deskripsi
Skill untuk menganalisis kode sumber - menghitung statistik, menemukan pola, memeriksa kualitas kode, dan memberikan saran perbaikan.

## Kemampuan
- Menghitung jumlah baris, fungsi, kelas, dan komentar dalam kode
- Mendeteksi bahasa pemrograman secara otomatis
- Menganalisis kompleksitas kode (cyclomatic complexity sederhana)
- Mencari pola umum dan anti-pattern
- Menghitung rasio komentar terhadap kode
- Mendaftar dependensi/import yang digunakan

## Penggunaan
```python
# Jalankan via SkillManager
result = await skill_manager.run_script("code_analyzer", "analyze", {"file_path": "main.py"})
```

## Instruksi
1. Berikan path file yang ingin dianalisis
2. Skill akan mendeteksi bahasa dan menganalisis struktur kode
3. Hasil berupa statistik dan saran perbaikan
