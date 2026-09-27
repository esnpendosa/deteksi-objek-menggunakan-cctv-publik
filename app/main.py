import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.database import engine, Base
from app.detection.yolo_engine import YoloEngine
from app.workers.camera_worker import CameraManager
from app.stream.health_checker import check_all_cameras_health, cleanup_old_data_and_snapshots
from app.api import cameras, detections, alerts, live

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("cpm")

# Lifespan event handler
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing CCTV Public Monitor (CPM)...")
    
    # 1. Initialize SQLite Database Tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema initialized.")

    # 2. Initialize YOLO Detection Engine
    model_file = str(settings.MODELS_DIR / settings.DEFAULT_MODEL_NAME)
    yolo_engine = YoloEngine(model_path=model_file, conf_threshold=settings.CONFIDENCE_THRESHOLD)
    app.state.yolo_engine = yolo_engine

    # 3. Initialize Camera Manager
    camera_manager = CameraManager(yolo_engine)
    app.state.camera_manager = camera_manager
    camera_manager.load_active_cameras()

    # 4. Start Background Scheduler for Health Checks & Retention Cleanup
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=lambda: check_all_cameras_health(camera_manager),
        trigger="interval",
        seconds=settings.HEALTH_CHECK_INTERVAL_SECONDS,
        id="camera_health_check",
        replace_existing=True
    )
    scheduler.add_job(
        func=lambda: cleanup_old_data_and_snapshots(settings.RETENTION_DAYS),
        trigger="interval",
        hours=24,
        id="retention_cleanup",
        replace_existing=True
    )
    scheduler.start()
    app.state.scheduler = scheduler
    logger.info("Background scheduler started (Health checks & Retention).")

    yield

    # Shutdown
    logger.info("Shutting down CPM...")
    scheduler.shutdown(wait=False)
    camera_manager.stop_all()
    logger.info("Shutdown complete.")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Static Files & Snapshots
app.mount("/static", StaticFiles(directory=str(settings.STATIC_DIR)), name="static")
app.mount("/snapshots", StaticFiles(directory=str(settings.SNAPSHOTS_DIR)), name="snapshots")

# Templates
templates = Jinja2Templates(directory=str(settings.TEMPLATES_DIR))

# Include API Routers
app.include_router(cameras.router)
app.include_router(detections.router)
app.include_router(alerts.router)
app.include_router(live.router)

@app.get("/")
def dashboard_page(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={"title": settings.PROJECT_NAME})

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)

@app.get("/health")
def health():
    return {"status": "ok", "project": settings.PROJECT_NAME, "version": settings.VERSION}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=True)
