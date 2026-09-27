# CCTV Public Monitor (CPM)
### Monitoring & Deteksi Objek CCTV Publik Real-Time berbasis Python + YOLO + SQLite

Aplikasi monitoring cerdas untuk menangkap stream CCTV publik (HLS `.m3u8`, RTSP, MJPEG, HTTP), memproses frame dengan model deteksi objek open source (Ultralytics YOLOv8 / YOLOv11), mencatat rekaman ke database SQLite, memberikan alert otomatis jika kepadatan melebihi batas, dan menyajikan dashboard web interaktif.

---

## 🚀 Fitur Utama

- **Stream Ingestion Fleksibel**: Mendukung URL stream HLS (`.m3u8`), RTSP (`rtsp://...`), MJPEG, dan HTTP progressive stream.
- **Deteksi Objek Real-Time (YOLOv8)**: Deteksi otomatis objek lalu lintas & publik (`car`, `motorcycle`, `person`, `bus`, `truck`, `bicycle`).
- **Dashboard Web Interaktif**:
  - Live Feed dengan visualisasi Bounding Box dan badge FPS/Objek real-time.
  - Ringkasan KPI (Kamera aktif, total objek 24 jam, status model, alert count).
  - Snapshot instan dengan sekali klik.
- **Manajemen Multi-Kamera**: Tambah, edit, hapus, dan uji validitas stream secara langsung dari browser.
- **Riwayat & Filter Deteksi**:
  - Filter pencarian berdasarkan kamera, kelas objek, rentang tanggal/jam, dan confidence threshold.
  - Ekspor seluruh riwayat deteksi ke format **CSV**.
- **Sistem Alert & Peringatan Dini**:
  - Aturan ambang batas jumlah kendaraan/orang (misal: jika mobil &ge; 10 unit dalam 1 kamera).
  - Snapshot bukti otomatis tersimpan ke folder `snapshots/` saat alert terpicu.
- **Pembersihan & Retensi Data Otomatis**: Background job membersihkan log & snapshot lama (default 30 hari).
- **Pemantauan Kesehatan (Health Check)**: Logging status online/offline tiap kamera secara berkala ke database.

---

## 📐 Arsitektur Sistem

```
[CCTV Publik (HLS/RTSP/MJPEG)] 
       │
       ▼
 [StreamReader (OpenCV)] ──(Latest Frame Buffer)
       │
       ▼
 [YOLO Engine (yolov8n.pt)] ──(Inference & Aggregation)
       │
       ├─► [SQLite Database (detections, boxes, alerts, health)]
       ├─► [Snapshots Storage (snapshots/*.jpg)]
       │
       ▼
 [FastAPI Backend] ──(MJPEG Stream & WebSocket)
       │
       ▼
 [Web Dashboard (HTML5 / TailwindCSS / Vanilla JS)]
```

---

## 🛠️ Instalasi & Menjalankan

### 1. Prasyarat
- Python 3.10 atau yang lebih baru.
- Koneksi internet untuk mengunduh bobot model awal `yolov8n.pt`.

### 2. Instal Dependensi
```bash
pip install -r requirements.txt
```

### 3. Menjalankan Server
Jalankan aplikasi menggunakan Uvicorn:
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Akses dashboard di browser Anda:
```
http://localhost:8000
```
Dokumentasi interaktif OpenAPI / Swagger dapat diakses di:
```
http://localhost:8000/docs
```

---

## 🔍 Cara Menemukan URL Stream CCTV Publik (Bukan `blob:`)

Portal CCTV Pemda (misalnya `cctvkanjeng.gresikkab.go.id`) sering kali menampilkan URL pemutar video berupa `blob:https://...`. URL `blob:` adalah referensi internal memori browser JavaScript dan **tidak dapat diakses oleh server backend Python**.

**Langkah menemukan URL stream asli:**
1. Buka halaman CCTV publik di browser Chrome / Firefox / Edge.
2. Tekan `F12` atau klik kanan &rarr; **Inspect** untuk membuka Developer Tools.
3. Klik tab **Network**.
4. Di bagian filter, pilih **Fetch/XHR** atau **Media**.
5. Muat ulang (Refresh) halaman atau putar video CCTV.
6. Cari request berulang dengan ekstensi:
   - `.m3u8` (HLS playlist stream, contoh: `https://.../live/cam01/index.m3u8`)
   - `.ts` (HLS video chunk)
   - `.mpd` (DASH stream)
   - atau koneksi WebSocket `ws://...` / `rtsp://...`
7. Klik kanan pada request `.m3u8` tersebut &rarr; pilih **Copy link address**.
8. Gunakan URL tersebut pada menu **Tambah Kamera** di dashboard CPM dan klik tombol **Uji Koneksi**.

---

## 📁 Struktur Direktori

```
deteksi object cctv/
├── app/
│   ├── main.py                 # FastAPI App, lifespan, middleware, routers
│   ├── config.py               # Konfigurasi sistem & path direktori
│   ├── database.py             # Koneksi SQLite & SQLAlchemy session
│   ├── models.py               # Definisi tabel DB (Camera, Detection, Alert, dsb.)
│   ├── stream/
│   │   ├── reader.py           # StreamReader background thread & URL validator
│   │   └── health_checker.py   # Pemeriksa status kamera & auto-cleanup retensi
│   ├── detection/
│   │   ├── yolo_engine.py      # Wrapper Ultralytics YOLO inference
│   │   └── postprocess.py      # Agregasi kelas & anotasi bounding box
│   ├── api/
│   │   ├── cameras.py          # REST API CRUD kamera & uji koneksi
│   │   ├── detections.py       # Query histori, statistik, ekspor CSV
│   │   ├── alerts.py           # Aturan alert & log peringatan
│   │   └── live.py             # Endpoint live MJPEG stream & WebSocket
│   └── workers/
│       └── camera_worker.py    # Worker loop per kamera & CameraManager
├── snapshots/                  # Direktori bukti snapshot gambar deteksi
├── models/                     # Direktori bobot model YOLO (*.pt)
├── static/
│   ├── css/
│   └── js/
│       └── app.js              # Logika frontend & interaksi realtime
├── templates/
│   └── index.html              # Antarmuka Dashboard CPM
├── requirements.txt            # Daftar paket dependensi
└── README.md
```

---

## ⚖️ Kepatuhan & Etika
- Pastikan penggunaan feed CCTV publik sesuai dengan *Terms of Service* (ToS) masing-masing pemerintah daerah.
- Sistem ini difokuskan pada pemantauan kepadatan lalu lintas dan keselamatan publik, tidak melakukan pengenalan wajah (*face recognition*) individu sesuai prinsip perlindungan privasi data pribadi.
