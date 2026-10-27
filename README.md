# ✋ HandCursor — Điều khiển chuột bằng cử chỉ tay không chạm

HandCursor là giải pháp biến webcam máy tính thành hệ thống điều khiển chuột thông minh bằng cử chỉ tay, hoạt động **100% Offline**, không cần chuột vật lý hay phần cứng chuyên dụng.

---

## 📂 Cấu trúc dự án

```text
hand-cursor/
├── web/                     # 🌐 Bản Web Prototype (Trải nghiệm ngay trong trình duyệt)
│   ├── index.html           # Giao diện Glassmorphism & Sân chơi tương tác
│   ├── style.css            # Thiết kế Dark Mode, bù sáng viền & animations
│   ├── app.js               # Logic MediaPipe, nhận diện cử chỉ & deadzone
│   └── one_euro_filter.js   # Thuật toán lọc rung One-Euro (CHI 2012)
│
└── native/                  # 💻 Bản Desktop Native (Điều khiển trỏ chuột macOS thật)
    ├── hand_cursor_mac.py   # Script điều khiển chuột toàn hệ điều hành macOS
    ├── requirements.txt     # Thư viện phụ thuộc (OpenCV, MediaPipe, PyAutoGUI)
    └── README_NATIVE.md     # Hướng dẫn cấp quyền Accessibility trên macOS
```

---

## 🚀 Hướng dẫn trải nghiệm nhanh

### 1. Bản Web Prototype (Thử nghiệm ngay lập tức)

Không cần cài đặt thư viện nặng, chỉ cần mở file web bằng bất kỳ HTTP server nào:

```bash
cd /Users/macbook/.gemini/antigravity-ide/scratch/hand-cursor/web
# Dùng Python có sẵn để chạy server cục bộ:
python3 -m http.server 8080
```
Sau đó mở trình duyệt tại: **`http://localhost:8080`**

**Các tính năng có sẵn trên Web:**
- **Thị giác máy tính:** Bật camera, nhận diện 21 khớp xương bàn tay theo thời gian thực.
- **Lọc rung One-Euro & Deadzone:** Khử hiện tượng rung lắc tay khi di chuyển và chống trượt trỏ chuột khi bấm chụm.
- **Sân chơi tương tác (Interactive Playground):**
  - *Click & Double-Click:* Thử nghiệm bấm nút và độ phản hồi.
  - *Chuột phải:* Chụm ngón cái + ngón giữa hoặc giữ chụm 0.5s để mở context menu.
  - *Kéo thả (Kanban):* Chụm ngón để gắp thẻ, di chuyển giữa các cột và buông để thả.
  - *Bảng vẽ ngón tay (Whiteboard):* Vẽ trong không khí bằng đầu ngón tay.
  - *Thuyết trình (Slide Deck):* Vuốt tay sang trái / phải để chuyển trang thuyết trình.
- **Bù sáng viền màn hình (Screen Glow):** Tự động phát sáng viền màn hình khi trời tối để webcam bắt rõ tay.
- **Cân chỉnh 4 góc (Calibration 10s):** Định vị tọa độ 4 góc màn hình phù hợp với khoảng cách ngồi.

---

### 2. Bản Desktop Native macOS (Điều khiển trỏ chuột thật)

Bản native sẽ điều khiển trực tiếp con trỏ chuột của macOS ở mọi ứng dụng (Figma, Chrome, Desktop,...).

```bash
cd /Users/macbook/.gemini/antigravity-ide/scratch/hand-cursor/native
pip install -r requirements.txt
python3 hand_cursor_mac.py
```

> **Lưu ý trên macOS:** Lần đầu chạy, macOS sẽ yêu cầu cấp quyền **Camera** và quyền **Accessibility (Trợ năng)** cho Terminal/iTerm trong `System Settings -> Privacy & Security -> Accessibility`.

---

## ✌️ Bảng cử chỉ (Gesture Cheatsheet)

| Cử chỉ | Thao tác tay | Chức năng tương ứng |
| :--- | :--- | :--- |
| **Dáng trỏ** | Giơ ngón trỏ, các ngón khác tự nhiên | Di chuyển con trỏ chuột |
| **Chụm ngón** | Đầu ngón cái chạm đầu ngón trỏ | Click chuột trái |
| **Kéo thả** | Chụm ngón trỏ + cái rồi giữ và di chuyển | Kéo cửa sổ, gắp thả file/đối tượng |
| **Chuột phải** | Chụm đầu ngón cái + ngón giữa (hoặc giữ chụm 0.5s) | Mở menu ngữ cảnh (Right Click) |
| **Nắm đấm** | Cuộn các ngón tay lại thành nắm đấm | Tạm dừng chuột (Freeze/Pause) |
| **Vuốt tay** | Di chuyển cả bàn tay nhanh sang trái/phải | Chuyển Slide thuyết trình / Chuyển app |
