# System Monitor

## Deskripsi
Skill untuk memantau kondisi sistem - penggunaan CPU, memori, disk, dan proses yang berjalan.

## Kemampuan
- Memeriksa penggunaan memori (RAM)
- Memeriksa penggunaan disk
- Mendaftar proses yang berjalan
- Memeriksa informasi sistem operasi
- Memantau uptime sistem

## Penggunaan
```python
result = await skill_manager.run_script("system_monitor", "monitor", {})
```

## Instruksi
1. Jalankan skill untuk mendapatkan snapshot kondisi sistem saat ini
2. Gunakan data untuk monitoring atau diagnostik
3. Bandingkan dengan snapshot sebelumnya untuk deteksi anomali
