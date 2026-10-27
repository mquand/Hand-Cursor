#!/bin/bash
cd "$(dirname "$0")"
echo "👁️ Đang mở Phòng Thí Nghiệm Trực Quan HandCursor..."
echo "🔒 Chế độ này KHÔNG chạm vào chuột máy tính thật, bạn yên tâm test!"
./venv/bin/python3 test_view.py
