#!/usr/bin/env python3
"""
HandCursor — Chế độ Test View Trực Quan (Sandboxed Test View)
KHÔNG ĐIỀU KHIỂN CHUỘT THẬT CỦA MÁY TÍNH.
Mở một cửa sổ giao diện trực quan 1280x720 để bạn xem trực tiếp:
 - Bên trái: Camera thực tế + Khung xương tay 21 điểm + Vùng hoạt động (Box).
 - Bên phải: Màn hình ảo (Virtual Screen) có con trỏ ảo, vệt di chuyển và các điểm đích để thử rê chuột.
"""

import cv2
import mediapipe as mp
import numpy as np
import time
import math

class LowPassFilter:
    def __init__(self, alpha=0.5):
        self.alpha = alpha
        self.s = 0.0
        self.initialized = False

    def filter(self, val, alpha=None):
        if alpha is not None:
            self.alpha = alpha
        if not self.initialized:
            self.s = val
            self.initialized = True
            return val
        self.s = self.alpha * val + (1.0 - self.alpha) * self.s
        return self.s

class OneEuroFilter:
    def __init__(self, min_cutoff=0.8, beta=0.04):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.x_filt = LowPassFilter()
        self.dx_filt = LowPassFilter()
        self.last_time = None

    def _alpha(self, cutoff, dt):
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def filter(self, val, timestamp):
        if self.last_time is None:
            self.last_time = timestamp
            return self.x_filt.filter(val)

        dt = max(timestamp - self.last_time, 0.001)
        self.last_time = timestamp

        prev_x = self.x_filt.s
        dx = (val - prev_x) / dt
        edx = self.dx_filt.filter(dx, self._alpha(1.0, dt))
        cutoff = self.min_cutoff + self.beta * abs(edx)
        return self.x_filt.filter(val, self._alpha(cutoff, dt))

class PointFilter:
    def __init__(self, min_cutoff=0.8, beta=0.04):
        self.fx = OneEuroFilter(min_cutoff, beta)
        self.fy = OneEuroFilter(min_cutoff, beta)

    def filter(self, x, y, timestamp):
        return (self.fx.filter(x, timestamp), self.fy.filter(y, timestamp))

def main():
    print("=" * 65)
    print(" 👁️ Đang mở Test View (Không chạm vào chuột thật)...")
    print(" Phím tắt:")
    print("  - 'c': Xóa vệt vẽ của chuột ảo")
    print("  - 'q': Thoát cửa sổ test")
    print("=" * 65)

    # MediaPipe Hands
    mp_hands = mp.solutions.hands
    mp_draw = mp.solutions.drawing_utils
    mp_styles = mp.solutions.drawing_styles

    hands = mp_hands.Hands(
        max_num_hands=1,
        model_complexity=0,
        min_detection_confidence=0.6,
        min_tracking_confidence=0.6
    )

    cap = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)
    if not cap.isOpened():
        cap = cv2.VideoCapture(0)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    # Canvas dimensions: 1280 x 720
    # Left: 640x720 (Camera + HUD)
    # Right: 640x720 (Virtual Playground Screen)
    CANVAS_W, CANVAS_H = 1280, 720
    SCREEN_W, SCREEN_H = 640, 720

    filter_2d = PointFilter(min_cutoff=0.8, beta=0.035)

    # Active hand boundary (normalized coordinates) - MỞ RỘNG TOÀN KHUNG HÌNH (Gần 90% Camera)
    is_wide = True
    box_x_min, box_x_max = 0.06, 0.94
    box_y_min, box_y_max = 0.06, 0.94

    # Sensitivity: 1.4x (Vua phai tren vung rong, bam '+' / '-' de tuy chinh)
    sensitivity = 1.4

    trail_points = []
    click_count = 0
    is_pinching = False

    # Targets to test aiming
    targets = [
        (80, 80, "Goc Tren Trai"),
        (560, 80, "Goc Tren Phai"),
        (320, 360, "Tam Man Hinh"),
        (80, 640, "Goc Duoi Trai"),
        (560, 640, "Goc Duoi Phai"),
    ]

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            continue

        now = time.time()
        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape

        # Main composite canvas
        canvas = np.zeros((CANVAS_H, CANVAS_W, 3), dtype=np.uint8)

        # Process hand landmarks
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = hands.process(rgb)

        cursor_x, cursor_y = None, None
        gesture_text = "Chua thay ban tay"
        gesture_color = (120, 120, 120)
        pinch_dist = 1.0

        if results.multi_hand_landmarks:
            landmarks = results.multi_hand_landmarks[0].landmark

            # Draw skeleton on camera frame
            mp_draw.draw_landmarks(
                frame,
                results.multi_hand_landmarks[0],
                mp_hands.HAND_CONNECTIONS,
                mp_styles.get_default_hand_landmarks_style(),
                mp_styles.get_default_hand_connections_style()
            )

            # Key points
            wrist = landmarks[0]
            thumb_tip = landmarks[4]
            index_tip = landmarks[8]
            index_dip = landmarks[7]
            index_pip = landmarks[6]
            index_mcp = landmarks[5]
            middle_tip = landmarks[12]

            # Cursor Anchor: Blend tip (8) with DIP (7) to eliminate jitter when pointing straight at camera
            anchor_x = 0.8 * index_tip.x + 0.2 * index_dip.x
            anchor_y = 0.8 * index_tip.y + 0.2 * index_dip.y

            # Robust Click: Measure distance to index tip OR index joint (supports both pinch and pistol trigger pull)
            dist_tip = math.dist((thumb_tip.x, thumb_tip.y), (index_tip.x, index_tip.y))
            dist_joint = math.dist((thumb_tip.x, thumb_tip.y), (index_pip.x, index_pip.y))
            pinch_dist = min(dist_tip, dist_joint)

            # Threshold for click (slightly more forgiving for forward pointing)
            is_currently_pinching = pinch_dist < 0.065

            if is_currently_pinching and not is_pinching:
                click_count += 1
                is_pinching = True
            elif not is_currently_pinching:
                is_pinching = False

            # Check gesture
            if is_pinching:
                gesture_text = "CHUM NGON / BOP CO (CLICK!)"
                gesture_color = (0, 255, 0)
            else:
                gesture_text = "CHI TAY / SUNG (DI CHUYEN)"
                gesture_color = (255, 200, 0)

            # Map from camera active box to Virtual Screen (Right Panel)
            norm_x = (anchor_x - box_x_min) / (box_x_max - box_x_min)
            norm_y = (anchor_y - box_y_min) / (box_y_max - box_y_min)

            # Apply sensitivity multiplier around center
            center_x = SCREEN_W / 2.0
            center_y = SCREEN_H / 2.0
            raw_target_x = center_x + (norm_x * SCREEN_W - center_x) * sensitivity
            raw_target_y = center_y + (norm_y * SCREEN_H - center_y) * sensitivity

            # Clamp within screen bounds
            raw_target_x = max(0.0, min(float(SCREEN_W), raw_target_x))
            raw_target_y = max(0.0, min(float(SCREEN_H), raw_target_y))

            # Apply One-Euro filter
            smoothed_x, smoothed_y = filter_2d.filter(raw_target_x, raw_target_y, now)
            cursor_x = int(smoothed_x)
            cursor_y = int(smoothed_y)

            # Store trail
            trail_points.append((cursor_x, cursor_y, is_pinching))
            if len(trail_points) > 35:
                trail_points.pop(0)

        # 1. Render Left Panel (Camera Feed)
        # Resize camera frame to fit 640x480 inside 640x720
        frame_resized = cv2.resize(frame, (640, 480))
        
        # Draw Active Box on camera feed
        bx1 = int(box_x_min * 640)
        by1 = int(box_y_min * 480)
        bx2 = int(box_x_max * 640)
        by2 = int(box_y_max * 480)
        cv2.rectangle(frame_resized, (bx1, by1), (bx2, by2), (0, 255, 255), 2)
        cv2.putText(frame_resized, "Vung tay hoat dong", (bx1 + 10, by1 + 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        canvas[0:480, 0:640] = frame_resized

        # Left HUD Details
        cv2.rectangle(canvas, (0, 480), (640, 720), (25, 28, 38), -1)
        cv2.putText(canvas, f"Cu chi: {gesture_text}", (20, 520),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, gesture_color, 2)
        cv2.putText(canvas, f"Khoang cach chum: {pinch_dist:.3f} (Nguong: 0.055)", (20, 555),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 200, 200), 1)
        cv2.putText(canvas, f"So lan da Click: {click_count}", (20, 590),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 200), 2)
        cv2.putText(canvas, f"DO NHAY (Sens): {sensitivity:.1f}x  [Bam '+' tang / '-' giam]", (20, 635),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.putText(canvas, "Bam 'c': Xoa vet | Bam 'q': Thoat", (20, 680),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (100, 150, 255), 1)

        # 2. Render Right Panel (Virtual Screen Sandbox)
        # Background: dark sleek grey
        cv2.rectangle(canvas, (640, 0), (CANVAS_W, CANVAS_H), (15, 18, 25), -1)
        
        # Border divider
        cv2.line(canvas, (640, 0), (640, CANVAS_H), (60, 65, 80), 2)
        cv2.putText(canvas, "MAN HINH AO (VIRTUAL SCREEN TEST)", (660, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(canvas, f"Sens: {sensitivity:.1f}x", (1120, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

        # Draw target aiming circles
        for tx, ty, label in targets:
            # Check if cursor is hovering over target
            is_hover = False
            if cursor_x is not None:
                dist_to_target = math.dist((cursor_x, cursor_y), (tx, ty))
                is_hover = dist_to_target < 40

            t_color = (0, 255, 120) if is_hover else (70, 80, 100)
            t_radius = 35 if is_hover else 25
            cv2.circle(canvas, (640 + tx, ty), t_radius, t_color, 2)
            cv2.putText(canvas, label, (640 + tx - 45, ty + 45),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (140, 150, 170), 1)

        # Draw trail
        for i in range(1, len(trail_points)):
            p1 = trail_points[i - 1]
            p2 = trail_points[i]
            color = (0, 255, 100) if p2[2] else (255, 180, 50)
            thickness = int(np.linspace(1, 4, len(trail_points))[i])
            cv2.line(canvas, (640 + p1[0], p1[1]), (640 + p2[0], p2[1]), color, thickness)

        # Draw Virtual Cursor
        if cursor_x is not None:
            c_pos = (640 + cursor_x, cursor_y)
            if is_pinching:
                # Big pulsing green circle for click
                cv2.circle(canvas, c_pos, 18, (0, 255, 0), -1)
                cv2.circle(canvas, c_pos, 28, (0, 255, 120), 2)
                cv2.putText(canvas, "CLICK", (c_pos[0] + 25, c_pos[1] + 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            else:
                # Blue glowing cursor for pointing
                cv2.circle(canvas, c_pos, 10, (255, 200, 0), -1)
                cv2.circle(canvas, c_pos, 20, (255, 220, 50), 2)

        cv2.imshow("HandCursor - Phong Thi Nghiem Truc Quan (Sandbox Test)", canvas)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('c'):
            trail_points.clear()
        elif key == ord('w'):
            is_wide = not is_wide
            if is_wide:
                box_x_min, box_x_max = 0.06, 0.94
                box_y_min, box_y_max = 0.06, 0.94
            else:
                box_x_min, box_x_max = 0.18, 0.82
                box_y_min, box_y_max = 0.18, 0.82
        elif key == ord('+') or key == ord('='):
            sensitivity = round(min(sensitivity + 0.3, 4.5), 1)
        elif key == ord('-') or key == ord('_'):
            sensitivity = round(max(sensitivity - 0.3, 0.8), 1)

    cap.release()
    cv2.destroyAllWindows()
    print("👋 Da dong che do Test.")

if __name__ == "__main__":
    main()
