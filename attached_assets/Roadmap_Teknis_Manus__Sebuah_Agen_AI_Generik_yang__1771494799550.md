# Roadmap Teknis Manus: Sebuah Agen AI Generik yang Komprehensif

**Penulis**: Manus AI
**Tanggal**: 19 Februari 2026

## 1. Pendahuluan

Dokumen ini menyajikan roadmap teknis yang komprehensif untuk membangun agen AI generik yang meniru fungsionalitas Manus.im. Berbeda dengan pendekatan berbasis tool sederhana, roadmap ini menguraikan arsitektur yang lebih canggih, berpusat pada **Agent Loop** iteratif dan lingkungan eksekusi **sandbox** yang terisolasi. Tujuannya adalah untuk menciptakan agen yang mampu menganalisis, berpikir, memilih alat, mengeksekusi tindakan, dan belajar dari observasi secara mandiri.

## 2. Arsitektur Umum: Agent Loop

Inti dari Manus adalah **Agent Loop** yang memungkinkan agen untuk beroperasi secara otonom dan adaptif. Alur kerja ini dirancang untuk memproses tugas secara iteratif, memastikan bahwa setiap tindakan didasarkan pada analisis konteks yang cermat dan umpan balik dari eksekusi sebelumnya. Proses ini mencakup:

1.  **Analyze Context**: Agen menganalisis input pengguna, status sistem saat ini, dan riwayat interaksi untuk memahami tujuan dan batasan tugas.
2.  **Think**: Berdasarkan analisis konteks, agen merumuskan rencana tindakan, yang mungkin melibatkan pembaruan rencana yang ada, memajukan fase, atau mengidentifikasi langkah-langkah spesifik yang perlu diambil.
3.  **Select Tool**: Agen memilih alat yang paling sesuai dari kumpulan alat yang tersedia (misalnya, `shell`, `file`, `browser`, `search`, `generate`, `slides`, `webdev_init_project`, `schedule`) untuk melaksanakan langkah berikutnya dalam rencana.
4.  **Execute Action**: Alat yang dipilih dijalankan di lingkungan sandbox yang terisolasi. Eksekusi ini bisa berupa perintah shell, operasi file, navigasi browser, atau pemanggilan API internal.
5.  **Receive Observation**: Hasil dari eksekusi alat (output shell, konten file, tangkapan layar browser, data pencarian, dll.) diterima dan diintegrasikan kembali ke dalam konteks agen. Observasi ini menjadi dasar untuk iterasi berikutnya dari Agent Loop.
6.  **Iterate Loop**: Proses ini berulang hingga tugas selesai atau agen membutuhkan klarifikasi lebih lanjut dari pengguna.

## 3. Komponen Utama Sistem

Sistem Manus terdiri dari beberapa komponen kunci yang bekerja sama untuk mendukung fungsionalitas agen AI:

### 3.1. Lingkungan Sandbox Terisolasi

Lingkungan eksekusi Manus adalah Virtual Machine (VM) Ubuntu 22.04 yang terisolasi sepenuhnya. Lingkungan ini menyediakan:

-   **Isolasi Penuh**: Mencegah interferensi antar tugas dan memastikan keamanan serta privasi data. Setiap sesi agen berjalan dalam lingkungan yang bersih dan terkontrol.
-   **Persistensi State**: Status sistem dan paket yang diinstal tetap ada di seluruh sesi, memungkinkan kelanjutan tugas tanpa perlu konfigurasi ulang yang berulang.
-   **Akses Internet**: Memungkinkan agen untuk berinteraksi dengan layanan eksternal, mengunduh dependensi, dan melakukan pencarian web.
-   **Multi-Runtime**: Mendukung berbagai lingkungan eksekusi, termasuk Python (3.11), Node.js (22.13), dan Shell (bash), memungkinkan fleksibilitas dalam menjalankan berbagai jenis kode dan aplikasi.

### 3.2. Sistem Tooling (Function Calling)

Manus dilengkapi dengan serangkaian alat yang dapat dipanggil secara terprogram oleh agen. Alat-alat ini adalah antarmuka utama agen untuk berinteraksi dengan lingkungan dan melaksanakan tugas. Beberapa alat penting meliputi:

-   **`shell`**: Untuk menjalankan perintah baris perintah, menginstal paket, mengelola proses, dan berinteraksi dengan sistem operasi.
-   **`file`**: Untuk melakukan operasi file (membaca, menulis, mengedit, melihat) dengan dukungan untuk berbagai format, termasuk multimodal (PDF, gambar, dokumen).
-   **`browser`**: Untuk navigasi web dinamis menggunakan Chromium, memungkinkan interaksi dengan halaman web yang kompleks, termasuk JavaScript, formulir, dan otentikasi.
-   **`search`**: Untuk melakukan pencarian informasi yang canggih di berbagai sumber (web, gambar, API, berita, alat, data, penelitian).
-   **`generate`**: Untuk membuat atau mengedit media (gambar, video, audio, ucapan) menggunakan kemampuan AI generatif.
-   **`slides`**: Untuk membuat presentasi berbasis slide, dengan opsi mode HTML atau gambar.
-   **`webdev_init_project`**: Untuk menginisialisasi proyek pengembangan web atau seluler dengan scaffolding yang telah ditentukan (misalnya, React, Next.js, Expo).
-   **`schedule`**: Untuk menjadwalkan tugas agar berjalan pada waktu atau interval tertentu (cron atau interval).
-   **`message`**: Untuk berkomunikasi dengan pengguna, memberikan pembaruan, mengajukan pertanyaan, atau menyampaikan hasil akhir.
-   **`plan`**: Untuk membuat, memperbarui, dan memajukan rencana tugas yang terstruktur.

### 3.3. Manajemen Konteks dan Memori

Agen mempertahankan konteks percakapan dan tugas melalui:

-   **Prompt Sistem**: Instruksi awal yang mendefinisikan peran, kemampuan, dan batasan agen.
-   **Riwayat Interaksi**: Catatan lengkap semua input pengguna, tindakan agen, dan observasi, yang digunakan untuk mempertahankan pemahaman tentang status tugas saat ini.
-   **Memori Jangka Panjang**: Mekanisme untuk menyimpan pengetahuan yang dipelajari dari tugas-tugas sebelumnya atau informasi penting yang perlu dipertahankan di seluruh sesi.

### 3.4. Modul Multimodal

Manus memiliki kemampuan untuk memproses dan menghasilkan berbagai jenis media:

-   **Pemrosesan Gambar**: Melihat, menganalisis, dan memanipulasi gambar.
-   **Pemrosesan Audio/Video**: Transkripsi audio, analisis konten video, dan generasi media.
-   **Pemahaman Dokumen**: Mengekstrak informasi dari PDF, Word, dan PowerPoint, termasuk konten teks dan visual.

## 4. Struktur File dan Direktori (Contoh Arsitektur)

Struktur file Manus dirancang untuk modularitas dan skalabilitas, memisahkan logika inti agen dari implementasi alat dan konfigurasi. Berikut adalah contoh struktur direktori tingkat tinggi:

```
/home/ubuntu/
├── agent_core/                   # Logika inti Agent Loop dan manajemen konteks
│   ├── main.py                   # Titik masuk utama, menginisialisasi Agent Loop
│   ├── agent_loop.py             # Implementasi Agent Loop (Analyze, Think, Select, Execute, Observe)
│   ├── context_manager.py        # Mengelola konteks percakapan dan memori
│   ├── tool_selector.py          # Logika untuk memilih alat berdasarkan niat dan konteks
│   └── planner.py                # Modul untuk membuat dan memperbarui rencana tugas
├── tools/                        # Implementasi alat-alat yang dapat dipanggil agen
│   ├── __init__.py
│   ├── shell_tool.py             # Wrapper untuk interaksi shell
│   ├── file_tool.py              # Wrapper untuk operasi sistem file
│   ├── browser_tool.py           # Wrapper untuk interaksi browser (Chromium)
│   ├── search_tool.py            # Wrapper untuk API pencarian eksternal
│   ├── generate_tool.py          # Wrapper untuk API generasi media (gambar, video, audio)
│   ├── slides_tool.py            # Logika untuk pembuatan presentasi
│   ├── webdev_tool.py            # Logika untuk inisialisasi proyek web/mobile
│   ├── schedule_tool.py          # Logika untuk penjadwalan tugas
│   └── message_tool.py           # Logika untuk komunikasi dengan pengguna
├── skills/                       # Direktori untuk skill yang dapat diperluas
│   ├── skill_creator/            # Contoh skill untuk membuat/memperbarui skill lain
│   │   ├── SKILL.md              # Deskripsi skill dan instruksi
│   │   └── scripts/              # Skrip terkait skill ini
│   └── another_skill/            # Skill lainnya
├── sandbox_env/                  # Konfigurasi dan manajemen lingkungan sandbox
│   ├── vm_manager.py             # Mengelola siklus hidup VM (start, stop, snapshot)
│   ├── package_manager.py        # Mengelola instalasi paket (pip, npm)
│   └── runtime_executor.py       # Menjalankan kode di berbagai runtime
├── config/                       # File konfigurasi global
│   ├── settings.yaml             # Pengaturan umum sistem
│   └── tool_configs.json         # Konfigurasi spesifik untuk setiap alat
├── logs/                         # Direktori untuk log sistem dan aktivitas agen
│   ├── agent_activity.log        # Log aktivitas Agent Loop
│   └── error.log                 # Log kesalahan sistem
├── data/                         # Direktori untuk data persisten atau model lokal
│   ├── knowledge_base.db         # Basis pengetahuan agen (SQLite)
│   └── user_profiles.json        # Profil pengguna dan preferensi
└── requirements.txt              # Dependensi Python untuk agent_core dan tools
```

## 5. Alur Kerja Detail Agent Loop

Setiap iterasi Agent Loop mengikuti langkah-langkah berikut:

1.  **Observasi & Konteks**: Agen menerima observasi terbaru (misalnya, output dari alat yang baru saja dijalankan, pesan baru dari pengguna). Semua informasi ini ditambahkan ke konteks yang terus berkembang.
2.  **Analisis & Pemahaman**: Agen menganalisis konteks untuk mengidentifikasi tujuan saat ini, kemajuan tugas, dan potensi masalah. Ini melibatkan pemrosesan bahasa alami untuk memahami niat pengguna dan output alat.
3.  **Perencanaan & Pemikiran**: Berdasarkan analisis, agen memperbarui rencana tugasnya. Ini mungkin melibatkan:
    -   Memilih fase berikutnya dalam rencana yang telah ditentukan.
    -   Memodifikasi rencana yang ada jika ada informasi baru atau perubahan persyaratan.
    -   Menentukan langkah-langkah mikro yang diperlukan untuk mencapai tujuan fase saat ini.
4.  **Pemilihan Alat**: Agen secara dinamis memilih alat yang paling sesuai dari daftar alat yang tersedia. Pemilihan ini didasarkan pada tujuan langkah saat ini, jenis data yang perlu diproses, dan kapabilitas alat.
5.  **Eksekusi Alat**: Agen memanggil alat yang dipilih dengan parameter yang sesuai. Eksekusi ini terjadi di lingkungan sandbox yang aman.
6.  **Umpan Balik & Koreksi Diri**: Jika eksekusi alat menghasilkan kesalahan atau hasil yang tidak terduga, agen akan menganalisis kesalahan tersebut, mencoba strategi alternatif, atau meminta klarifikasi dari pengguna. Ini adalah bagian penting dari kemampuan koreksi diri agen.

## 6. Fase Pengembangan (Roadmap yang Disempurnakan)

Roadmap ini menguraikan fase-fase pengembangan yang lebih realistis dan komprehensif untuk membangun agen AI generik, dikelompokkan dalam **Gelombang Pengerjaan**:

### Ringkasan Gelombang Pengerjaan

| Gelombang | Fase yang Dicakup | Fokus Utama |
| :-------- | :---------------- | :---------- |
| **Gelombang 1** | Fase 1, Fase 2    | Otak & Tangan (Agent Loop, File System) |
| **Gelombang 2** | Fase 3, Fase 4    | Interaksi Dunia Luar (Browser, Code Execution) |
| **Gelombang 3** | Fase 7            | Antarmuka Pengguna (UI/UX) |
| **Gelombang 4** | Fase 5, 6, 8, 9, 10, 11, 12 | Kecerdasan Lanjutan & Skalabilitas (Multimodal, Penjadwalan, Skill, Self-Improvement, Keamanan, Deployment, Integrasi) |

---

### **GELOMBANG 1: Membangun "Otak" dan "Tangan" (Fondasi Agen)**

**Fase 1: Fondasi Agent Loop & Sandbox (Core)**
-   **Tujuan**: Membangun inti Agent Loop dan lingkungan sandbox dasar.
-   **Komponen**: Implementasi `agent_loop.py`, `context_manager.py`, `tool_selector.py`. Setup VM Ubuntu dasar dengan Python dan Node.js. Integrasi alat `shell` dan `message` dasar.
-   **Output**: Agen dapat menerima perintah sederhana, menjalankan perintah shell, dan berkomunikasi dengan pengguna.

**Fase 2: Sistem File & Manajemen Data**
-   **Tujuan**: Mengaktifkan interaksi agen dengan sistem file dan persistensi data.
-   **Komponen**: Implementasi `file_tool.py` (read, write, append, edit, view). Integrasi database SQLite (`knowledge_base.db`) untuk memori jangka panjang dan manajemen profil pengguna.
-   **Output**: Agen dapat membuat, membaca, memodifikasi file, dan menyimpan/mengambil data dari basis pengetahuan.

---

### **GELOMBANG 2: Interaksi Dunia Luar (Kapabilitas Esensial)**

**Fase 3: Browser Agent & Web Interaction**
-   **Tujuan**: Memberikan agen kemampuan untuk berinteraksi secara dinamis dengan web.
-   **Komponen**: Implementasi `browser_tool.py` (navigasi, interaksi DOM, tangkapan layar). Integrasi `search_tool.py` untuk pencarian web yang canggih.
-   **Output**: Agen dapat menjelajahi internet, mengekstrak informasi dari halaman web, dan melakukan pencarian.

**Fase 4: Code Execution & Development Environment**
-   **Tujuan**: Memungkinkan agen untuk menulis, mengeksekusi, dan men-debug kode dalam berbagai bahasa.
-   **Komponen**: Peningkatan `shell_tool.py` untuk eksekusi kode yang lebih aman dan terisolasi. Implementasi `webdev_tool.py` untuk inisialisasi proyek dan manajemen dependensi.
-   **Output**: Agen dapat mengembangkan aplikasi sederhana, menginstal pustaka, dan menjalankan skrip.

---

### **GELOMBANG 3: Antarmuka dan Pengalaman Pengguna (Visibilitas Agen)**

**Fase 7: Peningkatan UI/UX & Visualisasi**
-   **Tujuan**: Mengembangkan antarmuka pengguna yang intuitif dan kaya fitur untuk berinteraksi dengan agen.
-   **Komponen**: Pengembangan frontend (React/Next.js) untuk menampilkan Task Cards, Live Activity Bar, File Explorer, dan output kode. Integrasi dengan API backend agen.
-   **Output**: Antarmuka pengguna yang responsif dan informatif yang memungkinkan pengguna memantau dan mengelola tugas agen.

---

### **GELOMBANG 4: Kecerdasan Lanjutan & Skalabilitas (Penyempurnaan Agen)**

**Fase 5: Multimodal Input & Output**
-   **Tujuan**: Memperluas kemampuan agen untuk memproses dan menghasilkan berbagai jenis media.
-   **Komponen**: Implementasi `generate_tool.py` (gambar, audio, video). Peningkatan `file_tool.py` untuk pemahaman dokumen multimodal (PDF, gambar).
-   **Output**: Agen dapat menghasilkan gambar dari teks, mentranskripsi audio, dan memahami konten visual dalam dokumen.

**Fase 6: Penjadwalan & Otomatisasi Tugas**
-   **Tujuan**: Memberikan agen kemampuan untuk menjadwalkan dan mengotomatisasi tugas.
-   **Komponen**: Implementasi `schedule_tool.py` (cron, interval). Integrasi dengan sistem notifikasi untuk pembaruan status tugas.
-   **Output**: Agen dapat mengatur tugas berulang atau tugas satu kali yang akan dieksekusi di masa mendatang.

**Fase 8: Skill Management & Ekstensibilitas**
-   **Tujuan**: Membangun sistem untuk membuat, mengelola, dan memperluas kemampuan agen melalui sistem skill modular.
-   **Komponen**: Implementasi direktori `skills/` dengan `SKILL.md` dan skrip terkait. Mekanisme untuk agen membaca dan menggunakan skill baru secara dinamis. Pengembangan `skill_creator` sebagai skill contoh.
-   **Output**: Agen dapat belajar dan mengintegrasikan kemampuan baru yang didefinisikan dalam format skill.

**Fase 9: Self-Improvement & Learning (Advanced)**
-   **Tujuan**: Mengembangkan kemampuan agen untuk belajar dari pengalaman dan meningkatkan kinerjanya secara otonom.
-   **Komponen**: Implementasi mekanisme Reinforcement Learning from Human Feedback (RLHF) untuk umpan balik pengguna. Modul meta-learning untuk agen belajar bagaimana belajar. Peningkatan `planner.py` untuk mengoptimalkan strategi berdasarkan riwayat tugas.
-   **Output**: Agen yang semakin cerdas dan efisien seiring waktu, mampu mengidentifikasi pola keberhasilan dan kegagalan.

**Fase 10: Keamanan & Kepatuhan**
-   **Tujuan**: Memastikan keamanan, privasi, dan kepatuhan sistem Manus.
-   **Komponen**: Audit keamanan sandbox, implementasi kontrol akses berbasis peran, enkripsi data, dan kepatuhan terhadap standar privasi data (misalnya, GDPR).
-   **Output**: Sistem yang aman dan patuh yang melindungi data pengguna dan operasi agen.

**Fase 11: Deployment & Scaling**
-   **Tujuan**: Mengoptimalkan Manus untuk deployment produksi dan skalabilitas.
-   **Komponen**: Kontainerisasi (Docker/Kubernetes) untuk deployment yang efisien. Implementasi arsitektur microservices untuk memisahkan komponen. Strategi penskalaan otomatis untuk menangani beban kerja yang bervariasi.
-   **Output**: Manus yang siap produksi, dapat diskalakan, dan tangguh.

**Fase 12: Kapabilitas Lanjutan & Integrasi Eksternal**
-   **Tujuan**: Menambahkan kapabilitas canggih dan integrasi dengan layanan eksternal.
-   **Komponen**: Integrasi dengan Model Context Protocol (MCP) untuk interaksi dengan LLM pihak ketiga. Pengembangan API eksternal untuk memungkinkan aplikasi lain berinteraksi dengan Manus. Dukungan untuk berbagai model LLM (misalnya, OpenAI, Gemini).
-   **Output**: Manus yang sangat fleksibel, dapat diintegrasikan, dan mampu memanfaatkan teknologi AI terbaru.

## 7. Referensi

[1] Manus AI: Features, Architecture, Access, Early Issues & More - DataCamp Blog
[2] In-depth technical investigation into the Manus AI agent - Gist by renschni
[3] Creating a Custom MCP Server with Flask to Power AI Code Execution - dev.to
[4] AI Agent Code Execution API - Replit Blog
[5] The Ultimate AI Agent Project Roadmap for 2025 - The AI Corner
