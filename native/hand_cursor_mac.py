#!/usr/bin/env python3
"""
HandCursor Ultra-Fast & Complete Native Mouse Controller for macOS
Full mouse functionality:
  1. Pointer Movement: 1 Index finger (One-Euro dynamic filter)
  2. Left Click: Pinch (Thumb + Index)
  3. Double Click: 2 rapid pinches (with auto-coordinate lock & CGEvent clickCount=2)
  4. Scroll Up / Down: 2 Fingers extended (Index + Middle) - Natural Trackpad Scroll
  5. Right Click: Pinch (Thumb + Middle)
  6. Drag & Drop / Selection: Pinch & Hold & Move
  7. Pause / Clutch: Fist (Cuộn bàn tay)
  8. Calibration: Press 'c' to calibrate 4 corners, 's' to save, 'r' to reset
"""

import sys
import time
import math
import threading
import ctypes
import json
import os
from ctypes import c_void_p, c_int, c_uint32, c_int32, c_double, Structure

import cv2
import mediapipe as mp

# ==================== macOS CoreGraphics via ctypes ====================
class CGPoint(Structure):
    _fields_ = [('x', c_double), ('y', c_double)]

try:
    cg = ctypes.cdll.LoadLibrary('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
    
    # Mouse Move / Click API
    cg.CGEventCreateMouseEvent.restype = c_void_p
    cg.CGEventCreateMouseEvent.argtypes = [c_void_p, c_int, CGPoint, c_int]
    
    # Scroll Wheel API
    cg.CGEventCreateScrollWheelEvent.restype = c_void_p
    cg.CGEventCreateScrollWheelEvent.argtypes = [c_void_p, c_uint32, c_uint32, c_int32]

    # Set Click Count (for double/triple click)
    cg.CGEventSetIntegerValueField.restype = None
    cg.CGEventSetIntegerValueField.argtypes = [c_void_p, c_uint32, ctypes.c_int64]

    cg.CGEventPost.restype = None
    cg.CGEventPost.argtypes = [c_int, c_void_p]
    
    cg.CFRelease.restype = None
    cg.CFRelease.argtypes = [c_void_p]

    cg.CGMainDisplayID.restype = c_int
    cg.CGDisplayPixelsWide.restype = c_int
    cg.CGDisplayPixelsWide.argtypes = [c_int]
    cg.CGDisplayPixelsHigh.restype = c_int
    cg.CGDisplayPixelsHigh.argtypes = [c_int]

    main_display_id = cg.CGMainDisplayID()
    SCREEN_WIDTH = cg.CGDisplayPixelsWide(main_display_id)
    SCREEN_HEIGHT = cg.CGDisplayPixelsHigh(main_display_id)
    HAS_CORE_GRAPHICS = True
except Exception as e:
    print(f"[Warning] CoreGraphics direct load failed: {e}. Fallback mode.")
    import pyautogui
    SCREEN_WIDTH, SCREEN_HEIGHT = pyautogui.size()
    HAS_CORE_GRAPHICS = False

# CoreGraphics Constants
kCGEventLeftMouseDown = 1
kCGEventLeftMouseUp = 2
kCGEventRightMouseDown = 3
kCGEventRightMouseUp = 4
kCGEventMouseMoved = 5
kCGEventLeftMouseDragged = 6
kCGEventRightMouseDragged = 7
kCGHIDEventTap = 0
kCGMouseEventClickState = 1  # Field 1 = click count (1=single, 2=double)

def post_mouse_event(event_type, x, y, button=0, click_count=1):
    """Post direct hardware mouse event with zero latency (< 0.05ms)"""
    if HAS_CORE_GRAPHICS:
        pt = CGPoint(float(x), float(y))
        evt = cg.CGEventCreateMouseEvent(None, event_type, pt, button)
        if evt:
            if click_count > 1:
                cg.CGEventSetIntegerValueField(evt, kCGMouseEventClickState, click_count)
            cg.CGEventPost(kCGHIDEventTap, evt)
            cg.CFRelease(evt)
    else:
        if event_type == kCGEventMouseMoved:
            pyautogui.moveTo(x, y)
        elif event_type == kCGEventLeftMouseDown:
            pyautogui.mouseDown()
        elif event_type == kCGEventLeftMouseUp:
            pyautogui.mouseUp()
        elif event_type == kCGEventRightMouseDown:
            pyautogui.rightClick()

def post_scroll_event(delta_y):
    """Post natural pixel scroll wheel event"""
    if HAS_CORE_GRAPHICS:
        # Units: 0 = Pixel scroll (silky smooth like macOS trackpad)
        evt = cg.CGEventCreateScrollWheelEvent(None, 0, 1, int(delta_y))
        if evt:
            cg.CGEventPost(kCGHIDEventTap, evt)
            cg.CFRelease(evt)
    else:
        pyautogui.scroll(int(delta_y))

# ==================== Threaded Zero-Buffer Camera Stream ====================
class ThreadedCamera:
    """Continuously grabs frames in background thread to eliminate OpenCV buffering lag"""
    def __init__(self, src=0, width=640, height=480):
        # On macOS, cv2.CAP_AVFOUNDATION is the native backend
        self.cap = cv2.VideoCapture(src, cv2.CAP_AVFOUNDATION)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(src)

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, 60)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self.ret, self.frame = self.cap.read()
        self.is_ready = self.cap.isOpened() and self.ret
        
        if not self.is_ready:
            print("\n" + "!" * 70)
            print(" ⚠️ CHƯA CẤP QUYỀN CAMERA TRÊN macOS!")
            print(" macOS đang chặn ứng dụng truy cập webcam vì lý do bảo mật.")
            print(" 👉 Vui lòng vào: System Settings -> Privacy & Security -> Camera")
            print("    và BẬT CÔNG TẮC cho Terminal (hoặc iTerm / IDE bạn đang dùng).")
            print(" 👉 Hoặc chạy lệnh: open \"x-apple.systempreferences:com.apple.preference.security?Privacy_Camera\"")
            print("!" * 70 + "\n")

        self.stopped = False
        self.lock = threading.Lock()
        
        if self.is_ready:
            self.thread = threading.Thread(target=self._capture_loop, daemon=True)
            self.thread.start()

    def _capture_loop(self):
        while not self.stopped:
            ret, frame = self.cap.read()
            if ret:
                with self.lock:
                    self.ret = ret
                    self.frame = frame
            time.sleep(0.002)

    def read(self):
        with self.lock:
            if not self.ret or self.frame is None:
                return False, None
            return True, self.frame.copy()

    def stop(self):
        self.stopped = True
        self.thread.join(timeout=1.0)
        self.cap.release()

# ==================== One-Euro Filter (Dynamic Velocity) ====================
class LowPassFilter:
    __slots__ = ('alpha', 's', 'initialized')
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
    __slots__ = ('min_cutoff', 'beta', 'd_cutoff', 'x_filt', 'dx_filt', 'last_time')
    def __init__(self, min_cutoff=0.8, beta=0.045, d_cutoff=1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
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
        edx = self.dx_filt.filter(dx, self._alpha(self.d_cutoff, dt))

        cutoff = self.min_cutoff + self.beta * abs(edx)
        return self.x_filt.filter(val, self._alpha(cutoff, dt))

class FastPointFilter:
    def __init__(self, min_cutoff=0.8, beta=0.045):
        self.fx = OneEuroFilter(min_cutoff, beta)
        self.fy = OneEuroFilter(min_cutoff, beta)

    def filter(self, x, y, timestamp):
        return (self.fx.filter(x, timestamp), self.fy.filter(y, timestamp))

# ==================== Calibration Config Management ====================
CONFIG_FILE = os.path.expanduser("~/.handcursor_config.json")

def load_calibration_config():
    """Load calibration from config file if exists"""
    global box_x_min, box_x_max, box_y_min, box_y_max, sensitivity
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                box_x_min = config.get('box_x_min', 0.25)
                box_x_max = config.get('box_x_max', 0.75)
                box_y_min = config.get('box_y_min', 0.25)
                box_y_max = config.get('box_y_max', 0.75)
                sensitivity = config.get('sensitivity', 1.8)
                print(f"✅ Đã tải cấu hình từ {CONFIG_FILE}")
                return True
    except Exception as e:
        print(f"⚠️ Lỗi khi tải cấu hình: {e}")
    return False

def save_calibration_config():
    """Save current calibration to config file"""
    global box_x_min, box_x_max, box_y_min, box_y_max, sensitivity
    try:
        config = {
            'box_x_min': box_x_min,
            'box_x_max': box_x_max,
            'box_y_min': box_y_min,
            'box_y_max': box_y_max,
            'sensitivity': sensitivity
        }
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"✅ Đã lưu cấu hình vào {CONFIG_FILE}")
        return True
    except Exception as e:
        print(f"⚠️ Lỗi khi lưu cấu hình: {e}")
        return False

def reset_calibration_config():
    """Reset calibration to default values"""
    global box_x_min, box_x_max, box_y_min, box_y_max, sensitivity
    box_x_min, box_x_max = 0.25, 0.75
    box_y_min, box_y_max = 0.25, 0.75
    sensitivity = 1.8
    if os.path.exists(CONFIG_FILE):
        os.remove(CONFIG_FILE)
    print("✅ Đã reset về cấu hình mặc định")

# ==================== Main Controller ====================
def main():
    print("=" * 70)
    print(" 🖱️ HandCursor FULL MOUSE — Bộ điều khiển chuột toàn diện cho macOS")
    print("=" * 70)
    print(" 📋 Bộ cử chỉ đầy đủ:")
    print("  👉 1 Ngón trỏ             : Di chuyển con trỏ chuột")
    print("  🤏 Chụm ngón trỏ + cái    : Click chuột trái")
    print("  ⚡ Chụm 2 lần nhanh (<0.4s): Double Click (Tự khóa tọa độ)")
    print("  🤏 Giữ chụm & di chuyển   : Kéo thả (Drag & Drop / Bôi đen)")
    print("  ✌️ 2 Ngón (Trỏ + Giữa)    : Cuộn trang lên / xuống (Scroll)")
    print("  🤌 Chụm ngón giữa + cái   : Chuột phải (Context Menu)")
    print("  ✊ Nắm đấm                : Tạm dừng / Nhấc chuột (Clutch)")
    print("=" * 70)
    print(" ⌨️ Phím tắt:")
    print("  'q' : Thoát chương trình")
    print("  'c' : Chế độ Calibration (Đưa tay tới 4 góc)")
    print("  's' : Lưu cấu hình Calibration hiện tại")
    print("  'r' : Reset về cấu hình mặc định")
    print("=" * 70)

    # Load saved calibration config
    load_calibration_config()

    # MediaPipe Lite (60 FPS on Apple Silicon)
    mp_hands = mp.solutions.hands
    mp_draw = mp.solutions.drawing_utils
    mp_styles = mp.solutions.drawing_styles

    hands = mp_hands.Hands(
        max_num_hands=1,
        model_complexity=0,
        min_detection_confidence=0.6,
        min_tracking_confidence=0.6
    )

    cam = ThreadedCamera(src=0, width=640, height=480)
    if not cam.is_ready:
        print("❌ Dừng chương trình do chưa có quyền Camera.")
        return
    time.sleep(0.3)

    point_filter = FastPointFilter(min_cutoff=0.8, beta=0.045)

    # Active hand boundary
    box_x_min, box_x_max = 0.25, 0.75
    box_y_min, box_y_max = 0.25, 0.75
    calib_w = box_x_max - box_x_min
    calib_h = box_y_max - box_y_min

    sensitivity = 1.8
    PINCH_CLICK_THRESH = 0.052
    PINCH_RIGHT_THRESH = 0.050

    # Calibration Mode State
    in_calibration_mode = False
    calib_step = 0  # 0-3 for 4 corners
    calib_corners = []  # Store (x, y) for each corner
    calib_w = box_x_max - box_x_min
    calib_h = box_y_max - box_y_min

    # States
    is_left_down = False
    last_right_click = 0
    click_deadzone_until = 0
    cur_x, cur_y = SCREEN_WIDTH / 2.0, SCREEN_HEIGHT / 2.0

    # Double click tracking
    last_click_release_time = 0
    last_click_pos = (cur_x, cur_y)
    double_click_active = False

    # Scroll tracking (2 fingers & momentum)
    in_scroll_mode = False
    prev_scroll_y = None
    scroll_velocity = 0.0
    momentum_velocity = 0.0

    fps_count = 0
    fps_timer = time.time()
    current_fps = 0

    try:
        while True:
            ret, frame = cam.read()
            if not ret or frame is None:
                time.sleep(0.005)
                continue

            fps_count += 1
            now = time.time()
            if now - fps_timer >= 1.0:
                current_fps = fps_count
                fps_count = 0
                fps_timer = now

            # Mirror frame horizontally
            frame = cv2.flip(frame, 1)
            h, w, _ = frame.shape

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands.process(rgb)

            status_str = "Sẵn sàng"
            status_color = (180, 180, 180)

            if results.multi_hand_landmarks:
                landmarks = results.multi_hand_landmarks[0].landmark

                # Key landmarks
                wrist = landmarks[0]
                thumb_tip = landmarks[4]
                index_tip = landmarks[8]
                middle_tip = landmarks[12]
                ring_tip = landmarks[16]
                pinky_tip = landmarks[20]

                index_mcp = landmarks[5]
                middle_mcp = landmarks[9]
                ring_mcp = landmarks[13]
                pinky_mcp = landmarks[17]

                # Calibration Mode Logic
                if in_calibration_mode:
                    pinch_left = math.dist((thumb_tip.x, thumb_tip.y), (index_tip.x, index_tip.y))

                    if pinch_left < PINCH_CLICK_THRESH:
                        # Pinch detected - capture this corner
                        calib_corners.append((index_tip.x, index_tip.y))
                        calib_step += 1

                        if calib_step >= 4:
                            # All 4 corners captured - update calibration box
                            xs = [c[0] for c in calib_corners]
                            ys = [c[1] for c in calib_corners]
                            box_x_min, box_x_max = min(xs), max(xs)
                            box_y_min, box_y_max = min(ys), max(ys)
                            calib_w = box_x_max - box_x_min
                            calib_h = box_y_max - box_y_min

                            in_calibration_mode = False
                            print(f"\n✅ Calibration hoàn tất!")
                            print(f"   Box: X[{box_x_min:.3f}-{box_x_max:.3f}] Y[{box_y_min:.3f}-{box_y_max:.3f}]")
                            print(f"   Nhấn 's' để lưu cấu hình")
                        else:
                            corner_names = ["góc trên trái", "góc trên phải", "góc dưới phải", "góc dưới trái"]
                            print(f"\n🎯 Đã ghi nhận góc {calib_step}/4 - Đưa tay tới {corner_names[calib_step]}")

                    # Draw calibration overlay
                    if calib_step < 4:
                        corner_positions = [
                            (50, 50), (w - 50, 50), (w - 50, h - 50), (50, h - 50)
                        ]
                        cv2.circle(frame, corner_positions[calib_step], 30, (0, 255, 0), 3)
                        cv2.putText(frame, f"Calib {calib_step + 1}/4", (50, h - 30),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

                    status_str = f"CALIBRATION {calib_step + 1}/4"
                    status_color = (0, 255, 0)
                    mp_draw.draw_landmarks(
                        frame,
                        results.multi_hand_landmarks[0],
                        mp_hands.HAND_CONNECTIONS,
                        mp_styles.get_default_hand_landmarks_style(),
                        mp_styles.get_default_hand_connections_style()
                    )
                    continue  # Skip normal processing during calibration

                # 1. Check Fist (Tạm dừng / Nhấc chuột)
                tips = [8, 12, 16, 20]
                mcps = [5, 9, 13, 17]
                fist_count = 0
                for t_idx, m_idx in zip(tips, mcps):
                    dt = math.dist((landmarks[t_idx].x, landmarks[t_idx].y), (wrist.x, wrist.y))
                    dm = math.dist((landmarks[m_idx].x, landmarks[m_idx].y), (wrist.x, wrist.y))
                    if dt < dm * 1.15:
                        fist_count += 1

                if fist_count >= 3:
                    status_str = "TẠM DỪNG (Nắm đấm)"
                    status_color = (0, 0, 255)
                    in_scroll_mode = False
                    if is_left_down:
                        post_mouse_event(kCGEventLeftMouseUp, cur_x, cur_y)
                        is_left_down = False

                else:
                    # Check Finger Extensions
                    d_index = math.dist((index_tip.x, index_tip.y), (wrist.x, wrist.y))
                    d_index_mcp = math.dist((index_mcp.x, index_mcp.y), (wrist.x, wrist.y))
                    is_index_extended = d_index > d_index_mcp * 1.2

                    d_middle = math.dist((middle_tip.x, middle_tip.y), (wrist.x, wrist.y))
                    d_middle_mcp = math.dist((middle_mcp.x, middle_mcp.y), (wrist.x, wrist.y))
                    is_middle_extended = d_middle > d_middle_mcp * 1.2

                    d_ring = math.dist((ring_tip.x, ring_tip.y), (wrist.x, wrist.y))
                    d_ring_mcp = math.dist((ring_mcp.x, ring_mcp.y), (wrist.x, wrist.y))
                    is_ring_folded = d_ring < d_ring_mcp * 1.25

                    d_pinky = math.dist((pinky_tip.x, pinky_tip.y), (wrist.x, wrist.y))
                    d_pinky_mcp = math.dist((pinky_mcp.x, pinky_mcp.y), (wrist.x, wrist.y))
                    is_pinky_folded = d_pinky < d_pinky_mcp * 1.25

                    # Pinch distances
                    pinch_left = math.dist((thumb_tip.x, thumb_tip.y), (index_tip.x, index_tip.y))
                    pinch_right = math.dist((thumb_tip.x, thumb_tip.y), (middle_tip.x, middle_tip.y))

                    # 2. CUỘN CHUỘT (SCROLL UP / DOWN) CÓ QUÁN TÍNH (INERTIA FLICK)
                    # Hỗ trợ: Giơ 2 ngón (Trỏ + Giữa) HOẶC Xòe bàn tay vuốt lên/xuống
                    is_two_finger_scroll = (
                        is_index_extended and is_middle_extended and
                        is_ring_folded and is_pinky_folded and
                        pinch_left > PINCH_CLICK_THRESH * 1.4
                    )
                    
                    # Hoặc vuốt bằng cả bàn tay xòe lên/xuống
                    is_open_hand_flick = (
                        is_index_extended and is_middle_extended and
                        (not is_ring_folded) and (not is_pinky_folded) and
                        fist_count == 0 and pinch_left > PINCH_CLICK_THRESH * 1.5
                    )

                    is_scrolling_now = is_two_finger_scroll or is_open_hand_flick

                    if is_scrolling_now:
                        current_mid_y = (index_tip.y + middle_tip.y) / 2.0
                        if in_scroll_mode and prev_scroll_y is not None:
                            # Natural scrolling: tay đi xuống -> trang cuộn xuống
                            delta_y = (prev_scroll_y - current_mid_y) * 620.0
                            if abs(delta_y) > 1.2:
                                post_scroll_event(delta_y)
                                # Cập nhật vận tốc quán tính (Inertia Momentum)
                                scroll_velocity = 0.65 * delta_y + 0.35 * scroll_velocity
                                status_str = f"VUỐT CUỘN {'LÊN ⬆️' if delta_y > 0 else 'XUỐNG ⬇️'}"
                                status_color = (0, 255, 255)
                            else:
                                scroll_velocity *= 0.5
                                status_str = "SẴN SÀNG CUỘN"
                                status_color = (0, 200, 200)
                        else:
                            in_scroll_mode = True
                            scroll_velocity = 0.0
                            status_str = "CUỘN TRANG (2 Ngón)"
                            status_color = (0, 200, 200)
                        prev_scroll_y = current_mid_y
                    else:
                        # Khi vừa dứt tay khỏi cử chỉ vuốt: Kích hoạt quán tính trượt tiếp (Momentum Coasting)
                        if in_scroll_mode and abs(scroll_velocity) > 5.0:
                            momentum_velocity = scroll_velocity * 0.8
                        in_scroll_mode = False
                        prev_scroll_y = None

                    # Thực thi quán tính (Momentum Decay) nếu vừa vuốt một cú dứt khoát
                    if not in_scroll_mode and abs(momentum_velocity) > 0.8:
                        post_scroll_event(int(momentum_velocity))
                        momentum_velocity *= 0.88  # Hãm phanh êm ái như iPhone / Mac Trackpad
                        status_str = f"QUÁN TÍNH {'⬆️' if momentum_velocity > 0 else '⬇️'}"
                        status_color = (0, 230, 180)

                    if not is_scrolling_now:
                        # Normalized map to screen coordinates
                        norm_x = (index_tip.x - box_x_min) / calib_w
                        norm_y = (index_tip.y - box_y_min) / calib_h

                        target_x = SCREEN_WIDTH * norm_x
                        target_y = SCREEN_HEIGHT * norm_y
                        center_x, center_y = SCREEN_WIDTH / 2.0, SCREEN_HEIGHT / 2.0
                        target_x = center_x + (target_x - center_x) * sensitivity
                        target_y = center_y + (target_y - center_y) * sensitivity

                        is_pinching_left = pinch_left < PINCH_CLICK_THRESH

                        # 3. DOUBLE-CLICK DETECTION & COORDINATE LOCK
                        if is_pinching_left and not is_left_down:
                            time_since_last_release = now - last_click_release_time
                            if time_since_last_release < 0.38:
                                # Snap to previous click coordinates (prevents missing double-click due to tiny hand drift!)
                                cur_x, cur_y = last_click_pos
                                double_click_active = True
                                click_deadzone_until = now + 0.15
                            else:
                                double_click_active = False
                                click_deadzone_until = now + 0.07

                        if now > click_deadzone_until:
                            cur_x, cur_y = point_filter.filter(target_x, target_y, now)
                            cur_x = max(0, min(SCREEN_WIDTH - 1, cur_x))
                            cur_y = max(0, min(SCREEN_HEIGHT - 1, cur_y))

                        # 4. RIGHT CLICK
                        if pinch_right < PINCH_RIGHT_THRESH:
                            if now - last_right_click > 0.6:
                                post_mouse_event(kCGEventRightMouseDown, cur_x, cur_y, button=1)
                                post_mouse_event(kCGEventRightMouseUp, cur_x, cur_y, button=1)
                                last_right_click = now
                            status_str = "CHUỘT PHẢI"
                            status_color = (255, 0, 255)

                        # 5. LEFT CLICK / DOUBLE CLICK / DRAG
                        elif is_pinching_left:
                            if not is_left_down:
                                click_count = 2 if double_click_active else 1
                                post_mouse_event(kCGEventLeftMouseDown, cur_x, cur_y, click_count=click_count)
                                is_left_down = True
                                last_click_pos = (cur_x, cur_y)
                                status_str = "DOUBLE CLICK! ⚡" if double_click_active else "CLICK"
                                status_color = (255, 128, 0) if double_click_active else (0, 255, 0)
                            else:
                                post_mouse_event(kCGEventLeftMouseDragged, cur_x, cur_y)
                                status_str = "KÉO THẢ (Dragging)"
                                status_color = (0, 255, 0)
                        else:
                            if is_left_down:
                                post_mouse_event(kCGEventLeftMouseUp, cur_x, cur_y)
                                is_left_down = False
                                last_click_release_time = now
                            post_mouse_event(kCGEventMouseMoved, cur_x, cur_y)
                            status_str = "DI CHUYỂN"
                            status_color = (255, 200, 0)

                # Draw minimal skeleton on preview
                mp_draw.draw_landmarks(
                    frame,
                    results.multi_hand_landmarks[0],
                    mp_hands.HAND_CONNECTIONS,
                    mp_styles.get_default_hand_landmarks_style(),
                    mp_styles.get_default_hand_connections_style()
                )

            # HUD Display
            cv2.rectangle(frame, (8, 8), (380, 52), (18, 20, 28), -1)
            cv2.putText(frame, f"{status_str} | {current_fps} FPS", (18, 38),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.62, status_color, 2)

            cv2.imshow("HandCursor Full Mouse (Nhan 'q' de thoat)", frame)

            # Keyboard shortcuts
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('c'):
                # Start calibration mode
                in_calibration_mode = True
                calib_step = 0
                calib_corners = []
                print("\n🎯 Chế độ Calibration: Đưa ngón tay tới góc trên trái (1/4)")
            elif key == ord('s'):
                # Save calibration
                save_calibration_config()
            elif key == ord('r'):
                # Reset calibration
                reset_calibration_config()

    finally:
        if is_left_down:
            post_mouse_event(kCGEventLeftMouseUp, 0, 0)
        cam.stop()
        cv2.destroyAllWindows()
        print("👋 Đã tắt HandCursor Native.")

if __name__ == "__main__":
    main()
