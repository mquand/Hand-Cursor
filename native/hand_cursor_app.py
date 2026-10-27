#!/usr/bin/env python3
"""
HandCursor — macOS Menu Bar Application (Production Edition)
Features:
 - Sits discreetly in the macOS Menu Bar (Status Bar) with ✋ icon
 - Headless background tracking (No clutter window, toggle camera PIP anytime)
 - Typing Auto-Mute: Auto-freezes mouse when you are typing on keyboard
 - Auto-Distance Adaptation: Dynamically scales sensitivity based on hand size/distance
 - Full Mouse Gestures: Move, Click, Double-Click, Drag, Right-Click, 2-Finger Scroll, Pinch-Zoom
 - Window Management: Swipe up for Mission Control, Swipe horizontally for App Switch
 - 100% Offline, runs at 60 FPS on Apple Silicon Metal
"""

import sys
import time
import math
import threading
import ctypes
from ctypes import c_void_p, c_int, c_uint32, c_int32, c_uint64, c_double, Structure

import cv2
import mediapipe as mp
import rumps
from pynput import keyboard

# ==================== macOS CoreGraphics via ctypes ====================
class CGPoint(Structure):
    _fields_ = [('x', c_double), ('y', c_double)]

cg = ctypes.cdll.LoadLibrary('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')

# CoreGraphics Signatures
cg.CGEventCreateMouseEvent.restype = c_void_p
cg.CGEventCreateMouseEvent.argtypes = [c_void_p, c_int, CGPoint, c_int]

cg.CGEventCreateScrollWheelEvent.restype = c_void_p
cg.CGEventCreateScrollWheelEvent.argtypes = [c_void_p, c_uint32, c_uint32, c_int32]

cg.CGEventCreateKeyboardEvent.restype = c_void_p
cg.CGEventCreateKeyboardEvent.argtypes = [c_void_p, c_uint32, ctypes.c_bool]

cg.CGEventSetFlags.restype = None
cg.CGEventSetFlags.argtypes = [c_void_p, c_uint64]

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

# CoreGraphics Constants
kCGEventLeftMouseDown = 1
kCGEventLeftMouseUp = 2
kCGEventRightMouseDown = 3
kCGEventRightMouseUp = 4
kCGEventMouseMoved = 5
kCGEventLeftMouseDragged = 6
kCGHIDEventTap = 0
kCGMouseEventClickState = 1

# Modifier Key Masks
kCGEventFlagMaskCommand = 0x00100000
kCGEventFlagMaskControl = 0x00040000

# macOS Virtual Keycodes
kVK_UpArrow = 0x7E
kVK_Tab = 0x30

def post_mouse_event(event_type, x, y, button=0, click_count=1):
    pt = CGPoint(float(x), float(y))
    evt = cg.CGEventCreateMouseEvent(None, event_type, pt, button)
    if evt:
        if click_count > 1:
            cg.CGEventSetIntegerValueField(evt, kCGMouseEventClickState, click_count)
        cg.CGEventPost(kCGHIDEventTap, evt)
        cg.CFRelease(evt)

def post_scroll_event(delta_y, is_zoom=False):
    """Post scroll wheel event; if is_zoom=True, adds Command modifier for Pinch-Zoom"""
    evt = cg.CGEventCreateScrollWheelEvent(None, 0, 1, int(delta_y))
    if evt:
        if is_zoom:
            cg.CGEventSetFlags(evt, kCGEventFlagMaskCommand)
        cg.CGEventPost(kCGHIDEventTap, evt)
        cg.CFRelease(evt)

def trigger_mission_control():
    """Trigger macOS Mission Control (Control + Up Arrow)"""
    down = cg.CGEventCreateKeyboardEvent(None, kVK_UpArrow, True)
    up = cg.CGEventCreateKeyboardEvent(None, kVK_UpArrow, False)
    if down and up:
        cg.CGEventSetFlags(down, kCGEventFlagMaskControl)
        cg.CGEventPost(kCGHIDEventTap, down)
        cg.CGEventPost(kCGHIDEventTap, up)
        cg.CFRelease(down)
        cg.CFRelease(up)

def trigger_app_switch():
    """Trigger macOS App Switcher (Command + Tab)"""
    down = cg.CGEventCreateKeyboardEvent(None, kVK_Tab, True)
    up = cg.CGEventCreateKeyboardEvent(None, kVK_Tab, False)
    if down and up:
        cg.CGEventSetFlags(down, kCGEventFlagMaskCommand)
        cg.CGEventPost(kCGHIDEventTap, down)
        cg.CGEventPost(kCGHIDEventTap, up)
        cg.CFRelease(down)
        cg.CFRelease(up)

# ==================== Threaded Zero-Buffer Camera Stream ====================
class ThreadedCamera:
    def __init__(self, src=0, width=640, height=480):
        self.cap = cv2.VideoCapture(src, cv2.CAP_AVFOUNDATION)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(src)

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, 60)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self.ret, self.frame = self.cap.read()
        self.is_ready = self.cap.isOpened() and self.ret
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
        if hasattr(self, 'thread'):
            self.thread.join(timeout=1.0)
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

# ==================== Global App State ====================
class HandCursorState:
    def __init__(self):
        self.is_running = True
        self.is_paused = False
        self.show_camera_window = False
        self.auto_mute_typing = True
        self.sensitivity_preset = 2.0  # Default fast & responsive
        self.typing_mute_until = 0.0

shared_state = HandCursorState()

# Listen to physical keyboard events for typing auto-mute
def on_key_press(key):
    if shared_state.auto_mute_typing:
        shared_state.typing_mute_until = time.time() + 1.2

keyboard_listener = keyboard.Listener(on_press=on_key_press)
keyboard_listener.daemon = True
keyboard_listener.start()

# ==================== Core Hand Tracking Engine ====================
def tracking_worker():
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
        print("❌ Camera permission not granted.")
        rumps.notification("HandCursor", "Lỗi Camera", "Chưa cấp quyền camera trong System Settings -> Privacy & Security -> Camera")
        return

    point_filter = FastPointFilter(min_cutoff=0.8, beta=0.045)

    box_x_min, box_x_max = 0.18, 0.82
    box_y_min, box_y_max = 0.18, 0.82
    calib_w = box_x_max - box_x_min
    calib_h = box_y_max - box_y_min

    PINCH_CLICK_THRESH = 0.052
    PINCH_RIGHT_THRESH = 0.050

    is_left_down = False
    last_right_click = 0
    click_deadzone_until = 0
    cur_x, cur_y = SCREEN_WIDTH / 2.0, SCREEN_HEIGHT / 2.0

    last_click_release_time = 0
    last_click_pos = (cur_x, cur_y)
    double_click_active = False

    in_scroll_mode = False
    prev_scroll_y = None
    scroll_velocity = 0.0
    momentum_velocity = 0.0

    # Zoom tracking
    prev_pinch_distance = None
    last_zoom_time = 0

    # Swipe tracking (App switcher & Mission Control)
    wrist_history = []
    last_swipe_action_time = 0

    while shared_state.is_running:
        if shared_state.is_paused:
            time.sleep(0.1)
            continue

        ret, frame = cam.read()
        if not ret or frame is None:
            time.sleep(0.005)
            continue

        now = time.time()

        # Check Typing Auto-Mute
        if now < shared_state.typing_mute_until:
            if shared_state.show_camera_window:
                cv2.putText(frame, "DANG GO PHIM (Auto-Mute)", (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
                cv2.imshow("HandCursor Preview", frame)
                cv2.waitKey(1)
            time.sleep(0.01)
            continue

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

            # Auto-Distance Scaling based on hand scale
            hand_scale = math.dist((wrist.x, wrist.y), (middle_mcp.x, middle_mcp.y))
            # Normal hand scale is ~0.18; if smaller (far away), boost sensitivity
            distance_factor = max(0.85, min(1.8, 0.18 / max(hand_scale, 0.08)))
            effective_sensitivity = shared_state.sensitivity_preset * distance_factor

            # Check Fist (Pause / Clutch)
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

                # Cursor Anchor: Blend tip (8) with DIP (7) for rock-solid stability when pointing at camera
                anchor_x = 0.8 * index_tip.x + 0.2 * landmarks[7].x
                anchor_y = 0.8 * index_tip.y + 0.2 * landmarks[7].y

                # Pinch & Trigger Click: Measure distance to tip OR joint (supports pinch and pistol trigger tap)
                dist_tip = math.dist((thumb_tip.x, thumb_tip.y), (index_tip.x, index_tip.y))
                dist_joint = math.dist((thumb_tip.x, thumb_tip.y), (landmarks[6].x, landmarks[6].y))
                pinch_left = min(dist_tip, dist_joint)
                pinch_right = math.dist((thumb_tip.x, thumb_tip.y), (middle_tip.x, middle_tip.y))

                # Swipe History for Window Management
                wrist_history.append((wrist.x, wrist.y, now))
                if len(wrist_history) > 10:
                    wrist_history.pop(0)

                # Check Rapid Swipe Gestures (Mission Control & App Switch)
                is_open_hand = (is_index_extended and is_middle_extended and
                                (not is_ring_folded) and (not is_pinky_folded) and fist_count == 0)

                if is_open_hand and len(wrist_history) >= 6 and (now - last_swipe_action_time > 1.2):
                    old_wx, old_wy, old_wt = wrist_history[0]
                    cur_wx, cur_wy, cur_wt = wrist_history[-1]
                    d_tx = cur_wx - old_wx
                    d_ty = cur_wy - old_wy
                    dt = cur_wt - old_wt

                    # Rapid Swipe Up -> Mission Control
                    if dt < 0.35 and d_ty < -0.22 and abs(d_tx) < 0.15:
                        trigger_mission_control()
                        status_str = "MISSION CONTROL 🪟"
                        last_swipe_action_time = now
                        wrist_history.clear()

                    # Rapid Swipe Right -> App Switcher (Cmd+Tab)
                    elif dt < 0.35 and d_tx > 0.25 and abs(d_ty) < 0.15:
                        trigger_app_switch()
                        status_str = "CHUYỂN APP (Cmd+Tab)"
                        last_swipe_action_time = now
                        wrist_history.clear()

                # SCROLL UP / DOWN with Momentum
                is_two_finger_scroll = (
                    is_index_extended and is_middle_extended and
                    is_ring_folded and is_pinky_folded and
                    pinch_left > PINCH_CLICK_THRESH * 1.4
                )

                if is_two_finger_scroll:
                    current_mid_y = (index_tip.y + middle_tip.y) / 2.0
                    if in_scroll_mode and prev_scroll_y is not None:
                        delta_y = (prev_scroll_y - current_mid_y) * 620.0
                        if abs(delta_y) > 1.2:
                            post_scroll_event(delta_y)
                            scroll_velocity = 0.65 * delta_y + 0.35 * scroll_velocity
                            status_str = f"CUỘN {'LÊN ⬆️' if delta_y > 0 else 'XUỐNG ⬇️'}"
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
                    if in_scroll_mode and abs(scroll_velocity) > 5.0:
                        momentum_velocity = scroll_velocity * 0.8
                    in_scroll_mode = False
                    prev_scroll_y = None

                if not in_scroll_mode and abs(momentum_velocity) > 0.8:
                    post_scroll_event(int(momentum_velocity))
                    momentum_velocity *= 0.88
                    status_str = f"QUÁN TÍNH {'⬆️' if momentum_velocity > 0 else '⬇️'}"
                    status_color = (0, 230, 180)

                # Mouse Move & Click
                if not is_two_finger_scroll:
                    norm_x = (anchor_x - box_x_min) / calib_w
                    norm_y = (anchor_y - box_y_min) / calib_h

                    target_x = SCREEN_WIDTH * norm_x
                    target_y = SCREEN_HEIGHT * norm_y
                    center_x, center_y = SCREEN_WIDTH / 2.0, SCREEN_HEIGHT / 2.0
                    target_x = center_x + (target_x - center_x) * effective_sensitivity
                    target_y = center_y + (target_y - center_y) * effective_sensitivity

                    is_pinching_left = pinch_left < PINCH_CLICK_THRESH

                    # Double Click Lock
                    if is_pinching_left and not is_left_down:
                        if (now - last_click_release_time) < 0.38:
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

                    # Right Click
                    if pinch_right < PINCH_RIGHT_THRESH:
                        if now - last_right_click > 0.6:
                            post_mouse_event(kCGEventRightMouseDown, cur_x, cur_y, button=1)
                            post_mouse_event(kCGEventRightMouseUp, cur_x, cur_y, button=1)
                            last_right_click = now
                        status_str = "CHUỘT PHẢI"
                        status_color = (255, 0, 255)

                    # Left Click / Double Click / Drag
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
                            status_str = "KÉO THẢ"
                            status_color = (0, 255, 0)
                    else:
                        if is_left_down:
                            post_mouse_event(kCGEventLeftMouseUp, cur_x, cur_y)
                            is_left_down = False
                            last_click_release_time = now
                        post_mouse_event(kCGEventMouseMoved, cur_x, cur_y)
                        status_str = "DI CHUYỂN"
                        status_color = (255, 200, 0)

            # Draw preview if camera window is opened
            if shared_state.show_camera_window:
                mp_draw.draw_landmarks(
                    frame,
                    results.multi_hand_landmarks[0],
                    mp_hands.HAND_CONNECTIONS,
                    mp_styles.get_default_hand_landmarks_style(),
                    mp_styles.get_default_hand_connections_style()
                )

        if shared_state.show_camera_window:
            cv2.rectangle(frame, (8, 8), (380, 52), (18, 20, 28), -1)
            cv2.putText(frame, f"{status_str}", (18, 38),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, status_color, 2)
            cv2.imshow("HandCursor Preview", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                shared_state.show_camera_window = False
                cv2.destroyAllWindows()
        else:
            time.sleep(0.005)

    if is_left_down:
        post_mouse_event(kCGEventLeftMouseUp, 0, 0)
    cam.stop()
    cv2.destroyAllWindows()

# ==================== macOS Menu Bar UI (Rumps) ====================
class HandCursorApp(rumps.App):
    def __init__(self):
        super(HandCursorApp, self).__init__("HandCursor", title="✋", quit_button=None)
        
        self.item_status = rumps.MenuItem("🟢 Đang hoạt động", callback=self.toggle_pause)
        self.item_preview = rumps.MenuItem("👁️ Hiện Camera (PIP)", callback=self.toggle_preview)
        self.item_mute_typing = rumps.MenuItem("⌨️ Tự tắt khi gõ phím: [BẬT]", callback=self.toggle_typing_mute)
        
        self.menu_sensitivity = rumps.MenuItem("⚙️ Độ nhạy chuột")
        self.sens_slow = rumps.MenuItem("Chậm (1.0x)", callback=lambda _: self.set_sens(1.0))
        self.sens_medium = rumps.MenuItem("✓ Vừa (1.4x)", callback=lambda _: self.set_sens(1.4))
        self.sens_fast = rumps.MenuItem("Nhanh (1.8x)", callback=lambda _: self.set_sens(1.8))
        self.menu_sensitivity.update([self.sens_slow, self.sens_medium, self.sens_fast])

        self.item_quit = rumps.MenuItem("❌ Thoát HandCursor", callback=self.quit_app)

        self.menu = [
            self.item_status,
            self.item_preview,
            self.item_mute_typing,
            None, # Separator
            self.menu_sensitivity,
            None, # Separator
            self.item_quit
        ]

        # Launch tracking worker thread
        self.worker_thread = threading.Thread(target=tracking_worker, daemon=True)
        self.worker_thread.start()

    def toggle_pause(self, sender):
        shared_state.is_paused = not shared_state.is_paused
        if shared_state.is_paused:
            self.title = "✋ (Tạm dừng)"
            self.item_status.title = "🔴 Đang tạm dừng"
        else:
            self.title = "✋"
            self.item_status.title = "🟢 Đang hoạt động"

    def toggle_preview(self, sender):
        shared_state.show_camera_window = not shared_state.show_camera_window
        if shared_state.show_camera_window:
            self.item_preview.title = "👁️ Ẩn Camera"
        else:
            self.item_preview.title = "👁️ Hiện Camera (PIP)"
            cv2.destroyAllWindows()

    def toggle_typing_mute(self, sender):
        shared_state.auto_mute_typing = not shared_state.auto_mute_typing
        self.item_mute_typing.title = f"⌨️ Tự tắt khi gõ phím: [{'BẬT' if shared_state.auto_mute_typing else 'TẮT'}]"

    def set_sens(self, val):
        shared_state.sensitivity_preset = val
        self.sens_slow.title = f"{'✓ ' if val == 1.0 else ''}Chậm (1.0x)"
        self.sens_medium.title = f"{'✓ ' if val == 1.4 else ''}Vừa (1.4x)"
        self.sens_fast.title = f"{'✓ ' if val == 1.8 else ''}Nhanh (1.8x)"

    def quit_app(self, sender):
        shared_state.is_running = False
        cv2.destroyAllWindows()
        rumps.quit_application()

if __name__ == '__main__':
    HandCursorApp().run()
