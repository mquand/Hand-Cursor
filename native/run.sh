#!/bin/bash
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    echo "📦 Đang khởi tạo môi trường Python..."
    python3 -m venv venv
    ./venv/bin/pip install --upgrade pip
    ./venv/bin/pip install opencv-python "mediapipe==0.10.14" rumps pynput
fi

echo "🚀 Đang khởi chạy HandCursor Menu Bar App..."
echo "👉 Ứng dụng sẽ xuất hiện dưới dạng icon ✋ trên thanh Menu Bar của macOS (cạnh đồng hồ)."
./venv/bin/python3 hand_cursor_app.py
