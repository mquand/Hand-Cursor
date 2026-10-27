@echo off
title HandCursor for Windows
echo ===================================================
echo  HandCursor — Dieu khien chuot khong cham (Windows)
echo ===================================================

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [LOI] Khong tim thay Python! Vui long cai Python tu python.org hoac Microsoft Store.
    pause
    exit /b
)

if not exist venv (
    echo [1/2] Dang khoi tao moi truong Python...
    python -m venv venv
    call venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    pip install opencv-python mediapipe pynput
) else (
    call venv\Scripts\activate.bat
)

echo [2/2] Dang khoi chay HandCursor Windows...
python hand_cursor_win.py
pause
