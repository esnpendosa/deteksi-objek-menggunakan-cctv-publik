import csv
import io
import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models import Detection, Camera, DetectionBox

router = APIRouter(prefix="/api/detections", tags=["Detections"])

class DetectionItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    camera_id: int
    camera_name: Optional[str] = None
    detected_at: datetime.datetime
    object_class: str
    object_count: int
    avg_confidence: Optional[float] = None
    snapshot_path: Optional[str] = None

class DetectionListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[DetectionItemResponse]

@router.get("", response_model=DetectionListResponse)
def get_detections(
    camera_id: Optional[int] = Query(None, description="Filter per ID kamera"),
    object_class: Optional[str] = Query(None, description="Filter kelas objek (misal 'car', 'person')"),
    start_date: Optional[datetime.datetime] = Query(None, description="Awal rentang waktu"),
    end_date: Optional[datetime.datetime] = Query(None, description="Akhir rentang waktu"),
    min_confidence: Optional[float] = Query(None, description="Ambang batas rata-rata confidence"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db)
):
    query = db.query(Detection).join(Camera, Detection.camera_id == Camera.id)

    if camera_id:
        query = query.filter(Detection.camera_id == camera_id)
    if object_class:
        query = query.filter(Detection.object_class == object_class.lower().strip())
    if start_date:
        query = query.filter(Detection.detected_at >= start_date)
    if end_date:
        query = query.filter(Detection.detected_at <= end_date)
    if min_confidence:
        query = query.filter(Detection.avg_confidence >= min_confidence)

    total = query.count()
    offset = (page - 1) * page_size
    records = query.order_by(Detection.detected_at.desc()).offset(offset).limit(page_size).all()

    items = []
    for r in records:
        items.append(DetectionItemResponse(
            id=r.id,
            camera_id=r.camera_id,
            camera_name=r.camera.name if r.camera else "Unknown",
            detected_at=r.detected_at,
            object_class=r.object_class,
            object_count=r.object_count,
            avg_confidence=r.avg_confidence,
            snapshot_path=r.snapshot_path
        ))

    return DetectionListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=items
    )

@router.get("/stats")
def get_detection_stats(
    camera_id: Optional[int] = Query(None),
    hours: int = Query(24, ge=1, le=720),
    db: Session = Depends(get_db)
):
    since = datetime.datetime.utcnow() - datetime.timedelta(hours=hours)
    query = db.query(Detection).filter(Detection.detected_at >= since)
    if camera_id:
        query = query.filter(Detection.camera_id == camera_id)

    # Aggregates by object class
    class_stats = db.query(
        Detection.object_class,
        func.sum(Detection.object_count).label("total_count"),
        func.avg(Detection.avg_confidence).label("avg_conf")
    ).filter(Detection.detected_at >= since)
    
    if camera_id:
        class_stats = class_stats.filter(Detection.camera_id == camera_id)
        
    class_results = class_stats.group_by(Detection.object_class).all()

    # Total counts
    total_detections = sum(r[1] or 0 for r in class_results)

    return {
        "time_window_hours": hours,
        "total_objects_detected": total_detections,
        "by_class": [
            {
                "class_name": r[0],
                "total_count": r[1],
                "avg_confidence": round(r[2] or 0.0, 3)
            }
            for r in class_results
        ]
    }

@router.get("/export/csv")
def export_detections_csv(
    camera_id: Optional[int] = Query(None),
    object_class: Optional[str] = Query(None),
    start_date: Optional[datetime.datetime] = Query(None),
    end_date: Optional[datetime.datetime] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Exports filtered detection history to CSV (FR-11).
    """
    query = db.query(Detection).join(Camera, Detection.camera_id == Camera.id)
    if camera_id:
        query = query.filter(Detection.camera_id == camera_id)
    if object_class:
        query = query.filter(Detection.object_class == object_class.lower().strip())
    if start_date:
        query = query.filter(Detection.detected_at >= start_date)
    if end_date:
        query = query.filter(Detection.detected_at <= end_date)

    records = query.order_by(Detection.detected_at.desc()).limit(5000).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Camera ID", "Camera Name", "Timestamp", "Object Class", "Count", "Avg Confidence", "Snapshot Path"])

    for r in records:
        writer.writerow([
            r.id,
            r.camera_id,
            r.camera.name if r.camera else "",
            r.detected_at.isoformat(),
            r.object_class,
            r.object_count,
            f"{r.avg_confidence:.3f}" if r.avg_confidence else "",
            r.snapshot_path or ""
        ])

    csv_data = output.getvalue()
    filename = f"cctv_detections_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
