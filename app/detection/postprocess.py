from typing import List, Dict, Any, Tuple
import cv2
import numpy as np

# Distinct colors for popular classes (BGR format for OpenCV)
CLASS_COLORS = {
    "person": (255, 128, 0),      # Blue-Orange
    "car": (0, 200, 255),         # Yellow
    "motorcycle": (0, 255, 128),  # Light green
    "bus": (255, 0, 128),         # Purple
    "truck": (0, 128, 255),       # Orange
    "bicycle": (128, 255, 0),     # Bright green
    "train": (255, 0, 255),       # Magenta
}
DEFAULT_COLOR = (0, 255, 0)

def validate_detection_geometry(item: Dict[str, Any], frame_w: int = 640, frame_h: int = 480) -> bool:
    """
    Validates physical plausibility of detected bounding boxes to eliminate
    false positives (e.g., small stones, buckets, curbs misclassified as cars).
    """
    cls_name = item["class_name"].lower()
    conf = float(item["confidence"])
    box = item["box"]
    x1, y1, x2, y2 = box
    w = x2 - x1
    h = y2 - y1
    area = w * h
    y_center = (y1 + y2) / 2

    if cls_name in ["car", "truck", "bus"]:
        # Increased confidence threshold for large vehicles to suppress noisy texture false positives
        if conf < 0.45:
            return False

        # Physical perspective sanity check:
        # In CCTV perspective, objects near the bottom of the screen (foreground) MUST be larger.
        if y_center > frame_h * 0.40:
            # Foreground: a real car cannot be a tiny blob like a stone
            if w < 48 or h < 38 or area < 2000:
                return False
        elif y_center > frame_h * 0.25:
            # Mid distance
            if w < 28 or h < 24 or area < 700:
                return False
        else:
            # Far distance (horizon)
            if w < 16 or h < 14 or area < 250:
                return False

        # Aspect ratio check
        aspect_ratio = w / max(h, 1)
        if aspect_ratio < 0.45 or aspect_ratio > 3.8:
            return False

    elif cls_name == "person":
        if conf < 0.35:
            return False
        if y_center > frame_h * 0.40 and h < 28:
            return False

    elif cls_name in ["motorcycle", "bicycle"]:
        if conf < 0.38:
            return False
        if y_center > frame_h * 0.40 and (h < 28 or area < 600):
            return False

    return True

def aggregate_detections(
    raw_detections: List[Dict[str, Any]],
    target_classes: List[str] = None,
    frame_shape: Tuple[int, int] = (480, 640)
) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Filters raw detections with geometry sanity checks and aggregates count per class.
    """
    aggregated: Dict[str, Dict[str, Any]] = {}
    filtered_boxes: List[Dict[str, Any]] = []
    frame_h, frame_w = frame_shape[:2]

    for item in raw_detections:
        cls_name = item["class_name"].lower()
        conf = float(item["confidence"])
        
        if target_classes and cls_name not in target_classes:
            continue

        # Spatial geometry & perspective filter (eliminates stones, curbs, shadows)
        if not validate_detection_geometry(item, frame_w=frame_w, frame_h=frame_h):
            continue

        filtered_boxes.append(item)

        if cls_name not in aggregated:
            aggregated[cls_name] = {
                "class_name": cls_name,
                "count": 0,
                "conf_sum": 0.0,
                "avg_confidence": 0.0
            }

        aggregated[cls_name]["count"] += 1
        aggregated[cls_name]["conf_sum"] += conf

    for cls_name, data in aggregated.items():
        if data["count"] > 0:
            data["avg_confidence"] = round(data["conf_sum"] / data["count"], 3)
        del data["conf_sum"]

    return aggregated, filtered_boxes


def annotate_frame(
    frame: np.ndarray,
    detections: List[Dict[str, Any]],
    fps: float = 0.0,
    camera_name: str = ""
) -> np.ndarray:
    """
    Draws bounding boxes, labels, and metadata overlay onto a copy of the frame.
    """
    annotated = frame.copy()
    h, w = annotated.shape[:2]

    # Draw boxes
    for det in detections:
        cls_name = det["class_name"]
        conf = det["confidence"]
        x1, y1, x2, y2 = [int(v) for v in det["box"]]
        
        # Clamp to frame boundaries
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        color = CLASS_COLORS.get(cls_name.lower(), DEFAULT_COLOR)

        # Draw bounding rectangle
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

        # Draw label background
        label = f"{cls_name} {conf:.2f}"
        (label_w, label_h), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        top = max(y1, label_h + 5)
        
        cv2.rectangle(
            annotated,
            (x1, top - label_h - 4),
            (x1 + label_w + 6, top + baseline - 2),
            color,
            -1
        )
        cv2.putText(
            annotated,
            label,
            (x1 + 3, top - 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 0, 0),
            1,
            cv2.LINE_AA
        )

    # Draw top header badge (Camera name & FPS)
    header_text = f"{camera_name} | {fps:.1f} FPS | Objects: {len(detections)}" if camera_name else f"{fps:.1f} FPS | Objects: {len(detections)}"
    cv2.rectangle(annotated, (10, 10), (10 + len(header_text) * 9 + 20, 36), (0, 0, 0), -1)
    cv2.putText(
        annotated,
        header_text,
        (18, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (0, 255, 200),
        1,
        cv2.LINE_AA
    )

    return annotated
