import os
from pathlib import Path
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseModel):
    PROJECT_NAME: str = "CCTV Public Monitor (CPM)"
    VERSION: str = "1.0.0"
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'cctv_monitor.db'}")
    
    # Paths
    BASE_DIR: Path = BASE_DIR
    MODELS_DIR: Path = BASE_DIR / "models"
    SNAPSHOTS_DIR: Path = BASE_DIR / "snapshots"
    STATIC_DIR: Path = BASE_DIR / "static"
    TEMPLATES_DIR: Path = BASE_DIR / "templates"
    
    # YOLO Model settings (YOLOv8s provides superior accuracy and false-positive suppression)
    DEFAULT_MODEL_NAME: str = "yolov8s.pt"
    CONFIDENCE_THRESHOLD: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.40"))
    VEHICLE_CONFIDENCE_THRESHOLD: float = float(os.getenv("VEHICLE_CONFIDENCE_THRESHOLD", "0.48"))
    
    # Ingestion / Inference interval per camera in seconds (e.g. 1.0 to save CPU)
    DETECTION_INTERVAL_SECONDS: float = float(os.getenv("DETECTION_INTERVAL_SECONDS", "1.0"))
    
    # Filter classes (traffic & public safety focus)
    TARGET_CLASSES: list[str] = [
        "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat"
    ]
    
    # Camera Stream settings
    STREAM_CONNECT_TIMEOUT: int = int(os.getenv("STREAM_CONNECT_TIMEOUT", "10"))
    HEALTH_CHECK_INTERVAL_SECONDS: int = int(os.getenv("HEALTH_CHECK_INTERVAL_SECONDS", "60"))
    
    # Retention cleanup (in days)
    RETENTION_DAYS: int = int(os.getenv("RETENTION_DAYS", "30"))

settings = Settings()

# Ensure directories exist
settings.MODELS_DIR.mkdir(parents=True, exist_ok=True)
settings.SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
