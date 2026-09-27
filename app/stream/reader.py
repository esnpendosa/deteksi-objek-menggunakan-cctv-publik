import cv2
import time
import logging
import threading
from typing import Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)

class StreamReader:
    """
    StreamReader handles fetching video frames from RTSP, HLS (.m3u8), MJPEG,
    or HTTP video streams using OpenCV VideoCapture.
    It runs a dedicated background thread to continuously buffer the latest frame,
    preventing OpenCV buffer lag and handling auto-reconnection.
    """

    def __init__(self, stream_url: str, reconnect_delay: float = 3.0, max_reconnect_attempts: int = 10):
        self.stream_url = stream_url
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_attempts = max_reconnect_attempts
        
        self.cap: Optional[cv2.VideoCapture] = None
        self._latest_frame: Optional[np.ndarray] = None
        self._lock = threading.Lock()
        
        self.is_running = False
        self.is_connected = False
        self.last_frame_time: float = 0.0
        self.last_error: Optional[str] = None
        self.fps_counter: float = 0.0
        self._frame_count: int = 0
        self._fps_start_time: float = time.time()
        
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.is_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._release_cap()
        self.is_connected = False

    def _release_cap(self):
        if self.cap:
            try:
                self.cap.release()
            except Exception as e:
                logger.warning(f"Error releasing VideoCapture: {e}")
            self.cap = None

    def _connect(self) -> bool:
        self._release_cap()
        try:
            logger.info(f"Connecting to stream: {self.stream_url}")
            # Try to open stream
            cap = cv2.VideoCapture(self.stream_url)
            # Set buffer size to 1 to reduce latency on RTSP
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    self.cap = cap
                    self.is_connected = True
                    self.last_error = None
                    with self._lock:
                        self._latest_frame = frame
                        self.last_frame_time = time.time()
                    logger.info(f"Successfully connected to stream: {self.stream_url}")
                    return True
                else:
                    cap.release()
                    self.last_error = "Connected but failed to read initial frame"
            else:
                self.last_error = "VideoCapture failed to open stream URL"
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"Stream connect error: {e}")
            
        self.is_connected = False
        return False

    def _capture_loop(self):
        reconnect_attempts = 0
        while self.is_running:
            if not self.is_connected or self.cap is None or not self.cap.isOpened():
                connected = self._connect()
                if not connected:
                    reconnect_attempts += 1
                    time.sleep(min(self.reconnect_delay * (1.2 ** min(reconnect_attempts, 5)), 30.0))
                    continue
                else:
                    reconnect_attempts = 0

            # Read frame
            try:
                ret, frame = self.cap.read()
                if not ret or frame is None:
                    logger.warning(f"Failed to read frame from {self.stream_url}, reconnecting...")
                    self.is_connected = False
                    self.last_error = "Frame read returned false"
                    time.sleep(1.0)
                    continue

                now = time.time()
                with self._lock:
                    self._latest_frame = frame
                    self.last_frame_time = now
                    self._frame_count += 1
                    if now - self._fps_start_time >= 3.0:
                        self.fps_counter = round(self._frame_count / (now - self._fps_start_time), 1)
                        self._frame_count = 0
                        self._fps_start_time = now
            except Exception as e:
                logger.error(f"Error reading frame: {e}")
                self.is_connected = False
                self.last_error = str(e)
                time.sleep(1.0)

    def get_latest_frame(self) -> Optional[np.ndarray]:
        """Returns the most recent frame thread-safely."""
        with self._lock:
            if self._latest_frame is not None:
                return self._latest_frame.copy()
            return None


def validate_stream_url(url: str, timeout_seconds: int = 5) -> Tuple[bool, str]:
    """
    Quickly tests if a video stream URL can be opened and produces a frame.
    Returns (is_valid, message).
    """
    if not url or not isinstance(url, str):
        return False, "Stream URL tidak boleh kosong."
        
    url = url.strip()
    if url.startswith("blob:"):
        return False, "URL 'blob:' adalah objek browser lokal dan tidak dapat diakses langsung oleh server. Silakan cari URL HLS (.m3u8), RTSP, atau MJPEG asli di Network tab DevTools browser."
        
    try:
        cap = cv2.VideoCapture(url)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        start = time.time()
        
        while time.time() - start < timeout_seconds:
            if cap.isOpened():
                ret, frame = cap.read()
                cap.release()
                if ret and frame is not None:
                    h, w = frame.shape[:2]
                    return True, f"Stream valid. Resolusi: {w}x{h}"
                else:
                    return False, "Stream terbuka tetapi tidak ada frame yang terbaca."
            time.sleep(0.5)
            
        cap.release()
        return False, f"Timeout ({timeout_seconds}s) saat mencoba menghubungi stream URL."
    except Exception as e:
        return False, f"Gagal memvalidasi stream: {str(e)}"
