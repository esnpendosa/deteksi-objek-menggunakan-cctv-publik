import os
import logging
from typing import List, Dict, Any, Optional
import numpy as np

logger = logging.getLogger(__name__)

class YoloEngine:
    """
    Wrapper for Ultralytics YOLO inference.
    Handles model loading, inference, and formatting of detection results.
    """
    def __init__(self, model_path: str = "models/yolov8n.pt", conf_threshold: float = 0.35):
        self.model_path = model_path
        self.conf_threshold = conf_threshold
        self.model = None
        self._load_model()

    def _load_model(self):
        try:
            from ultralytics import YOLO
            logger.info(f"Loading YOLO model from: {self.model_path}")
            self.model = YOLO(self.model_path)
            logger.info("YOLO model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
            self.model = None

    def detect(self, frame: np.ndarray, conf: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Runs object detection on a frame (BGR numpy array).
        Returns a list of dicts:
        [
            {
                "class_name": str,
                "confidence": float,
                "box": [x1, y1, x2, y2]
            },
            ...
        ]
        """
        if self.model is None:
            # Try reloading once
            self._load_model()
            if self.model is None:
                return []

        threshold = conf if conf is not None else self.conf_threshold
        detections: List[Dict[str, Any]] = []

        try:
            results = self.model.predict(
                source=frame,
                conf=threshold,
                verbose=False,
                device="cpu"
            )
            
            if not results or len(results) == 0:
                return []

            result = results[0]
            boxes = result.boxes
            if boxes is None or len(boxes) == 0:
                return []

            names = result.names  # class index to name map

            for box in boxes:
                cls_id = int(box.cls[0].item())
                confidence = float(box.conf[0].item())
                xyxy = box.xyxy[0].tolist()  # [x1, y1, x2, y2]
                class_name = names.get(cls_id, str(cls_id))

                detections.append({
                    "class_name": class_name,
                    "confidence": round(confidence, 3),
                    "box": [round(coord, 1) for coord in xyxy]
                })

        except Exception as e:
            logger.error(f"Error during YOLO inference: {e}")

        return detections
