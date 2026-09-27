# Product Requirements Document (PRD)
## Aplikasi Monitoring CCTV Publik Berbasis Python + YOLO + SQLite

| Field | Detail |
|---|---|
| Nama Produk | CCTV Public Monitor (CPM) |
| Versi Dokumen | 1.0 |
| Tanggal | 27 September 2026 |
| Dibuat oleh | - |
| Status | Draft |

---

## 1. Latar Belakang

Banyak pemerintah daerah (Pemda) menyediakan akses publik ke feed CCTV kota melalui portal web (contoh: `cctvkanjeng.gresikkab.go.id`). Feed ini biasanya dapat dipantau langsung oleh manusia lewat browser, tetapi tidak ada sistem otomatis yang bisa:
- Mendeteksi objek (kendaraan, orang, kepadatan lalu lintas, dsb.) secara real-time.
- Mencatat kejadian/anomali ke dalam basis data untuk ditelusuri kembali.
- Memberi notifikasi ketika terjadi kondisi tertentu (misal kepadatan tinggi, objek mencurigakan, jalan kosong tiba-tiba).

Proyek ini bertujuan membangun aplikasi monitoring yang mengambil stream dari CCTV publik, memprosesnya dengan model deteksi objek open source (YOLO), dan menyimpan hasil analitik ke database SQLite untuk keperluan pelaporan dan pencarian historis.

### 1.1 Catatan Teknis Penting (Wajib Dibaca)

Link yang diberikan sebagai contoh:
```
blob:https://cctvkanjeng.gresikkab.go.id/507c3e19-6084-467d-85c8-d4ebd7c6e0ce
```
adalah **URL `blob:`**, yaitu referensi objek media yang dibuat secara lokal oleh JavaScript di dalam browser (via `URL.createObjectURL()`). URL semacam ini:
- **Tidak bisa diakses dari luar browser** yang membuatnya (tidak bisa di-fetch oleh Python, `ffmpeg`, OpenCV, dsb.).
- Bersifat sementara dan unik per sesi browser — akan hilang begitu tab ditutup atau di-refresh.

Agar aplikasi Python bisa membaca stream, kita perlu menemukan **URL stream asli** di balik player web tersebut, biasanya berupa salah satu dari:
- `HLS` (`.m3u8`)
- `DASH` (`.mpd`)
- `RTSP` (`rtsp://...`)
- `RTMP` (`rtmp://...`)
- MJPEG / HTTP progressive stream

**Cara menemukannya:** buka halaman CCTV di browser desktop, buka DevTools → tab *Network* → filter `Media` atau `XHR`, lalu cari request yang berulang ke file `.m3u8`, `.mpd`, atau koneksi `ws/rtsp`. URL itulah yang dipakai di konfigurasi aplikasi ini, bukan URL `blob:`.

Dokumen PRD ini mengasumsikan aplikasi akan mengonsumsi URL stream asli (HLS/RTSP/MJPEG), dengan `blob:` URL sebagai representasi UI di sisi klien saja.

---

## 2. Tujuan Produk (Goals)

1. Menyediakan sistem monitoring CCTV publik otomatis berbasis deteksi objek open source.
2. Menyimpan hasil deteksi (jenis objek, jumlah, waktu, confidence score, snapshot) ke SQLite.
3. Menyediakan dashboard sederhana untuk melihat live feed + hasil deteksi.
4. Memungkinkan pencarian/filter riwayat deteksi berdasarkan waktu, kamera, dan jenis objek.
5. Bersifat modular agar mudah menambah kamera baru (multi-CCTV) dan mengganti model deteksi.

### 2.1 Non-Goals (Di Luar Cakupan v1.0)
- Tidak melakukan face recognition atau identifikasi pribadi individu.
- Tidak melakukan tracking lintas kamera (re-identification).
- Tidak menyediakan hosting cloud skala besar; fokus pada single-server/local deployment.
- Tidak menangani legalitas privasi data publik secara otomatis (lihat bagian Kepatuhan & Etika).

---

## 3. Target Pengguna

| Persona | Kebutuhan |
|---|---|
| Operator Dishub/Satpol PP | Memantau kepadatan lalu lintas & insiden secara real-time |
| Admin IT Pemda | Mengelola daftar kamera, kesehatan sistem, dan performa model |
| Analis Data/Peneliti | Mengambil data historis deteksi untuk laporan/statistik |

---

## 4. Ruang Lingkup Fitur (Scope)

### 4.1 Fitur Inti (Must Have)
- **Manajemen Sumber CCTV**: tambah/edit/hapus kamera (nama, lokasi, URL stream, status aktif).
- **Stream Ingestion**: menarik frame dari stream (HLS/RTSP/MJPEG) menggunakan OpenCV/ffmpeg.
- **Deteksi Objek Real-Time**: menjalankan model YOLO open source (YOLOv8/YOLOv9/YOLO-NAS via Ultralytics) pada setiap frame/interval tertentu.
- **Penyimpanan Hasil Deteksi**: simpan metadata deteksi (kelas objek, jumlah, confidence, timestamp, kamera) ke SQLite.
- **Snapshot Bukti**: simpan gambar/frame saat deteksi penting terjadi (opsional, disimpan ke disk dengan path direferensikan di DB).
- **Dashboard Web (lokal)**: tampilan live feed + bounding box + statistik ringkas.
- **Pencarian & Filter Riwayat**: filter berdasarkan kamera, rentang waktu, jenis objek, dan ambang confidence.
- **Notifikasi/Alert Dasar**: aturan sederhana (misal: jumlah kendaraan > N dalam periode X → tandai "padat").
- **Logging & Monitoring Kesehatan**: status koneksi tiap kamera (online/offline/error), FPS pemrosesan.

### 4.2 Fitur Tambahan (Nice to Have / v2.0)
- Multi-user login dengan role-based access.
- Export laporan ke PDF/Excel.
- Integrasi notifikasi ke Telegram/WhatsApp/Email.
- Heatmap kepadatan berdasarkan waktu.
- Dukungan GPU acceleration (CUDA) untuk performa lebih tinggi.
- Auto-reconnect stream dengan exponential backoff.

---

## 5. Arsitektur Sistem

### 5.1 Gambaran Umum
```
[CCTV Publik] --(HLS/RTSP/MJPEG)--> [Stream Reader (OpenCV/ffmpeg)]
        --> [Frame Queue]
        --> [YOLO Inference Worker]
        --> [Post-Processing: filter kelas, hitung objek, threshold]
        --> [SQLite Database]  <--query--  [Web Dashboard (Flask/FastAPI)]
                                                     |
                                              [Browser Operator]
```

### 5.2 Komponen Utama

| Komponen | Teknologi yang Disarankan | Fungsi |
|---|---|---|
| Stream Reader | `OpenCV` (`cv2.VideoCapture`) atau `ffmpeg-python` | Menarik frame dari URL stream |
| Model Deteksi | `Ultralytics YOLOv8/YOLOv11` (open source, lisensi AGPL/GPL) | Deteksi objek per frame |
| Backend/API | `FastAPI` atau `Flask` | Endpoint REST + WebSocket untuk live feed |
| Database | `SQLite` (via `SQLAlchemy` atau `sqlite3` native) | Penyimpanan metadata & histori |
| Task/Worker | `threading` / `multiprocessing` atau `Celery` (opsional untuk skala lebih besar) | Menjalankan inference secara paralel per kamera |
| Frontend Dashboard | `HTML/JS` sederhana, atau `Streamlit` untuk prototipe cepat | Visualisasi live feed & statistik |
| Scheduler | `APScheduler` | Menjalankan tugas berkala (cleanup, agregasi statistik) |

### 5.3 Alur Data Deteksi
1. Stream reader mengambil frame baru setiap interval (misal setiap 1 detik, bukan setiap frame agar hemat resource).
2. Frame dikirim ke YOLO inference worker.
3. Model mengembalikan daftar bounding box + kelas + confidence.
4. Sistem menyaring hasil sesuai aturan (kelas relevan: `person`, `car`, `motorcycle`, `truck`, `bus`).
5. Hasil agregat (jumlah per kelas per interval) disimpan ke tabel `detections`.
6. Jika snapshot diaktifkan dan confidence melewati threshold, frame disimpan ke folder `snapshots/` dan path-nya dicatat.
7. Dashboard mengambil data terbaru via polling/WebSocket untuk ditampilkan real-time.

---

## 6. Skema Database (SQLite)

```sql
-- Tabel kamera/sumber CCTV
CREATE TABLE cameras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    location TEXT,
    stream_url TEXT NOT NULL,       -- URL stream asli (HLS/RTSP/MJPEG), BUKAN blob:
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Tabel hasil deteksi (agregat per interval)
CREATE TABLE detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id INTEGER NOT NULL,
    detected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    object_class TEXT NOT NULL,     -- contoh: 'car', 'person', 'motorcycle'
    object_count INTEGER NOT NULL,
    avg_confidence REAL,
    snapshot_path TEXT,             -- nullable, path file gambar bukti
    FOREIGN KEY (camera_id) REFERENCES cameras(id)
);

-- Tabel deteksi mentah per objek (opsional, untuk detail bounding box)
CREATE TABLE detection_boxes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    detection_id INTEGER NOT NULL,
    class_name TEXT NOT NULL,
    confidence REAL NOT NULL,
    x1 REAL, y1 REAL, x2 REAL, y2 REAL,
    FOREIGN KEY (detection_id) REFERENCES detections(id)
);

-- Tabel status kesehatan kamera
CREATE TABLE camera_health_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id INTEGER NOT NULL,
    status TEXT NOT NULL,           -- 'online', 'offline', 'error'
    message TEXT,
    logged_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (camera_id) REFERENCES cameras(id)
);

-- Tabel aturan alert (opsional)
CREATE TABLE alert_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id INTEGER,
    object_class TEXT,
    threshold_count INTEGER,
    time_window_seconds INTEGER,
    is_active BOOLEAN DEFAULT 1
);

CREATE TABLE alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER,
    camera_id INTEGER,
    triggered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    details TEXT,
    FOREIGN KEY (rule_id) REFERENCES alert_rules(id),
    FOREIGN KEY (camera_id) REFERENCES cameras(id)
);
```

---

## 7. Kebutuhan Fungsional (Functional Requirements)

| ID | Requirement | Prioritas |
|---|---|---|
| FR-01 | Sistem dapat menambahkan kamera baru dengan input nama, lokasi, dan URL stream. | Must |
| FR-02 | Sistem dapat memvalidasi apakah URL stream dapat diakses sebelum disimpan. | Should |
| FR-03 | Sistem dapat menjalankan inference YOLO pada frame yang diambil dari stream. | Must |
| FR-04 | Sistem dapat menyimpan hasil deteksi (kelas, jumlah, waktu, confidence) ke SQLite. | Must |
| FR-05 | Sistem dapat menampilkan live feed dengan bounding box di dashboard. | Must |
| FR-06 | Sistem dapat memfilter riwayat deteksi berdasarkan kamera, tanggal, dan kelas objek. | Must |
| FR-07 | Sistem dapat mencatat status online/offline tiap kamera secara berkala. | Should |
| FR-08 | Sistem dapat memicu alert sederhana berdasarkan aturan ambang batas. | Should |
| FR-09 | Sistem dapat menyimpan snapshot gambar saat deteksi signifikan terjadi. | Should |
| FR-10 | Sistem dapat menghapus otomatis data/snapshot lama sesuai kebijakan retensi. | Could |
| FR-11 | Sistem dapat mengekspor hasil deteksi ke CSV. | Could |

---

## 8. Kebutuhan Non-Fungsional (Non-Functional Requirements)

| Kategori | Kebutuhan |
|---|---|
| Performa | Mampu memproses minimal 1 frame/detik per kamera pada CPU standar (tanpa GPU); direkomendasikan model ringan (YOLOv8n/YOLOv8s) untuk real-time di CPU. |
| Skalabilitas | Arsitektur modular agar mudah menambah kamera tanpa mengubah struktur inti. |
| Reliabilitas | Auto-reconnect jika koneksi stream terputus; sistem tidak crash total jika satu kamera gagal. |
| Keamanan | Autentikasi dasar untuk akses dashboard; validasi input URL untuk mencegah SSRF. |
| Portabilitas | Dapat dijalankan di Windows/Linux dengan Python 3.10+. |
| Observability | Logging terstruktur (level INFO/WARNING/ERROR) untuk debugging. |
| Penyimpanan | Rotasi/retensi snapshot untuk mencegah disk penuh (misal simpan maksimal 30 hari). |

---

## 9. Tech Stack yang Direkomendasikan

| Layer | Pilihan |
|---|---|
| Bahasa | Python 3.10+ |
| Model Deteksi | Ultralytics YOLOv8 / YOLOv11 (open source) |
| Computer Vision | OpenCV (`opencv-python`) |
| Stream Handling | `ffmpeg` (subprocess) atau `cv2.VideoCapture` dengan backend FFMPEG |
| Backend Framework | FastAPI (async, cocok untuk WebSocket live feed) |
| Database | SQLite + SQLAlchemy ORM |
| Realtime UI | WebSocket (FastAPI) + HTML/JS (atau Streamlit untuk MVP cepat) |
| Task Scheduling | APScheduler |
| Environment Management | `venv` atau `conda` |
| Deployment | Docker (opsional), Uvicorn/Gunicorn sebagai ASGI server |

### Contoh Dependensi (`requirements.txt`)
```
ultralytics
opencv-python
fastapi
uvicorn[standard]
sqlalchemy
apscheduler
python-multipart
websockets
```

---

## 10. Struktur Proyek yang Disarankan

```
cctv-monitor/
├── app/
│   ├── main.py                 # entry point FastAPI
│   ├── config.py                # konfigurasi (path model, threshold, dsb.)
│   ├── database.py              # koneksi & session SQLAlchemy
│   ├── models.py                # ORM models (cameras, detections, dst.)
│   ├── stream/
│   │   ├── reader.py             # kelas StreamReader (OpenCV/ffmpeg)
│   │   └── health_checker.py     # cek status kamera berkala
│   ├── detection/
│   │   ├── yolo_engine.py        # wrapper load model & inference
│   │   └── postprocess.py        # agregasi hasil deteksi
│   ├── api/
│   │   ├── cameras.py            # endpoint CRUD kamera
│   │   ├── detections.py         # endpoint query histori
│   │   └── live.py               # endpoint WebSocket live feed
│   └── workers/
│       └── camera_worker.py      # loop utama per kamera (thread/process)
├── snapshots/                    # penyimpanan gambar bukti deteksi
├── models/
│   └── yolov8n.pt                # bobot model open source
├── static/ & templates/          # dashboard sederhana
├── requirements.txt
└── README.md
```

---

## 11. User Stories

1. **Sebagai operator**, saya ingin menambahkan URL kamera baru agar sistem mulai memantaunya.
2. **Sebagai operator**, saya ingin melihat live feed dengan bounding box agar bisa memverifikasi deteksi secara visual.
3. **Sebagai analis**, saya ingin memfilter riwayat deteksi kendaraan pada rentang tanggal tertentu untuk membuat laporan kepadatan lalu lintas.
4. **Sebagai admin IT**, saya ingin melihat status online/offline semua kamera dalam satu halaman agar bisa cepat menindaklanjuti gangguan.
5. **Sebagai operator**, saya ingin menerima notifikasi ketika jumlah kendaraan di suatu titik melebihi ambang batas tertentu.

---

## 12. Kepatuhan & Etika (Compliance & Ethics)

Karena aplikasi ini mengakses CCTV milik pihak lain (Pemda), beberapa hal perlu diperhatikan sebelum implementasi produksi:
- **Izin akses**: pastikan penggunaan feed CCTV publik sesuai dengan ketentuan penggunaan (ToS) yang ditetapkan oleh penyedia (Pemda/Dishub setempat). Beberapa portal CCTV publik menyediakan API resmi atau syarat penggunaan tertentu.
- **Privasi**: hindari penyimpanan data yang bisa mengidentifikasi individu secara spesifik (misal plat nomor, wajah) kecuali memang menjadi kebutuhan resmi instansi dan sudah sesuai regulasi perlindungan data pribadi (UU PDP di Indonesia).
- **Retensi data**: terapkan kebijakan retensi yang wajar untuk snapshot dan histori deteksi.

Bagian ini sifatnya informatif; keputusan kepatuhan akhir tetap berada pada tim/instansi yang menjalankan proyek.

---

## 13. Rencana Pengembangan (Roadmap)

| Fase | Durasi (estimasi) | Output |
|---|---|---|
| Fase 1: Setup & Riset Stream | 1 minggu | Menemukan URL stream asli, setup project skeleton, koneksi SQLite |
| Fase 2: Integrasi YOLO | 1-2 minggu | Model dapat mendeteksi objek dari 1 kamera, hasil tersimpan di DB |
| Fase 3: Multi-Kamera & Worker | 1 minggu | Mendukung banyak kamera secara paralel |
| Fase 4: Dashboard Web | 1-2 minggu | UI live feed + histori + filter |
| Fase 5: Alert & Health Monitoring | 1 minggu | Notifikasi dasar + status kamera |
| Fase 6: Testing & Optimasi | 1 minggu | Load testing, optimasi performa CPU/GPU |

---

## 14. Risiko & Mitigasi

| Risiko | Dampak | Mitigasi |
|---|---|---|
| URL stream (`blob:`) tidak bisa diakses langsung | Sistem gagal menarik feed | Temukan URL asli via DevTools; gunakan proxy/reverse-engineer jika portal memiliki API internal |
| Beban komputasi tinggi jika banyak kamera + YOLO real-time | Lag/drop frame | Kurangi resolusi input, gunakan model ringan (YOLOv8n), proses per-N-frame, pertimbangkan GPU |
| Stream CCTV publik sering putus-putus | Data tidak konsisten | Implementasi auto-reconnect & logging status kesehatan |
| Perubahan struktur portal CCTV oleh Pemda | URL stream berubah sewaktu-waktu | Buat mekanisme validasi URL berkala + alert ke admin jika gagal |
| Isu privasi/legalitas akses CCTV publik | Risiko hukum/etika | Tinjau ToS penyedia CCTV, batasi penggunaan sesuai izin resmi |

---

## 15. Kriteria Keberhasilan (Success Metrics)

- Sistem mampu memproses minimal 1 kamera secara stabil selama >90% waktu operasional dalam sehari.
- Latensi antara frame diambil dan hasil deteksi tersimpan < 3 detik (pada CPU standar).
- Akurasi deteksi objek dasar (kendaraan/orang) sesuai benchmark model YOLO yang dipakai (≥ mAP standar model pretrained di COCO dataset).
- Dashboard dapat menampilkan minimal 10 histori deteksi terbaru tanpa lag signifikan.

---

## 16. Lampiran: Contoh Kode Inti (Ilustrasi Struktur, Bukan Implementasi Penuh)

### 16.1 Stream Reader (ilustrasi)
```python
import cv2

class StreamReader:
    def __init__(self, stream_url: str):
        self.stream_url = stream_url
        self.cap = cv2.VideoCapture(stream_url)

    def read_frame(self):
        if not self.cap.isOpened():
            self.cap.open(self.stream_url)
        ret, frame = self.cap.read()
        return frame if ret else None
```

### 16.2 YOLO Inference (ilustrasi)
```python
from ultralytics import YOLO

class YoloEngine:
    def __init__(self, model_path: str = "models/yolov8n.pt"):
        self.model = YOLO(model_path)

    def detect(self, frame):
        results = self.model(frame, verbose=False)
        return results[0]  # berisi boxes, classes, confidences
```

### 16.3 Menyimpan Hasil ke SQLite (ilustrasi, via SQLAlchemy)
```python
from sqlalchemy.orm import Session
from app.models import Detection

def save_detection(db: Session, camera_id: int, object_class: str, count: int, avg_conf: float):
    detection = Detection(
        camera_id=camera_id,
        object_class=object_class,
        object_count=count,
        avg_confidence=avg_conf
    )
    db.add(detection)
    db.commit()
```

> Catatan: contoh di atas hanya ilustrasi struktur kode inti untuk kebutuhan perencanaan. Implementasi lengkap (error handling, threading per kamera, konfigurasi model, dsb.) akan dikembangkan pada tahap development sesuai roadmap di Bagian 13.

---

## 17. Referensi Teknologi Open Source

- Ultralytics YOLO (YOLOv8/YOLOv11) — deteksi objek real-time, open source (lisensi AGPL-3.0, perlu diperhatikan untuk penggunaan komersial).
- OpenCV — pemrosesan citra dan pembacaan stream video.
- FastAPI — framework backend modern berbasis async Python.
- SQLite — database ringan tanpa server terpisah, cocok untuk aplikasi single-instance.

---

*Dokumen ini adalah rancangan awal (v1.0) dan dapat disesuaikan lebih lanjut sesuai kebutuhan spesifik instansi/tim pengembang.*
