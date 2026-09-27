import time
import asyncio
import cv2
import numpy as np
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, Response

from app.workers.camera_worker import get_global_camera_manager

router = APIRouter(prefix="/api/live", tags=["Live"])

def get_camera_manager():
    from app.main import app
    return getattr(app.state, "camera_manager", None) or get_global_camera_manager()

def generate_mjpeg_stream(worker):
    """
    Generator that encodes annotated frames to JPEG and streams them over multipart/x-mixed-replace.
    """
    blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(
        blank_frame,
        "Menghubungkan Stream...",
        (150, 240),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2
    )
    _, encoded_blank = cv2.imencode(".jpg", blank_frame)
    blank_bytes = encoded_blank.tobytes()

    while True:
        frame = worker.get_latest_annotated_frame()
        if frame is not None:
            ret, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ret:
                frame_bytes = buffer.tobytes()
            else:
                frame_bytes = blank_bytes
        else:
            frame_bytes = blank_bytes

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
        )
        time.sleep(0.04)  # ~25 FPS max stream output

@router.get("/{camera_id}/stream")
def live_stream_mjpeg(camera_id: int):
    camera_manager = get_camera_manager()
    worker = camera_manager.get_worker(camera_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Kamera atau worker tidak ditemukan")

    return StreamingResponse(
        generate_mjpeg_stream(worker),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@router.get("/{camera_id}/snapshot")
def live_snapshot(camera_id: int):
    camera_manager = get_camera_manager()
    worker = camera_manager.get_worker(camera_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Kamera atau worker tidak ditemukan")

    frame = worker.get_latest_annotated_frame()
    if frame is None:
        raise HTTPException(status_code=503, detail="Frame kamera belum tersedia")

    ret, buffer = cv2.imencode(".jpg", frame)
    if not ret:
        raise HTTPException(status_code=500, detail="Gagal encode frame")

    return Response(content=buffer.tobytes(), media_type="image/jpeg")

@router.websocket("/ws/{camera_id}")
async def live_websocket(websocket: WebSocket, camera_id: int):
    await websocket.accept()
    camera_manager = get_camera_manager()
    worker = camera_manager.get_worker(camera_id)
    
    if not worker:
        await websocket.send_json({"error": "Worker kamera tidak aktif"})
        await websocket.close()
        return

    try:
        while True:
            status = worker.get_status()
            await websocket.send_json(status)
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        pass
