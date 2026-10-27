# Hướng dẫn chạy HandCursor Native trên macOS

Script `hand_cursor_mac.py` sử dụng `PyAutoGUI` và `OpenCV` để trực tiếp điều khiển con trỏ chuột hệ thống ngoài màn hình macOS.

## 1. Cài đặt thư viện
Khuyến nghị tạo môi trường ảo (virtualenv):
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 2. Cấp quyền trên macOS (Quan trọng)
Để điều khiển chuột của máy tính, macOS yêu cầu hai quyền bảo mật trong **System Settings (Cài đặt hệ thống)**:
1. **Camera**: Cấp quyền cho Terminal (hoặc IDE như VSCode / Antigravity).
2. **Accessibility (Trợ năng)**:
   - Vào `System Settings` -> `Privacy & Security` -> `Accessibility`.
   - Bật công tắc cho ứng dụng Terminal hoặc IDE đang chạy script.

## 3. Khởi chạy
```bash
python3 hand_cursor_mac.py
```
- Đưa bàn tay lên trước webcam để di chuyển chuột thật của macOS.
- Bấm phím `q` trên cửa sổ camera để thoát.
