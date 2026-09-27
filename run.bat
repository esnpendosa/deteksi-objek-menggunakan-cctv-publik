@echo off
title CCTV Public Monitor (CPM)
echo ========================================================
echo         CCTV Public Monitor (CPM) - YOLO + SQLite
echo ========================================================
echo.
echo Memulai server Uvicorn di http://localhost:8080 ...
echo Tekan Ctrl+C untuk menghentikan server.
echo.
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
pause
