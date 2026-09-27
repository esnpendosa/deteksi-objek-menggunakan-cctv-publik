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

    # Relationships
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
    x1 = Column(Float, nullable=True)
    y1 = Column(Float, nullable=True)
    x2 = Column(Float, nullable=True)
    y2 = Column(Float, nullable=True)

    detection = relationship("Detection", back_populates="boxes")


class CameraHealthLog(Base):
    __tablename__ = "camera_health_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=False, index=True)
    status = Column(String, nullable=False)  # 'online', 'offline', 'error'
    message = Column(Text, nullable=True)
    logged_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)

    camera = relationship("Camera", back_populates="health_logs")


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=True, index=True)  # null means applies to all
    object_class = Column(String, nullable=False)  # e.g., 'car', 'person'
    threshold_count = Column(Integer, nullable=False)  # trigger alert if count >= threshold
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
