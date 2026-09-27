import os
import time
import logging
import datetime
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import Camera, CameraHealthLog, Detection
from app.workers.camera_worker import CameraManager

logger = logging.getLogger(__name__)

def check_all_cameras_health(camera_manager: CameraManager):
    """
    Periodic job that assesses each active camera's connectivity and logs its health.
    """
    db: Session = SessionLocal()
    try:
        cameras = db.query(Camera).filter(Camera.is_active == True).all()
        for cam in cameras:
            worker = camera_manager.get_worker(cam.id)
            if worker is None:
                status = "offline"
                message = "Worker belum diinisialisasi atau kamera tidak aktif"
            elif worker.reader.is_connected:
                status = "online"
                message = f"Stream aktif (FPS: {worker.reader.fps_counter})"
            else:
                status = "error" if worker.reader.last_error else "offline"
                message = worker.reader.last_error or "Koneksi stream terputus"

            # Log to DB
            log_entry = CameraHealthLog(
                camera_id=cam.id,
                status=status,
                message=message
            )
            db.add(log_entry)

        db.commit()
        logger.info(f"Completed health check for {len(cameras)} active cameras.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error during camera health check: {e}")
    finally:
        db.close()


def cleanup_old_data_and_snapshots(retention_days: int = 30):
    """
    Cleans up detection snapshots and database logs older than the retention period.
    """
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=retention_days)
    db: Session = SessionLocal()
    try:
        # 1. Clean up old snapshots on disk
        old_detections_with_snapshots = db.query(Detection).filter(
            Detection.detected_at < cutoff,
            Detection.snapshot_path != None
        ).all()

        deleted_files_count = 0
        for det in old_detections_with_snapshots:
            if det.snapshot_path:
                full_path = settings.BASE_DIR / det.snapshot_path
                if full_path.exists():
                    try:
                        full_path.unlink()
                        deleted_files_count += 1
                    except Exception as err:
                        logger.warning(f"Failed to delete old snapshot file {full_path}: {err}")
                det.snapshot_path = None  # Remove reference

        # 2. Clean up old health logs
        deleted_health_logs = db.query(CameraHealthLog).filter(
            CameraHealthLog.logged_at < cutoff
        ).delete()

        db.commit()
        logger.info(f"Retention cleanup: removed {deleted_files_count} snapshot files, {deleted_health_logs} health logs older than {retention_days} days.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error during retention cleanup: {e}")
    finally:
        db.close()
