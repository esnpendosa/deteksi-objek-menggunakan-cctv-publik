import pytest
import numpy as np
import cv2
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.database import SessionLocal, engine, Base
from app.models import Camera, Detection, AlertRule, Alert
from app.detection.yolo_engine import YoloEngine
from app.detection.postprocess import aggregate_detections, annotate_frame
from app.stream.reader import validate_stream_url

client = TestClient(app)

def setup_module():
    Base.metadata.create_all(bind=engine)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_blob_url_validation_rejection():
    # Per PRD section 1.1: blob: URLs must be explicitly rejected with a clear message
    blob_url = "blob:https://cctvkanjeng.gresikkab.go.id/507c3e19-6084-467d-85c8-d4ebd7c6e0ce"
    is_valid, msg = validate_stream_url(blob_url)
    assert is_valid is False
    assert "blob:" in msg

def test_camera_crud_flow():
    # 1. Create camera
    new_cam_data = {
        "name": "Simpang Lima Test",
        "location": "Gresik Kota",
        "stream_url": "https://example.com/live/simpang.m3u8",
        "is_active": False,
        "validate_url": False
    }
    create_res = client.post("/api/cameras", json=new_cam_data)
    assert create_res.status_code == 200
    cam_id = create_res.json()["id"]

    # 2. Get camera list
    list_res = client.get("/api/cameras")
    assert list_res.status_code == 200
    cameras = list_res.json()
    assert any(c["id"] == cam_id for c in cameras)

    # 3. Update camera
    update_res = client.put(f"/api/cameras/{cam_id}", json={"name": "Simpang Lima Updated"})
    assert update_res.status_code == 200
    assert update_res.json()["name"] == "Simpang Lima Updated"

    # 4. Delete camera
    del_res = client.delete(f"/api/cameras/{cam_id}")
    assert del_res.status_code == 200

def test_yolo_inference_and_postprocessing():
    engine = YoloEngine(str(settings.MODELS_DIR / "yolov8n.pt"))
    # Create test frame
    test_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    # Draw simple shapes or blank
    raw_dets = engine.detect(test_frame)
    assert isinstance(raw_dets, list)

    # Test aggregation logic (including stone false positive elimination)
    sample_dets = [
        {"class_name": "car", "confidence": 0.85, "box": [10, 10, 100, 100]},
        {"class_name": "car", "confidence": 0.75, "box": [120, 50, 200, 150]},
        {"class_name": "car", "confidence": 0.67, "box": [172, 264, 205, 296]},  # Stone on sidewalk misclassified as car
        {"class_name": "motorcycle", "confidence": 0.90, "box": [220, 80, 280, 160]},
        {"class_name": "dog", "confidence": 0.95, "box": [300, 100, 350, 150]}  # non-traffic
    ]
    aggregated, filtered = aggregate_detections(sample_dets, target_classes=["car", "motorcycle"])
    assert "car" in aggregated
    assert aggregated["car"]["count"] == 2  # Stone rejected, only 2 real cars kept
    assert aggregated["car"]["avg_confidence"] == 0.8
    assert "motorcycle" in aggregated
    assert "dog" not in aggregated
    assert len(filtered) == 3

    # Test annotation
    annotated = annotate_frame(test_frame, filtered, fps=25.0, camera_name="Test Cam")
    assert annotated.shape == test_frame.shape

def test_alert_rules_and_history():
    # Create alert rule
    rule_data = {
        "camera_id": None,
        "object_class": "car",
        "threshold_count": 5
    }
    res = client.post("/api/alerts/rules", json=rule_data)
    assert res.status_code == 200
    rule_id = res.json()["id"]

    # List rules
    rules_res = client.get("/api/alerts/rules")
    assert rules_res.status_code == 200
    assert any(r["id"] == rule_id for r in rules_res.json())

    # Delete rule
    del_res = client.delete(f"/api/alerts/rules/{rule_id}")
    assert del_res.status_code == 200

def test_detection_csv_export():
    res = client.get("/api/detections/export/csv")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert "Camera Name" in res.text
