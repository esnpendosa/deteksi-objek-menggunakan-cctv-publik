# 📚 Panduan Lengkap: Membangun Aplikasi Monitoring CCTV Publik Berbasis Python, YOLOv8, dan SQLite

Tutorial ini menjelaskan langkah demi langkah cara membangun sistem **CCTV Public Monitor (CPM)** dari awal (dari nol). Sistem ini mampu menarik video stream CCTV publik dari internet secara real-time, mendeteksi objek (kendaraan dan orang) menggunakan kecerdasan buatan (AI) YOLOv8, menyimpan hasil analitik ke database SQLite, serta menyajikannya dalam dashboard web interaktif lengkap dengan WebSocket dan peringatan dini (*alerting*).

---

## 📑 Daftar Isi
1. [Konsep & Arsitektur Sistem](#1-konsep--arsitektur-sistem)
2. [Prasyarat & Persiapan Lingkungan](#2-prasyarat--persiapan-lingkungan)
3. [Trik Mendapatkan URL Stream Asli CCTV (Menembus URL `blob:`)](#3-trik-mendapatkan-url-stream-asli-cctv-menembus-url-blob)
4. [Struktur Direktori Proyek](#4-struktur-direktori-proyek)
5. [Langkah 1: Konfigurasi Sistem (`app/config.py`)](#5-langkah-1-konfigurasi-sistem-appconfigpy)
6. [Langkah 2: Database & Model ORM (`app/database.py` & `app/models.py`)](#6-langkah-2-database--model-orm-appdatabasepy--appmodelspy)
7. [Langkah 3: Stream Ingestion Threading (`app/stream/reader.py`)](#7-langkah-3-stream-ingestion-threading-appstreamreaderpy)
8. [Langkah 4: AI YOLO Engine & Filter Geometri Spasial (`app/detection/`)](#8-langkah-4-ai-yolo-engine--filter-geometri-spasial-appdetection)
9. [Langkah 5: Worker Per Kamera & Health Checker (`app/workers/` & `app/stream/`)](#9-langkah-5-worker-per-kamera--health-checker)
10. [Langkah 6: REST API, Streaming MJPEG, & WebSocket (`app/api/`)](#10-langkah-6-rest-api-streaming-mjpeg--websocket-appapi)
11. [Langkah 7: Entry Point & Lifespan FastAPI (`app/main.py`)](#11-langkah-7-entry-point--lifespan-fastapi-appmainpy)
12. [Langkah 8: Dashboard Web Frontend (`templates/index.html` & `static/js/app.js`)](#12-langkah-8-dashboard-web-frontend)
13. [Langkah 9: Pengujian Otomatis (`tests/test_cpm.py`)](#13-langkah-9-pengujian-otomatis-teststest_cpmpy)
14. [Langkah 10: Menjalankan Proyek](#14-langkah-10-menjalankan-proyek)
15. [Troubleshooting & Tips Optimasi](#15-troubleshooting--tips-optimasi)

---

## 1. Konsep & Arsitektur Sistem

Banyak portal CCTV pemerintah daerah (Dishub/Kominfo) menyediakan video siaran langsung di web. Namun, siaran tersebut hanya dipantau manusia secara manual tanpa analitik data.

Arsitektur aplikasi ini bekerja dengan alur sebagai berikut:

```
[ CCTV Publik (HLS .m3u8 / RTSP) ]
               │
               ▼
   [ StreamReader (OpenCV) ] ── (Background Threading Buffer Frame Terkini)
               │
               ▼
   [ YoloEngine (YOLOv8s) ] ── (Inference per Interval 1 Detik)
               │
               ▼
   [ Spatial Geometry Filter ] ── (Menyaring False Positive: Batu / Objek Palsu)
               │
        ┌──────┴────────────────────────┐
        ▼                               ▼
[ SQLite Database ]             [ Snapshots Disk ]
(Tabel Detections, Alerts)      (Bukti Gambar *.jpg)
        │                               │
        └──────────────┬────────────────┘
                       ▼
             [ FastAPI Backend ]
        (REST API + MJPEG + WebSocket)
                       │
                       ▼
            [ Web Dashboard UI ]
         (Live Feed + Histori + Alert)
```

---

## 2. Prasyarat & Persiapan Lingkungan

### A. Kebutuhan Sistem
* **Python**: Versi 3.10 atau yang lebih baru (disarankan 3.10 – 3.12 / 3.14).
* **Git**: Untuk version control.
* **Koneksi Internet**: Untuk mengunduh bobot model awal (*weights*) dan menarik stream HLS.

### B. Membuat Virtual Environment (Opsional tetapi Disarankan)
Buka terminal / PowerShell di folder proyek Anda:
```bash
python -m venv venv
# Mengaktifkan di Windows PowerShell:
.\venv\Scripts\Activate.ps1
```

### C. File `requirements.txt`
Buat file `requirements.txt` dengan isi berikut:
```txt
ultralytics>=8.0.0
opencv-python>=4.8.0
fastapi>=0.100.0
uvicorn[standard]>=0.23.0
websockets>=11.0
sqlalchemy>=2.0.0
apscheduler>=3.10.0
python-multipart>=0.0.6
pydantic>=2.0.0
jinja2>=3.1.0
aiofiles>=23.0.0
numpy>=1.24.0
pytest>=8.0.0
```

Instal semua pustaka di atas:
```bash
pip install -r requirements.txt
```

---

## 3. Trik Mendapatkan URL Stream Asli CCTV (Menembus URL `blob:`)

Portal CCTV Pemda (seperti `cctvkanjeng.gresikkab.go.id`) sering kali menampilkan pemutar video dengan URL seperti:
```
blob:https://cctvkanjeng.gresikkab.go.id/507c3e19-6084-467d-85c8-d4ebd7c6e0ce
```

> ⚠️ **Catatan Penting:** URL berawalan `blob:` adalah objek lokal dalam memori browser klien via `URL.createObjectURL()`. Server Python, OpenCV, dan FFmpeg **tidak bisa** membaca URL `blob:`.

### Cara Menemukan URL Stream Asli:
1. Buka halaman CCTV publik di browser (Chrome/Edge/Firefox).
2. Tekan tombol **F12** (atau klik kanan &rarr; **Inspect**) untuk membuka DevTools.
3. Masuk ke tab **Network**.
4. Di bilah filter, pilih **Fetch/XHR** atau ketik `.m3u8`.
5. Muat ulang halaman (Refresh `F5`) dan tekan tombol *Play* pada video CCTV.
6. Perhatikan request yang berulang dengan format:
   * `https://cctvkanjeng.gresikkab.go.id/hls/pasar-bungah-2/index.m3u8`
   * `https://cctvkanjeng.gresikkab.go.id/hls/perempatan-sedayu-2/index.m3u8`
7. Klik kanan pada request tersebut &rarr; pilih **Copy link address**. URL inilah yang valid untuk dimasukkan ke sistem.

---

## 4. Struktur Direktori Proyek

Buat struktur folder berikut di dalam proyek Anda:

```
cctv-monitor/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI Application & Lifespan
│   ├── config.py               # Pengaturan sistem & konstanta
│   ├── database.py             # Koneksi engine & session SQLAlchemy
│   ├── models.py               # Skema ORM Database SQLite
│   ├── stream/
│   │   ├── __init__.py
│   │   ├── reader.py           # Threading StreamReader & validator
│   │   └── health_checker.py   # Pemeriksa status kamera & auto-retensi
│   ├── detection/
│   │   ├── __init__.py
│   │   ├── yolo_engine.py      # Wrapper Ultralytics YOLO
│   │   └── postprocess.py      # Filter geometri & anotasi visual
│   ├── api/
│   │   ├── __init__.py
│   │   ├── cameras.py          # Endpoint CRUD kamera
│   │   ├── detections.py       # Endpoint query histori & ekspor CSV
│   │   ├── alerts.py           # Endpoint aturan alert & log
│   │   └── live.py             # Endpoint live MJPEG stream & WebSocket
│   └── workers/
│       ├── __init__.py
│       └── camera_worker.py    # Worker loop per kamera & CameraManager
├── snapshots/                  # Tempat penyimpanan bukti gambar deteksi
├── models/                     # Tempat file bobot YOLO (*.pt)
├── static/
│   └── js/
│       └── app.js              # Frontend UI logic & WebSocket client
├── templates/
│   └── index.html              # Antarmuka Dashboard Web
├── tests/
│   └── test_cpm.py             # Unit test otomatis
├── requirements.txt
├── run.bat                     # Windows double-click launcher
└── README.md
```

---

## 5. Langkah 1: Konfigurasi Sistem (`app/config.py`)

File ini bertugas mengelola variabel lingkungan, direktori penyimpanan, serta ambang batas parameter model.

```python
import os
from pathlib import Path
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseModel):
    PROJECT_NAME: str = "CCTV Public Monitor (CPM)"
    VERSION: str = "1.0.0"
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'cctv_monitor.db'}")
    
    BASE_DIR: Path = BASE_DIR
    MODELS_DIR: Path = BASE_DIR / "models"
    SNAPSHOTS_DIR: Path = BASE_DIR / "snapshots"
    STATIC_DIR: Path = BASE_DIR / "static"
    TEMPLATES_DIR: Path = BASE_DIR / "templates"
    
    # Gunakan YOLOv8s untuk akurasi optimal & false positive rendah
    DEFAULT_MODEL_NAME: str = "yolov8s.pt"
    CONFIDENCE_THRESHOLD: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.40"))
    VEHICLE_CONFIDENCE_THRESHOLD: float = float(os.getenv("VEHICLE_CONFIDENCE_THRESHOLD", "0.48"))
    
    # Interval deteksi: 1 detik per kamera untuk menghemat beban CPU
    DETECTION_INTERVAL_SECONDS: float = float(os.getenv("DETECTION_INTERVAL_SECONDS", "1.0"))
    
    TARGET_CLASSES: list[str] = [
        "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat"
    ]
    
    STREAM_CONNECT_TIMEOUT: int = 10
    HEALTH_CHECK_INTERVAL_SECONDS: int = 60
    RETENTION_DAYS: int = 30

settings = Settings()
settings.MODELS_DIR.mkdir(parents=True, exist_ok=True)
settings.SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
```

---

## 6. Langkah 2: Database & Model ORM (`app/database.py` & `app/models.py`)

### A. File `app/database.py`
Konfigurasi SQLite dengan opsi multi-thread agar aman diakses oleh background worker dan API secara bersamaan:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings

connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### B. File `app/models.py`
Mendefinisikan skema tabel:
1. `cameras`: Data CCTV (nama, lokasi, stream_url, is_active).
2. `detections`: Catatan agregat jumlah objek per kelas dan confidence rata-rata.
3. `detection_boxes`: Bounding box mentah per objek.
4. `camera_health_logs`: Status kesehatan koneksi (`online`, `offline`, `error`).
5. `alert_rules`: Aturan ambang batas (misal: mobil &ge; 5).
6. `alerts`: Riwayat peringatan yang terpicu.

```python
import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base

class Camera(Base):
    __tablename__ = "cameras"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, nullable=False)
    location = Column(String, nullable=True)
    stream_url = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    detections = relationship("Detection", back_populates="camera", cascade="all, delete-orphan")
    health_logs = relationship("CameraHealthLog", back_populates="camera", cascade="all, delete-orphan")
    alert_rules = relationship("AlertRule", back_populates="camera", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="camera", cascade="all, delete-orphan")

class Detection(Base):
    __tablename__ = "detections"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=False, index=True)
    detected_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    object_class = Column(String, nullable=False, index=True)
    object_count = Column(Integer, nullable=False)
    avg_confidence = Column(Float, nullable=True)
    snapshot_path = Column(String, nullable=True)

    camera = relationship("Camera", back_populates="detections")
    boxes = relationship("DetectionBox", back_populates="detection", cascade="all, delete-orphan")

class DetectionBox(Base):
    __tablename__ = "detection_boxes"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    detection_id = Column(Integer, ForeignKey("detections.id"), nullable=False, index=True)
    class_name = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    x1 = Column(Float, nullable=True); y1 = Column(Float, nullable=True)
    x2 = Column(Float, nullable=True); y2 = Column(Float, nullable=True)
    detection = relationship("Detection", back_populates="boxes")

class CameraHealthLog(Base):
    __tablename__ = "camera_health_logs"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=False, index=True)
    status = Column(String, nullable=False)
    message = Column(Text, nullable=True)
    logged_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    camera = relationship("Camera", back_populates="health_logs")

class AlertRule(Base):
    __tablename__ = "alert_rules"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=True, index=True)
    object_class = Column(String, nullable=False)
    threshold_count = Column(Integer, nullable=False)
    time_window_seconds = Column(Integer, default=60)
    is_active = Column(Boolean, default=True)
    camera = relationship("Camera", back_populates="alert_rules")
    alerts = relationship("Alert", back_populates="rule", cascade="all, delete-orphan")

class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    rule_id = Column(Integer, ForeignKey("alert_rules.id"), nullable=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=False, index=True)
    triggered_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    details = Column(Text, nullable=True)
    rule = relationship("AlertRule", back_populates="alerts")
    camera = relationship("Camera", back_populates="alerts")
```

---

## 7. Langkah 3: Stream Ingestion Threading (`app/stream/reader.py`)

Masalah umum membaca stream live video dengan OpenCV adalah **buffer lag** (keterlambatan frame akibat antrean buffer internal). 

Untuk mengatasinya, dibuat kelas `StreamReader` yang menjalankan sebuah *background daemon thread*. Thread ini terus-menerus mengambil frame terbaru dan menyimpannya di memori, sehingga saat aplikasi meminta frame, aplikasi selalu mendapatkan frame paling baru tanpa lag, dilengkapi *auto-reconnect*.

```python
import cv2, time, logging, threading
from typing import Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)

class StreamReader:
    def __init__(self, stream_url: str, reconnect_delay: float = 3.0):
        self.stream_url = stream_url
        self.reconnect_delay = reconnect_delay
        self.cap: Optional[cv2.VideoCapture] = None
        self._latest_frame: Optional[np.ndarray] = None
        self._lock = threading.Lock()
        
        self.is_running = False
        self.is_connected = False
        self.last_error: Optional[str] = None
        self.fps_counter: float = 0.0
        self._frame_count = 0
        self._fps_start_time = time.time()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self.is_running: return
        self.is_running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.is_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._release_cap()
        self.is_connected = False

    def _release_cap(self):
        if self.cap:
            try: self.cap.release()
            except: pass
            self.cap = None

    def _connect(self) -> bool:
        self._release_cap()
        try:
            cap = cv2.VideoCapture(self.stream_url)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1) # Set buffer seminimal mungkin
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    self.cap = cap
                    self.is_connected = True
                    self.last_error = None
                    with self._lock:
                        self._latest_frame = frame
                    return True
            self.last_error = "Tidak dapat membuka stream URL"
        except Exception as e:
            self.last_error = str(e)
        self.is_connected = False
        return False

    def _capture_loop(self):
        attempts = 0
        while self.is_running:
            if not self.is_connected or self.cap is None or not self.cap.isOpened():
                if not self._connect():
                    attempts += 1
                    time.sleep(min(self.reconnect_delay * (1.2 ** min(attempts, 5)), 20.0))
                    continue
                else: attempts = 0

            ret, frame = self.cap.read()
            if not ret or frame is None:
                self.is_connected = False
                time.sleep(1.0)
                continue

            now = time.time()
            with self._lock:
                self._latest_frame = frame
                self._frame_count += 1
                if now - self._fps_start_time >= 3.0:
                    self.fps_counter = round(self._frame_count / (now - self._fps_start_time), 1)
                    self._frame_count = 0
                    self._fps_start_time = now

    def get_latest_frame(self) -> Optional[np.ndarray]:
        with self._lock:
            return self._latest_frame.copy() if self._latest_frame is not None else None

def validate_stream_url(url: str, timeout_seconds: int = 5) -> Tuple[bool, str]:
    if not url or not isinstance(url, str):
        return False, "Stream URL tidak boleh kosong."
    if url.strip().startswith("blob:"):
        return False, "URL 'blob:' adalah objek browser lokal. Harap gunakan URL HLS (.m3u8) asli."
    try:
        cap = cv2.VideoCapture(url.strip())
        start = time.time()
        while time.time() - start < timeout_seconds:
            if cap.isOpened():
                ret, frame = cap.read()
                cap.release()
                if ret and frame is not None:
                    h, w = frame.shape[:2]
                    return True, f"Stream valid. Resolusi: {w}x{h}"
            time.sleep(0.5)
        cap.release()
        return False, "Timeout saat menghubungi stream URL."
    except Exception as e:
        return False, str(e)
```

---

## 8. Langkah 4: AI YOLO Engine & Filter Geometri Spasial (`app/detection/`)

### A. Masalah Objek Palsu (False Positive): Batu Terdeteksi Mobil
Pada kamera CCTV jalanan malam hari, batu atau ember kecil di trotoar dapat memiliki tekstur atau pantulan cahaya yang mirip dengan kap mobil. Model YOLO ukuran kecil (`yolov8n`) bisa keliru mendeteksi batu tersebut sebagai `car`.

### B. Solusi: Filter Geometri & Perspektif Fisik
Dalam ilmu computer vision untuk CCTV:
* Di bagian **bawah gambar (foreground / dekat kamera)**, mobil asli **pasti berukuran besar** (lebar &ge; 48px, tinggi &ge; 38px, luas area &ge; 2000px).
* Objek kecil berukuran 33x32 piksel di area foreground secara hukum perspektif **mustahil merupakan mobil**.
* Dibuat fungsi `validate_detection_geometry` untuk menolak anomali ini.

### B1. File `app/detection/postprocess.py`:
```python
from typing import List, Dict, Any, Tuple
import cv2, numpy as np

CLASS_COLORS = {
    "person": (255, 128, 0), "car": (0, 200, 255), "motorcycle": (0, 255, 128),
    "bus": (255, 0, 128), "truck": (0, 128, 255), "bicycle": (128, 255, 0),
}
DEFAULT_COLOR = (0, 255, 0)

def validate_detection_geometry(item: Dict[str, Any], frame_w: int = 640, frame_h: int = 480) -> bool:
    cls_name = item["class_name"].lower()
    conf = float(item["confidence"])
    x1, y1, x2, y2 = item["box"]
    w, h = x2 - x1, y2 - y1
    area = w * h
    y_center = (y1 + y2) / 2

    if cls_name in ["car", "truck", "bus"]:
        if conf < 0.45: return False
        
        # Perspektif: objek dekat (bawah) harus berukuran proporsional
        if y_center > frame_h * 0.40:
            if w < 48 or h < 38 or area < 2000:
                return False  # Menolak batu/ember trotoar
        elif y_center > frame_h * 0.25:
            if w < 28 or h < 24 or area < 700:
                return False
        else:
            if w < 16 or h < 14 or area < 250:
                return False

        aspect_ratio = w / max(h, 1)
        if aspect_ratio < 0.45 or aspect_ratio > 3.8:
            return False

    elif cls_name == "person":
        if conf < 0.35: return False
        if y_center > frame_h * 0.40 and h < 28: return False

    elif cls_name in ["motorcycle", "bicycle"]:
        if conf < 0.38: return False
        if y_center > frame_h * 0.40 and (h < 28 or area < 600): return False

    return True

def aggregate_detections(
    raw_detections: List[Dict[str, Any]],
    target_classes: List[str] = None,
    frame_shape: Tuple[int, int] = (480, 640)
) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    aggregated = {}
    filtered_boxes = []
    frame_h, frame_w = frame_shape[:2]

    for item in raw_detections:
        cls_name = item["class_name"].lower()
        if target_classes and cls_name not in target_classes: continue
        if not validate_detection_geometry(item, frame_w=frame_w, frame_h=frame_h):
            continue

        filtered_boxes.append(item)
        if cls_name not in aggregated:
            aggregated[cls_name] = {"class_name": cls_name, "count": 0, "conf_sum": 0.0, "avg_confidence": 0.0}
        aggregated[cls_name]["count"] += 1
        aggregated[cls_name]["conf_sum"] += float(item["confidence"])

    for cls_name, data in aggregated.items():
        if data["count"] > 0:
            data["avg_confidence"] = round(data["conf_sum"] / data["count"], 3)
        del data["conf_sum"]

    return aggregated, filtered_boxes

def annotate_frame(frame: np.ndarray, detections: List[Dict[str, Any]], fps: float = 0.0, camera_name: str = "") -> np.ndarray:
    annotated = frame.copy()
    h, w = annotated.shape[:2]

    for det in detections:
        cls_name = det["class_name"]
        conf = det["confidence"]
        x1, y1, x2, y2 = [int(v) for v in det["box"]]
        color = CLASS_COLORS.get(cls_name.lower(), DEFAULT_COLOR)

        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        label = f"{cls_name} {conf:.2f}"
        (label_w, label_h), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        top = max(y1, label_h + 5)
        cv2.rectangle(annotated, (x1, top - label_h - 4), (x1 + label_w + 6, top + baseline - 2), color, -1)
        cv2.putText(annotated, label, (x1 + 3, top - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)

    header = f"{camera_name} | {fps:.1f} FPS | Objek: {len(detections)}" if camera_name else f"{fps:.1f} FPS | Objek: {len(detections)}"
    cv2.rectangle(annotated, (10, 10), (10 + len(header) * 9 + 20, 36), (0, 0, 0), -1)
    cv2.putText(annotated, header, (18, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 200), 1, cv2.LINE_AA)
    return annotated
```

### B2. File `app/detection/yolo_engine.py`:
Wrapper pemuatan model YOLO Ultralytics yang otomatis mengunduh bobot bila belum tersedia di lokal:
```python
import logging
from typing import List, Dict, Any, Optional
import numpy as np
from ultralytics import YOLO

logger = logging.getLogger(__name__)

class YoloEngine:
    def __init__(self, model_path: str = "models/yolov8s.pt", conf_threshold: float = 0.40):
        self.model_path = model_path
        self.conf_threshold = conf_threshold
        self.model = YOLO(model_path)

    def detect(self, frame: np.ndarray, conf: Optional[float] = None) -> List[Dict[str, Any]]:
        threshold = conf if conf is not None else self.conf_threshold
        try:
            results = self.model.predict(source=frame, conf=threshold, verbose=False, device="cpu")
            if not results or len(results) == 0: return []
            result = results[0]
            if result.boxes is None: return []

            detections = []
            names = result.names
            for box in result.boxes:
                cls_id = int(box.cls[0].item())
                confidence = float(box.conf[0].item())
                xyxy = box.xyxy[0].tolist()
                detections.append({
                    "class_name": names.get(cls_id, str(cls_id)),
                    "confidence": round(confidence, 3),
                    "box": [round(c, 1) for c in xyxy]
                })
            return detections
        except Exception as e:
            logger.error(f"Inference error: {e}")
            return []
```

---

## 9. Langkah 5: Worker Per Kamera & Health Checker

### A. File `app/workers/camera_worker.py`
Setiap CCTV memiliki thread `CameraWorker` sendiri, sehingga jika satu kamera mengalami gangguan koneksi, kamera lainnya tetap berjalan normal (*fault tolerance*).

```python
import os, time, logging, threading, datetime
import cv2, numpy as np
from app.config import settings
from app.database import SessionLocal
from app.models import Camera, Detection, DetectionBox, AlertRule, Alert
from app.stream.reader import StreamReader
from app.detection.yolo_engine import YoloEngine
from app.detection.postprocess import aggregate_detections, annotate_frame

logger = logging.getLogger(__name__)

class CameraWorker:
    def __init__(self, camera_id: int, name: str, stream_url: str, yolo_engine: YoloEngine, detection_interval: float = 1.0):
        self.camera_id = camera_id
        self.name = name
        self.stream_url = stream_url
        self.yolo_engine = yolo_engine
        self.detection_interval = detection_interval
        self.target_classes = settings.TARGET_CLASSES

        self.reader = StreamReader(stream_url)
        self.is_running = False
        self._thread = None
        self._lock = threading.Lock()
        self._latest_annotated_frame = None
        self._latest_raw_frame = None
        self._latest_summary = {}
        self._latest_detections = []

    def start(self):
        if self.is_running: return
        self.is_running = True
        self.reader.start()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.is_running = False
        self.reader.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _run_loop(self):
        last_run = 0.0
        while self.is_running:
            now = time.time()
            frame = self.reader.get_latest_frame()
            if frame is None:
                time.sleep(0.1)
                continue

            with self._lock:
                self._latest_raw_frame = frame

            if now - last_run >= self.detection_interval:
                last_run = now
                self._process_frame(frame)
            time.sleep(0.03)

    def _process_frame(self, frame: np.ndarray):
        try:
            raw_dets = self.yolo_engine.detect(frame)
            aggregated, filtered_boxes = aggregate_detections(
                raw_dets, target_classes=self.target_classes, frame_shape=frame.shape[:2]
            )
            annotated = annotate_frame(frame, filtered_boxes, fps=self.reader.fps_counter, camera_name=self.name)

            with self._lock:
                self._latest_annotated_frame = annotated
                self._latest_detections = filtered_boxes
                self._latest_summary = {cls: d["count"] for cls, d in aggregated.items()}

            if aggregated:
                self._save_to_db(frame, aggregated, filtered_boxes)
        except Exception as e:
            logger.error(f"Process error cam {self.camera_id}: {e}")

    def _save_to_db(self, raw_frame, aggregated, filtered_boxes):
        db = SessionLocal()
        try:
            snapshot_path = None
            total_obj = sum(d["count"] for d in aggregated.values())
            
            # Cek Aturan Alert
            rules = db.query(AlertRule).filter(
                (AlertRule.camera_id == self.camera_id) | (AlertRule.camera_id == None),
                AlertRule.is_active == True
            ).all()

            triggered = []
            for r in rules:
                count = aggregated.get(r.object_class.lower(), {}).get("count", 0)
                if count >= r.threshold_count:
                    msg = f"Alert! {count} {r.object_class} (ambang: {r.threshold_count}) di {self.name}"
                    db.add(Alert(rule_id=r.id, camera_id=self.camera_id, details=msg))
                    triggered.append(msg)

            # Simpan snapshot jika alert terpicu atau kepadatan tinggi
            if triggered or total_obj >= 5:
                fname = f"cam_{self.camera_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"
                fpath = settings.SNAPSHOTS_DIR / fname
                cv2.imwrite(str(fpath), raw_frame)
                snapshot_path = f"snapshots/{fname}"

            for cls_name, data in aggregated.items():
                det = Detection(
                    camera_id=self.camera_id, object_class=cls_name,
                    object_count=data["count"], avg_confidence=data["avg_confidence"],
                    snapshot_path=snapshot_path
                )
                db.add(det)
                db.flush()
                for b in filtered_boxes:
                    if b["class_name"].lower() == cls_name:
                        bx = b["box"]
                        db.add(DetectionBox(detection_id=det.id, class_name=cls_name, confidence=b["confidence"],
                                           x1=bx[0], y1=bx[1], x2=bx[2], y2=bx[3]))
            db.commit()
        finally:
            db.close()

    def get_latest_annotated_frame(self):
        with self._lock:
            return self._latest_annotated_frame.copy() if self._latest_annotated_frame is not None else None

    def get_status(self):
        with self._lock:
            return {
                "camera_id": self.camera_id, "name": self.name, "is_running": self.is_running,
                "is_connected": self.reader.is_connected, "fps": self.reader.fps_counter,
                "last_error": self.reader.last_error, "latest_summary": self._latest_summary.copy(),
                "total_detections": len(self._latest_detections)
            }

class CameraManager:
    def __init__(self, yolo_engine: YoloEngine):
        self.yolo_engine = yolo_engine
        self.workers = {}
        self._lock = threading.Lock()

    def load_active_cameras(self):
        db = SessionLocal()
        try:
            for cam in db.query(Camera).filter(Camera.is_active == True).all():
                self.start_camera(cam.id, cam.name, cam.stream_url)
        finally: db.close()

    def start_camera(self, camera_id: int, name: str, stream_url: str):
        with self._lock:
            if camera_id in self.workers: self.workers[camera_id].stop()
            worker = CameraWorker(camera_id, name, stream_url, self.yolo_engine, settings.DETECTION_INTERVAL_SECONDS)
            worker.start()
            self.workers[camera_id] = worker

    def stop_camera(self, camera_id: int):
        with self._lock:
            if camera_id in self.workers:
                self.workers[camera_id].stop()
                del self.workers[camera_id]

    def stop_all(self):
        with self._lock:
            for w in self.workers.values(): w.stop()
            self.workers.clear()

    def get_worker(self, camera_id: int):
        with self._lock: return self.workers.get(camera_id)

_global_camera_manager = None
def get_global_camera_manager():
    global _global_camera_manager
    if _global_camera_manager is None:
        engine = YoloEngine(str(settings.MODELS_DIR / settings.DEFAULT_MODEL_NAME))
        _global_camera_manager = CameraManager(engine)
    return _global_camera_manager
```

### B. File `app/stream/health_checker.py`
Tugas berkala (*cron*) yang mencatat status koneksi kamera dan membersihkan snapshot lama (> 30 hari):

```python
import datetime, logging
from app.config import settings
from app.database import SessionLocal
from app.models import Camera, CameraHealthLog, Detection

logger = logging.getLogger(__name__)

def check_all_cameras_health(camera_manager):
    db = SessionLocal()
    try:
        for cam in db.query(Camera).filter(Camera.is_active == True).all():
            w = camera_manager.get_worker(cam.id)
            if not w: status, msg = "offline", "Worker tidak aktif"
            elif w.reader.is_connected: status, msg = "online", f"Stream aktif (FPS: {w.reader.fps_counter})"
            else: status, msg = "error", w.reader.last_error or "Terputus"
            db.add(CameraHealthLog(camera_id=cam.id, status=status, message=msg))
        db.commit()
    finally: db.close()

def cleanup_old_data_and_snapshots(retention_days=30):
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=retention_days)
    db = SessionLocal()
    try:
        old_dets = db.query(Detection).filter(Detection.detected_at < cutoff, Detection.snapshot_path != None).all()
        for d in old_dets:
            f = settings.BASE_DIR / d.snapshot_path
            if f.exists(): f.unlink()
            d.snapshot_path = None
        db.query(CameraHealthLog).filter(CameraHealthLog.logged_at < cutoff).delete()
        db.commit()
    finally: db.close()
```

---

## 10. Langkah 6: REST API, Streaming MJPEG, & WebSocket (`app/api/`)

### A. Endpoint Live Streaming (`app/api/live.py`)
Mendukung video stream via MJPEG (`multipart/x-mixed-replace`) langsung ke elemen `<img>` HTML, dan WebSocket untuk pengiriman ringkasan data objek real-time:

```python
import time, asyncio, cv2, numpy as np
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, Response
from app.workers.camera_worker import get_global_camera_manager

router = APIRouter(prefix="/api/live", tags=["Live"])

def get_camera_manager():
    from app.main import app
    return getattr(app.state, "camera_manager", None) or get_global_camera_manager()

def generate_mjpeg(worker):
    while True:
        frame = worker.get_latest_annotated_frame()
        if frame is not None:
            ret, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            frame_bytes = buf.tobytes() if ret else b""
        else:
            blank = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(blank, "Menghubungkan...", (180, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255,255,255), 2)
            _, buf = cv2.imencode(".jpg", blank)
            frame_bytes = buf.tobytes()

        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
        time.sleep(0.04)

@router.get("/{camera_id}/stream")
def live_stream(camera_id: int):
    w = get_camera_manager().get_worker(camera_id)
    if not w: raise HTTPException(404, "Kamera tidak ditemukan")
    return StreamingResponse(generate_mjpeg(w), media_type="multipart/x-mixed-replace; boundary=frame")

@router.get("/{camera_id}/snapshot")
def live_snapshot(camera_id: int):
    w = get_camera_manager().get_worker(camera_id)
    if not w: raise HTTPException(404, "Kamera tidak ditemukan")
    frame = worker.get_latest_annotated_frame()
    if frame is None: raise HTTPException(503, "Frame belum siap")
    _, buf = cv2.imencode(".jpg", frame)
    return Response(content=buf.tobytes(), media_type="image/jpeg")

@router.websocket("/ws/{camera_id}")
async def live_ws(websocket: WebSocket, camera_id: int):
    await websocket.accept()
    w = get_camera_manager().get_worker(camera_id)
    if not w:
        await websocket.close()
        return
    try:
        while True:
            await websocket.send_json(w.get_status())
            await asyncio.sleep(0.5)
    except WebSocketDisconnect: pass
```

---

## 11. Langkah 7: Entry Point & Lifespan FastAPI (`app/main.py`)

File utama untuk menginisialisasi database, model YOLO, APScheduler, dan router:

```python
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.database import engine, Base
from app.detection.yolo_engine import YoloEngine
from app.workers.camera_worker import CameraManager
from app.stream.health_checker import check_all_cameras_health, cleanup_old_data_and_snapshots
from app.api import cameras, detections, alerts, live

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("cpm")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Memulai CCTV Public Monitor...")
    Base.metadata.create_all(bind=engine)

    model_path = str(settings.MODELS_DIR / settings.DEFAULT_MODEL_NAME)
    yolo_engine = YoloEngine(model_path=model_path, conf_threshold=settings.CONFIDENCE_THRESHOLD)
    app.state.yolo_engine = yolo_engine

    camera_manager = CameraManager(yolo_engine)
    app.state.camera_manager = camera_manager
    camera_manager.load_active_cameras()

    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: check_all_cameras_health(camera_manager), "interval", seconds=settings.HEALTH_CHECK_INTERVAL_SECONDS)
    scheduler.add_job(lambda: cleanup_old_data_and_snapshots(settings.RETENTION_DAYS), "interval", hours=24)
    scheduler.start()
    app.state.scheduler = scheduler

    yield

    scheduler.shutdown(wait=False)
    camera_manager.stop_all()

app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.mount("/static", StaticFiles(directory=str(settings.STATIC_DIR)), name="static")
app.mount("/snapshots", StaticFiles(directory=str(settings.SNAPSHOTS_DIR)), name="snapshots")
templates = Jinja2Templates(directory=str(settings.TEMPLATES_DIR))

app.include_router(cameras.router)
app.include_router(detections.router)
app.include_router(alerts.router)
app.include_router(live.router)

@app.get("/")
def dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={"title": settings.PROJECT_NAME})

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)

@app.get("/health")
def health():
    return {"status": "ok", "version": settings.VERSION}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=True)
```

---

## 12. Langkah 8: Dashboard Web Frontend

Antarmuka dibangun modern dan responsif:
* **`templates/index.html`**: Menyediakan 4 tab utama:
  1. **Live Feed**: Video player MJPEG + status FPS + indikator jumlah objek real-time per kelas (mobil, motor, orang).
  2. **Histori Deteksi**: Tabel riwayat dengan filter tanggal, kamera, kelas objek, serta tombol **Ekspor CSV**.
  3. **Kamera**: Manajemen sumber stream (tambah/edit/hapus/uji koneksi URL).
  4. **Alerts**: Pengaturan aturan ambang batas dan log alarm yang terpicu.
* **`static/js/app.js`**: Menghubungkan WebSocket ke `/api/live/ws/{id}` untuk pembaruan data real-time tanpa me-refresh halaman browser.

---

## 13. Langkah 9: Pengujian Otomatis (`tests/test_cpm.py`)

Jalankan test suite menggunakan `pytest` untuk memverifikasi seluruh komponen:
```bash
python -m pytest tests/test_cpm.py -v
```

Semua 6 pengujian inti harus berstatus `PASSED`:
1. `test_health_endpoint` (Pemeriksaan API health check)
2. `test_blob_url_validation_rejection` (Penolakan teredukasi untuk URL `blob:`)
3. `test_camera_crud_flow` (Alur CRUD kamera)
4. `test_yolo_inference_and_postprocessing` (Verifikasi inferensi YOLO dan eliminasi false positive batu)
5. `test_alert_rules_and_history` (Aturan alarm dan pembuatan log)
6. `test_detection_csv_export` (Ekspor laporan deteksi ke CSV)

---

## 14. Langkah 10: Menjalankan Proyek

### A. Melalui Terminal / Command Prompt
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

### B. Melalui File Batch di Windows
Cukup klik ganda file **`run.bat`**.

Buka browser Anda di:
* **Dashboard CPM:** `http://localhost:8080`
* **Dokumentasi API Swagger:** `http://localhost:8080/docs`

---

## 15. Troubleshooting & Tips Optimasi

1. **Port Konflik (`[Errno 10048] address already in use`):**
   * Port 8000 sering digunakan software lain di Windows. Karena itu proyek ini dikonfigurasi menggunakan port **8080**.
2. **Koneksi WebSocket Gagal (Error 404):**
   * Pastikan paket `websockets` sudah terinstal: `pip install websockets`.
3. **Menghemat Penggunaan CPU:**
   * Di `app/config.py`, atur `DETECTION_INTERVAL_SECONDS = 1.0` (inferensi dilakukan 1 detik sekali per kamera, bukan 30 fps), sehingga CPU laptop tetap dingin dan ringan saat memantau multi-CCTV.
4. **Koneksi CCTV Publik Sering Terputus:**
   * Modul `StreamReader` telah dilengkapi *exponential backoff auto-reconnect* otomatis mencoba menghubungkan ulang tanpa membuat server crash.
