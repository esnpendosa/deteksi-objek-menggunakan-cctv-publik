from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Camera
from app.stream.reader import validate_stream_url
from app.workers.camera_worker import get_global_camera_manager

router = APIRouter(prefix="/api/cameras", tags=["Cameras"])

class CameraCreate(BaseModel):
    name: str
    location: Optional[str] = None
    stream_url: str
    is_active: bool = True
    validate_url: bool = False

class CameraUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    stream_url: Optional[str] = None
    is_active: Optional[bool] = None
    validate_url: bool = False

class CameraResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    location: Optional[str] = None
    stream_url: str
    is_active: bool
    status: Optional[str] = "unknown"
    fps: Optional[float] = 0.0

# Helper to access camera manager safely
def get_camera_manager():
    from app.main import app
    return getattr(app.state, "camera_manager", None) or get_global_camera_manager()

@router.get("", response_model=List[CameraResponse])
def list_cameras(db: Session = Depends(get_db)):
    cameras = db.query(Camera).order_by(Camera.id.desc()).all()
    camera_manager = get_camera_manager()
    
    results = []
    for cam in cameras:
        status_info = "offline"
        fps = 0.0
        worker = camera_manager.get_worker(cam.id)
        if worker:
            status_info = "online" if worker.reader.is_connected else ("error" if worker.reader.last_error else "offline")
            fps = worker.reader.fps_counter
        
        results.append(CameraResponse(
            id=cam.id,
            name=cam.name,
            location=cam.location,
            stream_url=cam.stream_url,
            is_active=cam.is_active,
            status=status_info,
            fps=fps
        ))
    return results

@router.post("", response_model=CameraResponse)
def create_camera(payload: CameraCreate, db: Session = Depends(get_db)):
    if payload.validate_url:
        is_valid, msg = validate_stream_url(payload.stream_url)
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"Validasi stream gagal: {msg}")

    new_cam = Camera(
        name=payload.name.strip(),
        location=payload.location.strip() if payload.location else None,
        stream_url=payload.stream_url.strip(),
        is_active=payload.is_active
    )
    db.add(new_cam)
    db.commit()
    db.refresh(new_cam)

    # Start worker if active
    if new_cam.is_active:
        camera_manager = get_camera_manager()
        camera_manager.start_camera(new_cam.id, new_cam.name, new_cam.stream_url)

    return CameraResponse(
        id=new_cam.id,
        name=new_cam.name,
        location=new_cam.location,
        stream_url=new_cam.stream_url,
        is_active=new_cam.is_active,
        status="starting" if new_cam.is_active else "offline"
    )

@router.get("/{camera_id}", response_model=CameraResponse)
def get_camera(camera_id: int, db: Session = Depends(get_db)):
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Kamera tidak ditemukan")
    
    camera_manager = get_camera_manager()
    worker = camera_manager.get_worker(cam.id)
    status_info = "offline"
    fps = 0.0
    if worker:
        status_info = "online" if worker.reader.is_connected else "offline"
        fps = worker.reader.fps_counter

    return CameraResponse(
        id=cam.id,
        name=cam.name,
        location=cam.location,
        stream_url=cam.stream_url,
        is_active=cam.is_active,
        status=status_info,
        fps=fps
    )

@router.put("/{camera_id}", response_model=CameraResponse)
def update_camera(camera_id: int, payload: CameraUpdate, db: Session = Depends(get_db)):
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Kamera tidak ditemukan")

    if payload.stream_url and payload.validate_url:
        is_valid, msg = validate_stream_url(payload.stream_url)
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"Validasi stream gagal: {msg}")

    if payload.name is not None:
        cam.name = payload.name.strip()
    if payload.location is not None:
        cam.location = payload.location.strip()
    if payload.stream_url is not None:
        cam.stream_url = payload.stream_url.strip()
    if payload.is_active is not None:
        cam.is_active = payload.is_active

    db.commit()
    db.refresh(cam)

    # Sync worker
    camera_manager = get_camera_manager()
    if cam.is_active:
        camera_manager.start_camera(cam.id, cam.name, cam.stream_url)
    else:
        camera_manager.stop_camera(cam.id)

    return CameraResponse(
        id=cam.id,
        name=cam.name,
        location=cam.location,
        stream_url=cam.stream_url,
        is_active=cam.is_active,
        status="online" if cam.is_active else "offline"
    )

@router.delete("/{camera_id}")
def delete_camera(camera_id: int, db: Session = Depends(get_db)):
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Kamera tidak ditemukan")

    camera_manager = get_camera_manager()
    camera_manager.stop_camera(cam.id)

    db.delete(cam)
    db.commit()
    return {"message": f"Kamera {camera_id} berhasil dihapus"}

@router.post("/validate-url")
def test_stream_url(stream_url: str = Query(..., description="URL stream untuk diuji")):
    is_valid, message = validate_stream_url(stream_url)
    return {
        "valid": is_valid,
        "message": message
    }
