import os
import time
import logging
import threading
import datetime
from typing import Optional, Dict, Any, List
import cv2
import numpy as np
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import Camera, Detection, DetectionBox, CameraHealthLog, AlertRule, Alert
from app.stream.reader import StreamReader
from app.detection.yolo_engine import YoloEngine
from app.detection.postprocess import aggregate_detections, annotate_frame

logger = logging.getLogger(__name__)

class CameraWorker:
    """
    Dedicated worker thread per CCTV camera.
    Manages StreamReader, executes YOLO inference at configured intervals,
    saves detection records/snapshots/alerts to SQLite, and maintains
    the latest annotated frame for live dashboard consumption.
    """

    def __init__(
        self,
        camera_id: int,
        name: str,
        stream_url: str,
        yolo_engine: YoloEngine,
        detection_interval: float = 1.0,
        target_classes: Optional[List[str]] = None
    ):
        self.camera_id = camera_id
        self.name = name
        self.stream_url = stream_url
        self.yolo_engine = yolo_engine
        self.detection_interval = detection_interval
        self.target_classes = target_classes or settings.TARGET_CLASSES

        self.reader = StreamReader(stream_url)
        self.is_running = False
        self._thread: Optional[threading.Thread] = None

        self._lock = threading.Lock()
        self._latest_annotated_frame: Optional[np.ndarray] = None
        self._latest_raw_frame: Optional[np.ndarray] = None
        self._latest_detections: List[Dict[str, Any]] = []
        self._latest_summary: Dict[str, Any] = {}
        self.last_inference_time: float = 0.0

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.reader.start()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info(f"Started CameraWorker for camera {self.camera_id} ({self.name})")

    def stop(self):
        self.is_running = False
        self.reader.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info(f"Stopped CameraWorker for camera {self.camera_id} ({self.name})")

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

            # Run inference periodically according to detection_interval
            if now - last_run >= self.detection_interval:
                last_run = now
                self.last_inference_time = now
                self._process_frame(frame)

            time.sleep(0.03)  # Small yield to prevent CPU spin

    def _process_frame(self, frame: np.ndarray):
        try:
            # 1. Inference
            raw_dets = self.yolo_engine.detect(frame)
            
            # 2. Aggregation & filtering (with perspective geometry sanity check)
            aggregated, filtered_boxes = aggregate_detections(
                raw_dets,
                target_classes=self.target_classes,
                frame_shape=frame.shape[:2]
            )

            # 3. Annotation for live feed
            annotated = annotate_frame(
                frame,
                filtered_boxes,
                fps=self.reader.fps_counter,
                camera_name=self.name
            )

            with self._lock:
                self._latest_annotated_frame = annotated
                self._latest_detections = filtered_boxes
                self._latest_summary = {
                    cls_name: data["count"] for cls_name, data in aggregated.items()
                }

            # 4. Save to Database & Check Alerts
            if aggregated:
                self._save_results_and_alerts(frame, aggregated, filtered_boxes)

        except Exception as e:
            logger.error(f"Error processing frame in worker {self.camera_id}: {e}")

    def _save_results_and_alerts(
        self,
        raw_frame: np.ndarray,
        aggregated: Dict[str, Dict[str, Any]],
        filtered_boxes: List[Dict[str, Any]]
    ):
        db: Session = SessionLocal()
        try:
            snapshot_path: Optional[str] = None
            total_objects = sum(d["count"] for d in aggregated.values())

            # Check if alert rules are triggered
            rules = db.query(AlertRule).filter(
                (AlertRule.camera_id == self.camera_id) | (AlertRule.camera_id == None),
                AlertRule.is_active == True
            ).all()

            triggered_alerts = []
            for rule in rules:
                rule_class = rule.object_class.lower()
                count = aggregated.get(rule_class, {}).get("count", 0)
                if count >= rule.threshold_count:
                    msg = f"Alert! Deteksi {count} {rule_class} (ambang: {rule.threshold_count}) pada kamera '{self.name}'"
                    alert = Alert(
                        rule_id=rule.id,
                        camera_id=self.camera_id,
                        details=msg
                    )
                    db.add(alert)
                    triggered_alerts.append(msg)

            # Save snapshot if alert triggered or notable object count (e.g. > 5)
            if triggered_alerts or total_objects >= 5:
                timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                filename = f"cam_{self.camera_id}_{timestamp_str}.jpg"
                filepath = settings.SNAPSHOTS_DIR / filename
                cv2.imwrite(str(filepath), raw_frame)
                snapshot_path = f"snapshots/{filename}"

            # Save aggregate detections
            for cls_name, data in aggregated.items():
                det_record = Detection(
                    camera_id=self.camera_id,
                    object_class=cls_name,
                    object_count=data["count"],
                    avg_confidence=data["avg_confidence"],
                    snapshot_path=snapshot_path
                )
                db.add(det_record)
                db.flush()

                # Save individual boxes associated with this detection class
                for box_item in filtered_boxes:
                    if box_item["class_name"].lower() == cls_name:
                        b = box_item["box"]
                        box_record = DetectionBox(
                            detection_id=det_record.id,
                            class_name=cls_name,
                            confidence=box_item["confidence"],
                            x1=b[0], y1=b[1], x2=b[2], y2=b[3]
                        )
                        db.add(box_record)

            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"DB save error for camera {self.camera_id}: {e}")
        finally:
            db.close()

    def get_latest_annotated_frame(self) -> Optional[np.ndarray]:
        with self._lock:
            if self._latest_annotated_frame is not None:
                return self._latest_annotated_frame.copy()
            if self._latest_raw_frame is not None:
                return self._latest_raw_frame.copy()
            return None

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "camera_id": self.camera_id,
                "name": self.name,
                "is_running": self.is_running,
                "is_connected": self.reader.is_connected,
                "fps": self.reader.fps_counter,
                "last_error": self.reader.last_error,
                "latest_summary": self._latest_summary.copy(),
                "total_detections": len(self._latest_detections)
            }


class CameraManager:
    """
    Singleton-style manager overseeing all active CameraWorkers.
    """
    def __init__(self, yolo_engine: YoloEngine):
        self.yolo_engine = yolo_engine
        self.workers: Dict[int, CameraWorker] = {}
        self._lock = threading.Lock()

    def load_active_cameras(self):
        """Loads and starts active cameras from the database."""
        db: Session = SessionLocal()
        try:
            cameras = db.query(Camera).filter(Camera.is_active == True).all()
            for cam in cameras:
                self.start_camera(cam.id, cam.name, cam.stream_url)
        finally:
            db.close()

    def start_camera(self, camera_id: int, name: str, stream_url: str):
        with self._lock:
            if camera_id in self.workers:
                self.workers[camera_id].stop()
            worker = CameraWorker(
                camera_id=camera_id,
                name=name,
                stream_url=stream_url,
                yolo_engine=self.yolo_engine,
                detection_interval=settings.DETECTION_INTERVAL_SECONDS
            )
            worker.start()
            self.workers[camera_id] = worker
            logger.info(f"Registered camera worker {camera_id}")

    def stop_camera(self, camera_id: int):
        with self._lock:
            if camera_id in self.workers:
                self.workers[camera_id].stop()
                del self.workers[camera_id]
                logger.info(f"Unregistered camera worker {camera_id}")

    def stop_all(self):
        with self._lock:
            for worker in self.workers.values():
                worker.stop()
            self.workers.clear()

    def get_worker(self, camera_id: int) -> Optional[CameraWorker]:
        with self._lock:
            return self.workers.get(camera_id)

_global_camera_manager: Optional[CameraManager] = None

def get_global_camera_manager() -> CameraManager:
    global _global_camera_manager
    if _global_camera_manager is None:
        yolo_engine = YoloEngine(str(settings.MODELS_DIR / settings.DEFAULT_MODEL_NAME))
        _global_camera_manager = CameraManager(yolo_engine)
    return _global_camera_manager

def set_global_camera_manager(manager: CameraManager):
    global _global_camera_manager
    _global_camera_manager = manager
