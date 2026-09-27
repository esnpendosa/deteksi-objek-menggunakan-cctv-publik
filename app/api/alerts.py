from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
import datetime

from app.database import get_db
from app.models import AlertRule, Alert, Camera

router = APIRouter(prefix="/api/alerts", tags=["Alerts"])

class AlertRuleCreate(BaseModel):
    camera_id: Optional[int] = None
    object_class: str
    threshold_count: int
    time_window_seconds: int = 60
    is_active: bool = True

class AlertRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    camera_id: Optional[int] = None
    camera_name: Optional[str] = "Semua Kamera"
    object_class: str
    threshold_count: int
    time_window_seconds: int
    is_active: bool

class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_id: Optional[int] = None
    camera_id: int
    camera_name: Optional[str] = None
    triggered_at: datetime.datetime
    details: Optional[str] = None

@router.get("/rules", response_model=List[AlertRuleResponse])
def get_alert_rules(db: Session = Depends(get_db)):
    rules = db.query(AlertRule).all()
    results = []
    for r in rules:
        cam_name = r.camera.name if r.camera else "Semua Kamera"
        results.append(AlertRuleResponse(
            id=r.id,
            camera_id=r.camera_id,
            camera_name=cam_name,
            object_class=r.object_class,
            threshold_count=r.threshold_count,
            time_window_seconds=r.time_window_seconds,
            is_active=r.is_active
        ))
    return results

@router.post("/rules", response_model=AlertRuleResponse)
def create_alert_rule(payload: AlertRuleCreate, db: Session = Depends(get_db)):
    if payload.camera_id:
        cam = db.query(Camera).filter(Camera.id == payload.camera_id).first()
        if not cam:
            raise HTTPException(status_code=404, detail="Kamera target tidak ditemukan")

    rule = AlertRule(
        camera_id=payload.camera_id,
        object_class=payload.object_class.lower().strip(),
        threshold_count=payload.threshold_count,
        time_window_seconds=payload.time_window_seconds,
        is_active=payload.is_active
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)

    cam_name = rule.camera.name if rule.camera else "Semua Kamera"
    return AlertRuleResponse(
        id=rule.id,
        camera_id=rule.camera_id,
        camera_name=cam_name,
        object_class=rule.object_class,
        threshold_count=rule.threshold_count,
        time_window_seconds=rule.time_window_seconds,
        is_active=rule.is_active
    )

@router.delete("/rules/{rule_id}")
def delete_alert_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(AlertRule).filter(AlertRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Aturan alert tidak ditemukan")
    db.delete(rule)
    db.commit()
    return {"message": f"Aturan alert {rule_id} berhasil dihapus"}

@router.get("", response_model=List[AlertResponse])
def get_alerts(
    camera_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    query = db.query(Alert).join(Camera, Alert.camera_id == Camera.id)
    if camera_id:
        query = query.filter(Alert.camera_id == camera_id)

    alerts = query.order_by(Alert.triggered_at.desc()).limit(limit).all()
    results = []
    for a in alerts:
        results.append(AlertResponse(
            id=a.id,
            rule_id=a.rule_id,
            camera_id=a.camera_id,
            camera_name=a.camera.name if a.camera else "",
            triggered_at=a.triggered_at,
            details=a.details
        ))
    return results
