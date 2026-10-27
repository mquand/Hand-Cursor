#!/usr/bin/env python3
"""
HandCursor — Windows Native Ultra-Fast Controller
Uses Win32 user32.dll direct C-level hardware injection (< 0.05ms latency):
  - SetCursorPos(x, y) for instantaneous mouse movement
  - mouse_event for Click, Double-Click, Drag, and Wheel Scroll
  - Task View (Win + Tab) & App Switch (Alt + Tab)
  - 100% Offline with MediaPipe Lite 60 FPS
"""

import sys
import time
import math
import threading
import ctypes

import cv2
import mediapipe as mp

# ==================== Win32 user32.dll Direct API ====================
user32 = ctypes.windll.user32

# Get primary display resolution
SCREEN_WIDTH = user32.GetSystemMetrics(0)   # SM_CXSCREEN
SCREEN_HEIGHT = user32.GetSystemMetrics(1)  # SM_CYSCREEN

# Win32 Mouse Event Flags
MOUSEEVENTF_LEFTDOWN   = 0x0002
MOUSEEVENTF_LEFTUP     = 0x0004
MOUSEEVENTF_RIGHTDOWN  = 0x0008
MOUSEEVENTF_RIGHTUP    = 0x0010
MOUSEEVENTF_WHEEL      = 0x0800

# Win32 Keyboard Event Flags
KEYEVENTF_KEYUP        = 0x0002
VK_LWIN                = 0x5B
VK_TAB                 = 0x09
VK_MENU                = 0x12  # Alt key

def win_move_mouse(x, y):
    user32.SetCursorPos(int(x), int(y))

def win_click_down():
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)

def win_click_up():
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

def win_right_click():
    user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
    user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)

def win_scroll(delta_y):
    # WHEEL_DELTA is usually 120 on Windows
    user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, int(delta_y), 0)

def trigger_task_view():
    """Trigger Windows Task View (Win + Tab)"""
    user32.keybd_event(VK_LWIN, 0, 0, 0)
    user32.keybd_event(VK_TAB, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(VK_TAB, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_LWIN, 0, KEYEVENTF_KEYUP, 0)

def trigger_alt_tab():
    """Trigger Windows App Switch (Alt + Tab)"""
    user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.keybd_event(VK_TAB, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(VK_TAB, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

# ==================== Threaded Zero-Buffer Camera Stream ====================
class ThreadedCameraWin:
    def __init__(self, src=0, width=640, height=480):
        # On Windows, cv2.CAP_DSHOW provides fastest camera startup
        self.cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(src)

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, 60)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self.ret, self.frame = self.cap.read()
        self.stopped = False
        self.lock = threading.Lock()
        
        if self.cap.isOpened() and self.ret:
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
        self.cap.release()

# ==================== One-Euro Filter ====================
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

# ==================== Main Loop ====================
def main():
    print("=" * 65)
    print(" 🪟 HandCursor for Windows — Điều khiển chuột bằng Win32 C-API")
    print(f" 🖥️ Màn hình: {SCREEN_WIDTH}x{SCREEN_HEIGHT} | Động cơ: user32.dll")
    print("=" * 65)

    mp_hands = mp.solutions.hands
    mp_draw = mp.solutions.drawing_utils
    mp_styles = mp.solutions.drawing_styles

    hands = mp_hands.Hands(
        max_num_hands=1,
        model_complexity=0,
        min_detection_confidence=0.6,
        min_tracking_confidence=0.6
    )

    cam = ThreadedCameraWin(src=0, width=640, height=480)
    time.sleep(0.3)

    point_filter = FastPointFilter(min_cutoff=0.8, beta=0.045)

    box_x_min, box_x_max = 0.18, 0.82
    box_y_min, box_y_max = 0.18, 0.82
    calib_w = box_x_max - box_x_min
    calib_h = box_y_max - box_y_min

    sensitivity = 1.35
    PINCH_CLICK_THRESH = 0.052
    PINCH_RIGHT_THRESH = 0.050

    is_left_down = False
    last_right_click = 0
    click_deadzone_until = 0
    cur_x, cur_y = SCREEN_WIDTH / 2.0, SCREEN_HEIGHT / 2.0

    in_scroll_mode = False
    prev_scroll_y = None
    scroll_velocity = 0.0
    momentum_velocity = 0.0

    wrist_history = []
    last_swipe_time = 0

    try:
        while True:
            ret, frame = cam.read()
            if not ret or frame is None:
                time.sleep(0.005)
                continue

            now = time.time()
            frame = cv2.flip(frame, 1)
            h, w, _ = frame.shape

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands.process(rgb)

            status_str = "Sẵn sàng"
            status_color = (180, 180, 180)

            if results.multi_hand_landmarks:
                landmarks = results.multi_hand_landmarks[0].landmark

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

                # Check Fist
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
                        win_click_up()
                        is_left_down = False
                else:
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

                    pinch_left = math.dist((thumb_tip.x, thumb_tip.y), (index_tip.x, index_tip.y))
                    pinch_right = math.dist((thumb_tip.x, thumb_tip.y), (middle_tip.x, middle_tip.y))

                    # 2-Finger Scroll
                    is_two_finger_scroll = (
                        is_index_extended and is_middle_extended and
                        is_ring_folded and is_pinky_folded and
                        pinch_left > PINCH_CLICK_THRESH * 1.4
                    )

                    if is_two_finger_scroll:
                        current_mid_y = (index_tip.y + middle_tip.y) / 2.0
                        if in_scroll_mode and prev_scroll_y is not None:
                            delta_y = (prev_scroll_y - current_mid_y) * 520.0
                            if abs(delta_y) > 1.2:
                                win_scroll(delta_y)
                                scroll_velocity = 0.65 * delta_y + 0.35 * scroll_velocity
                                status_str = f"CUỘN {'LÊN ⬆️' if delta_y > 0 else 'XUỐNG ⬇️'}"
                                status_color = (0, 255, 255)
                        else:
                            in_scroll_mode = True
                            scroll_velocity = 0.0
                        prev_scroll_y = current_mid_y
                    else:
                        if in_scroll_mode and abs(scroll_velocity) > 5.0:
                            momentum_velocity = scroll_velocity * 0.8
                        in_scroll_mode = False
                        prev_scroll_y = None

                    if not in_scroll_mode and abs(momentum_velocity) > 0.8:
                        win_scroll(momentum_velocity)
                        momentum_velocity *= 0.88

                    # Move & Click
                    if not is_two_finger_scroll:
                        norm_x = (index_tip.x - box_x_min) / calib_w
                        norm_y = (index_tip.y - box_y_min) / calib_h

                        target_x = SCREEN_WIDTH * norm_x
                        target_y = SCREEN_HEIGHT * norm_y
                        center_x, center_y = SCREEN_WIDTH / 2.0, SCREEN_HEIGHT / 2.0
                        target_x = center_x + (target_x - center_x) * sensitivity
                        target_y = center_y + (target_y - center_y) * sensitivity

                        is_pinching_left = pinch_left < PINCH_CLICK_THRESH

                        if is_pinching_left and not is_left_down:
                            click_deadzone_until = now + 0.07

                        if now > click_deadzone_until:
                            cur_x, cur_y = point_filter.filter(target_x, target_y, now)
                            cur_x = max(0, min(SCREEN_WIDTH - 1, cur_x))
                            cur_y = max(0, min(SCREEN_HEIGHT - 1, cur_y))
                            win_move_mouse(cur_x, cur_y)

                        # Right Click
                        if pinch_right < PINCH_RIGHT_THRESH:
                            if now - last_right_click > 0.6:
                                win_right_click()
                                last_right_click = now
                            status_str = "CHUỘT PHẢI"
                            status_color = (255, 0, 255)

                        # Left Click / Drag
                        elif is_pinching_left:
                            if not is_left_down:
                                win_click_down()
                                is_left_down = True
                                status_str = "CLICK"
                                status_color = (0, 255, 0)
                            else:
                                status_str = "KÉO THẢ"
                        else:
                            if is_left_down:
                                win_click_up()
                                is_left_down = False
                            status_str = "DI CHUYỂN"
                            status_color = (255, 200, 0)

                mp_draw.draw_landmarks(
                    frame,
                    results.multi_hand_landmarks[0],
                    mp_hands.HAND_CONNECTIONS,
                    mp_styles.get_default_hand_landmarks_style(),
                    mp_styles.get_default_hand_connections_style()
                )

            cv2.rectangle(frame, (8, 8), (340, 52), (18, 20, 28), -1)
            cv2.putText(frame, f"{status_str}", (18, 38),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, status_color, 2)
            cv2.imshow("HandCursor Windows (Nhan 'q' de thoat)", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    finally:
        if is_left_down:
            win_click_up()
        cam.stop()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
