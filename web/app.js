import { Point2DFilter } from './one_euro_filter.js';

/**
 * HandCursor — Core Web Controller & Gesture Recognizer
 */

// Application State
const state = {
  isCameraActive: false,
  isScreenGlowActive: false,
  handDetected: false,
  fps: 0,
  lastFrameTime: performance.now(),
  frameCount: 0,
  
  // Cursor & Physics
  cursorX: window.innerWidth / 2,
  cursorY: window.innerHeight / 2,
  isPinching: false,
  isMiddlePinching: false,
  isFist: false,
  isDragging: false,
  dragTarget: null,
  dragOffset: { x: 0, y: 0 },
  
  // Pinch Timing & Deadzone
  pinchStartTime: 0,
  pinchHoldTimer: null,
  clickDeadzoneUntil: 0,
  lastClickTime: 0,

  // Calibration Box (Normalized webcam coordinates mapped to viewport)
  calib: {
    minX: 0.25,
    maxX: 0.75,
    minY: 0.25,
    maxY: 0.75,
    step: 0,
    active: false
  },

  // Swipe Gesture Tracking
  palmHistory: [],

  // Settings
  sensitivity: 1.8,
  pinchThreshold: 0.055,
  drawLandmarks: true
};

// Filter instances: minCutoff=0.4 (smooth jitter), beta=0.02 (less lag, more stability)
const cursorFilter = new Point2DFilter(0.4, 0.02);

// DOM Elements
const videoEl = document.getElementById('webcam-video');
const canvasEl = document.getElementById('landmarks-canvas');
const ctx = canvasEl.getContext('2d');
const cursorEl = document.getElementById('virtual-cursor');
const btnToggleCam = document.getElementById('btn-toggle-cam');
const btnCamText = document.getElementById('btn-cam-text');
const btnScreenGlow = document.getElementById('btn-screen-glow');
const btnCalibrate = document.getElementById('btn-calibrate');
const camPlaceholder = document.getElementById('cam-placeholder');
const camStatusDot = document.getElementById('cam-status-dot');
const handCountBadge = document.getElementById('hand-count-badge');
const gestureBadge = document.getElementById('gesture-badge');
const fpsVal = document.getElementById('fps-val');
const luxVal = document.getElementById('lux-val');
const pinchDistVal = document.getElementById('pinch-dist-val');
const pinchMeterFill = document.getElementById('pinch-meter-fill');
const pinchPercentText = document.getElementById('pinch-percent-text');

// Sliders
const rngSensitivity = document.getElementById('rng-sensitivity');
const rngSmoothing = document.getElementById('rng-smoothing');
const rngPinchThresh = document.getElementById('rng-pinch-thresh');
const lblSensitivity = document.getElementById('lbl-sensitivity');
const lblSmoothing = document.getElementById('lbl-smoothing');
const lblPinchThresh = document.getElementById('lbl-pinch-thresh');
const chkDrawMesh = document.getElementById('chk-draw-mesh');

// Calibration Save Buttons
const btnSaveCalib = document.getElementById('btn-save-calib');
const btnResetCalib = document.getElementById('btn-reset-calib');
const calibStatusText = document.getElementById('calib-status-text');

// Interactive Playground Elements
const tabBtns = document.querySelectorAll('.tab-btn');
const tabContents = document.querySelectorAll('.tab-content');
const testBtnCounter = document.getElementById('test-btn-counter');
const clickCounterVal = document.getElementById('click-counter-val');
const testBtnDblClick = document.getElementById('test-btn-dblclick');
const dblClickState = document.getElementById('dblclick-state');
const contextZone = document.getElementById('context-zone');
const contextPopup = document.getElementById('context-popup');

// Whiteboard
const drawingCanvas = document.getElementById('drawing-canvas');
const drawCtx = drawingCanvas.getContext('2d');
let isDrawing = false;
let lastDrawPoint = null;
let currentColor = '#38bdf8';

// Slide Deck
const slidesData = [
  { title: "Chào mừng đến với HandCursor", body: "Công nghệ điều khiển máy tính thế hệ mới bằng cử chỉ tay không chạm. 100% xử lý offline, bảo mật tuyệt đối." },
  { title: "Khắc phục triệt để rung tay", body: "Tích hợp thuật toán One-Euro Filter và cơ chế Click Deadzone giúp trỏ chuột di chuyển mượt mà, bấm không bị trượt." },
  { title: "Điều khiển không giới hạn", body: "Hoàn hảo cho thuyết trình, y tế, nhà bếp, người run tay, hoặc đơn giản khi bạn để quên chuột máy tính." },
  { title: "Tự thích nghi thông minh", body: "Tự động kích hoạt bù sáng viền màn hình khi phòng tối, học thói quen người dùng với bộ cân chỉnh 10 giây." }
];
let currentSlideIndex = 0;
const slideTitleEl = document.getElementById('current-slide-title');
const slideBodyEl = document.getElementById('current-slide-body');
const slideNumEl = document.getElementById('current-slide-num');

// MediaPipe Hands & Camera Instances
let hands = null;
let camera = null;
let clickCount = 0;

// Setup Drawing Canvas Resizing
function resizeDrawingCanvas() {
  if (drawingCanvas) {
    const rect = drawingCanvas.getBoundingClientRect();
    drawingCanvas.width = rect.width;
    drawingCanvas.height = rect.height;
    drawCtx.lineCap = 'round';
    drawCtx.lineJoin = 'round';
    drawCtx.lineWidth = 4;
  }
}
window.addEventListener('resize', resizeDrawingCanvas);
setTimeout(resizeDrawingCanvas, 300);

// Initialize MediaPipe Hands
function initMediaPipe() {
  if (typeof window.Hands === 'undefined') {
    console.error('MediaPipe Hands is not loaded from CDN yet.');
    return;
  }

  hands = new window.Hands({
    locateFile: (file) => `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${file}`
  });

  hands.setOptions({
    maxNumHands: 1,
    modelComplexity: 0,
    minDetectionConfidence: 0.6,
    minTrackingConfidence: 0.6
  });

  hands.onResults(onHandResults);
}

// Calculate Euclidean distance between two 3D landmarks
function dist(p1, p2) {
  const dx = p1.x - p2.x;
  const dy = p1.y - p2.y;
  const dz = (p1.z || 0) - (p2.z || 0);
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

// Detect Fist gesture (all fingertips folded towards base)
function checkFist(landmarks) {
  const wrist = landmarks[0];
  const tips = [8, 12, 16, 20];
  const mcps = [5, 9, 13, 17];
  
  let foldedCount = 0;
  for (let i = 0; i < 4; i++) {
    const dTip = dist(landmarks[tips[i]], wrist);
    const dMcp = dist(landmarks[mcps[i]], wrist);
    if (dTip < dMcp * 1.15) {
      foldedCount++;
    }
  }
  return foldedCount >= 3;
}

// Calculate average brightness of camera frame
function checkLuminance(video) {
  try {
    const sampleCanvas = document.createElement('canvas');
    sampleCanvas.width = 40;
    sampleCanvas.height = 30;
    const sCtx = sampleCanvas.getContext('2d');
    sCtx.drawImage(video, 0, 0, 40, 30);
    const imgData = sCtx.getImageData(0, 0, 40, 30).data;
    let sum = 0;
    for (let i = 0; i < imgData.length; i += 4) {
      sum += 0.299 * imgData[i] + 0.587 * imgData[i + 1] + 0.114 * imgData[i + 2];
    }
    const avg = Math.round(sum / (imgData.length / 4));
    luxVal.textContent = `${avg} lux`;

    // Auto-suggest screen glow if dark (< 45 lux)
    if (avg < 45 && !state.isScreenGlowActive) {
      btnScreenGlow.classList.add('glow-active');
    }
  } catch (e) {
    // Canvas security/frame not ready
  }
}

// Hand Tracking Results Callback
function onHandResults(results) {
  updateFPS();

  // Resize landmarks canvas to match video
  canvasEl.width = videoEl.videoWidth || 640;
  canvasEl.height = videoEl.videoHeight || 480;
  ctx.clearRect(0, 0, canvasEl.width, canvasEl.height);

  if (!results.multiHandLandmarks || results.multiHandLandmarks.length === 0) {
    state.handDetected = false;
    handCountBadge.style.display = 'none';
    gestureBadge.textContent = 'Tìm tay...';
    gestureBadge.className = 'gesture-name-badge';
    pinchMeterFill.style.width = '0%';
    pinchPercentText.textContent = '0%';
    pinchDistVal.textContent = '--';
    cursorEl.style.opacity = '0.35';
    return;
  }

  state.handDetected = true;
  handCountBadge.style.display = 'flex';
  cursorEl.style.opacity = '1';

  const landmarks = results.multiHandLandmarks[0];

  // Draw Skeleton Landmarks if enabled
  if (state.drawLandmarks && window.drawConnectors && window.drawLandmarks) {
    window.drawConnectors(ctx, landmarks, window.HAND_CONNECTIONS, { color: 'rgba(56, 189, 248, 0.45)', lineWidth: 3 });
    window.drawLandmarks(ctx, landmarks, { color: '#a855f7', lineWidth: 1, radius: 3 });
  }

  // Key Landmarks:
  const thumbTip = landmarks[4];
  const indexTip = landmarks[8];
  const middleTip = landmarks[12];
  const wrist = landmarks[0];

  // 1. Check Fist (Tạm dừng)
  const isFist = checkFist(landmarks);
  state.isFist = isFist;

  if (isFist) {
    gestureBadge.textContent = 'Nắm đấm (Tạm dừng)';
    gestureBadge.className = 'gesture-name-badge fist';
    cursorEl.className = 'paused';
    return;
  }

  // 2. Pinch Distances
  const pinchDist = dist(thumbTip, indexTip);
  const middlePinchDist = dist(thumbTip, middleTip);

  pinchDistVal.textContent = pinchDist.toFixed(3);
  const pinchPercent = Math.min(Math.max(Math.round((1 - pinchDist / (state.pinchThreshold * 2.2)) * 100), 0), 100);
  pinchMeterFill.style.width = `${pinchPercent}%`;
  pinchPercentText.textContent = `${pinchPercent}%`;

  const isIndexPinching = pinchDist < state.pinchThreshold;
  const isMiddlePinching = middlePinchDist < (state.pinchThreshold * 0.95);

  // 3. Coordinate Normalization & Mapping with Calibration Box
  // Note: Video is mirrored horizontally, so normalized x is inverted: (1 - indexTip.x)
  const rawNormX = 1 - indexTip.x;
  const rawNormY = indexTip.y;

  const calibW = Math.max(state.calib.maxX - state.calib.minX, 0.1);
  const calibH = Math.max(state.calib.maxY - state.calib.minY, 0.1);

  // Map calibrated coordinates to screen space
  let screenTargetX = ((rawNormX - state.calib.minX) / calibW) * window.innerWidth;
  let screenTargetY = ((rawNormY - state.calib.minY) / calibH) * window.innerHeight;

  // Apply Sensitivity
  const centerX = window.innerWidth / 2;
  const centerY = window.innerHeight / 2;
  screenTargetX = centerX + (screenTargetX - centerX) * state.sensitivity;
  screenTargetY = centerY + (screenTargetY - centerY) * state.sensitivity;

  // Clamp to window boundaries
  screenTargetX = Math.max(0, Math.min(window.innerWidth, screenTargetX));
  screenTargetY = Math.max(0, Math.min(window.innerHeight, screenTargetY));

  // Apply One-Euro Filter
  const now = performance.now();
  
  // Deadzone logic: When starting pinch, freeze coordinate for 70ms to avoid click slip
  if (isIndexPinching && !state.isPinching) {
    state.clickDeadzoneUntil = now + 70;
  }

  if (now > state.clickDeadzoneUntil) {
    const smoothed = cursorFilter.filter(screenTargetX, screenTargetY, now);
    state.cursorX = smoothed.x;
    state.cursorY = smoothed.y;
  }

  // Update DOM Cursor Position
  cursorEl.style.transform = `translate3d(${state.cursorX}px, ${state.cursorY}px, 0)`;

  // Check Two-Finger Scroll Gesture (Index + Middle extended, others folded)
  const ringTip = landmarks[16];
  const pinkyTip = landmarks[20];
  const indexMcp = landmarks[5];
  const middleMcp = landmarks[9];
  const ringMcp = landmarks[13];
  const pinkyMcp = landmarks[17];

  const isIndexExt = dist(indexTip, wrist) > dist(indexMcp, wrist) * 1.2;
  const isMiddleExt = dist(middleTip, wrist) > dist(middleMcp, wrist) * 1.2;
  const isRingFold = dist(ringTip, wrist) < dist(ringMcp, wrist) * 1.25;
  const isPinkyFold = dist(pinkyTip, wrist) < dist(pinkyMcp, wrist) * 1.25;

  const isTwoFingerScroll = isIndexExt && isMiddleExt && isRingFold && isPinkyFold && (pinchDist > state.pinchThreshold * 1.4);
  const isOpenHandFlick = isIndexExt && isMiddleExt && !isRingFold && !isPinkyFold && !state.isFist && (pinchDist > state.pinchThreshold * 1.5);
  const isScrollingNow = isTwoFingerScroll || isOpenHandFlick;

  if (isScrollingNow) {
    const currentMidY = (indexTip.y + middleTip.y) / 2.0;
    if (state.inScrollMode && state.prevScrollY !== null) {
      const deltaY = (state.prevScrollY - currentMidY) * window.innerHeight * 2.5;
      if (Math.abs(deltaY) > 2) {
        window.scrollBy({ top: -deltaY, behavior: 'auto' });
        state.scrollVelocity = 0.65 * deltaY + 0.35 * (state.scrollVelocity || 0);
        gestureBadge.textContent = deltaY < 0 ? 'Vuốt Xuống ⬇️' : 'Vuốt Lên ⬆️';
        gestureBadge.className = 'gesture-name-badge';
      }
    } else {
      state.inScrollMode = true;
      state.scrollVelocity = 0;
      gestureBadge.textContent = 'Cuộn trang (2 Ngón)';
      gestureBadge.className = 'gesture-name-badge';
    }
    state.prevScrollY = currentMidY;
    cursorEl.className = 'paused';
    return;
  } else {
    // When finishing a flick gesture: trigger momentum glide
    if (state.inScrollMode && Math.abs(state.scrollVelocity) > 5) {
      state.momentumVelocity = state.scrollVelocity * 0.85;
    }
    state.inScrollMode = false;
    state.prevScrollY = null;
  }

  // Momentum coasting loop
  if (!isScrollingNow && Math.abs(state.momentumVelocity) > 0.8) {
    window.scrollBy({ top: -state.momentumVelocity, behavior: 'auto' });
    state.momentumVelocity *= 0.88; // Friction damping like iPhone
    gestureBadge.textContent = `Trượt quán tính ${state.momentumVelocity > 0 ? '⬆️' : '⬇️'}`;
  }

  // 4. Gesture State Machine:
  if (isMiddlePinching) {
    // Chuột phải (Pinch ngón cái + ngón giữa)
    handleRightClick(state.cursorX, state.cursorY);
    gestureBadge.textContent = 'Chuột phải';
    gestureBadge.className = 'gesture-name-badge';
    cursorEl.className = 'right-clicking';
  } else if (isIndexPinching) {
    if (!state.isPinching) {
      // Just started pinching (MouseDown)
      state.isPinching = true;
      state.pinchStartTime = now;
      handlePinchStart(state.cursorX, state.cursorY);
    } else {
      // Sustained pinch (Dragging / Holding)
      handlePinchHold(state.cursorX, state.cursorY, now);
    }
  } else {
    if (state.isPinching) {
      // Released pinch (MouseUp)
      handlePinchEnd(state.cursorX, state.cursorY);
      state.isPinching = false;
    } else {
      // Free hover / pointing
      gestureBadge.textContent = 'Dáng trỏ (Di chuyển)';
      gestureBadge.className = 'gesture-name-badge pointing';
      cursorEl.className = '';
    }
  }

  // 5. Swipe Detection (Horizontal Hand Swipe)
  trackSwipeGesture(wrist.x, now);
}

// Track Swipe for Slide Changing
function trackSwipeGesture(wristX, now) {
  state.palmHistory.push({ x: wristX, t: now });
  if (state.palmHistory.length > 10) state.palmHistory.shift();

  if (state.palmHistory.length >= 6) {
    const oldest = state.palmHistory[0];
    const newest = state.palmHistory[state.palmHistory.length - 1];
    const dt = newest.t - oldest.t;
    const dx = newest.x - oldest.x;

    // Check rapid horizontal velocity
    if (dt > 100 && dt < 450 && Math.abs(dx) > 0.22) {
      if (dx > 0) {
        // Swiped right
        triggerSwipe('right');
      } else {
        // Swiped left
        triggerSwipe('left');
      }
      state.palmHistory = [];
    }
  }
}

let lastSwipeTime = 0;
function triggerSwipe(direction) {
  const now = performance.now();
  if (now - lastSwipeTime < 800) return; // Debounce
  lastSwipeTime = now;

  gestureBadge.textContent = `Vuốt ${direction === 'left' ? 'Trái' : 'Phải'}`;
  gestureBadge.className = 'gesture-name-badge';

  if (direction === 'left') {
    nextSlide();
  } else {
    prevSlide();
  }
}

// Interaction Handlers (Pinch / Click / Drag / Whiteboard)
function handlePinchStart(x, y) {
  const target = document.elementFromPoint(x, y);

  // If in Whiteboard Tab, begin drawing
  const drawingTab = document.getElementById('tab-drawing');
  if (drawingTab && drawingTab.classList.contains('active')) {
    const rect = drawingCanvas.getBoundingClientRect();
    if (x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom) {
      isDrawing = true;
      lastDrawPoint = { x: x - rect.left, y: y - rect.top };
      drawCtx.strokeStyle = currentColor;
      drawCtx.beginPath();
      drawCtx.arc(lastDrawPoint.x, lastDrawPoint.y, 2, 0, Math.PI * 2);
      drawCtx.fill();
    }
  }

  // Check if target is a draggable card
  const chip = target ? target.closest('.draggable-chip') : null;
  if (chip) {
    state.isDragging = true;
    state.dragTarget = chip;
    chip.classList.add('dragging');
  }

  cursorEl.className = 'clicking';
}

function handlePinchHold(x, y, now) {
  // If dragging a Kanban card
  if (state.isDragging && state.dragTarget) {
    gestureBadge.textContent = 'Kéo thả (Dragging)';
    gestureBadge.className = 'gesture-name-badge dragging';
    cursorEl.className = 'dragging';

    // Highlight container beneath cursor
    const elUnder = document.elementFromPoint(x, y);
    const container = elUnder ? elUnder.closest('.kanban-items-container') : null;
    document.querySelectorAll('.kanban-items-container').forEach(c => c.classList.remove('drag-over'));
    if (container) {
      container.classList.add('drag-over');
    }
    return;
  }

  // If drawing on whiteboard
  if (isDrawing && lastDrawPoint) {
    const rect = drawingCanvas.getBoundingClientRect();
    const curX = x - rect.left;
    const curY = y - rect.top;

    drawCtx.beginPath();
    drawCtx.moveTo(lastDrawPoint.x, lastDrawPoint.y);
    drawCtx.lineTo(curX, curY);
    drawCtx.stroke();
    lastDrawPoint = { x: curX, y: curY };

    gestureBadge.textContent = 'Vẽ bảng (Drawing)';
    gestureBadge.className = 'gesture-name-badge clicking';
    return;
  }

  // If stationary for > 500ms, trigger Right-Click (Alt method)
  if (now - state.pinchStartTime > 550 && !state.dragTarget && !isDrawing) {
    handleRightClick(x, y);
  }
}

function handlePinchEnd(x, y) {
  cursorEl.className = '';

  // Finish Whiteboard Drawing
  if (isDrawing) {
    isDrawing = false;
    lastDrawPoint = null;
  }

  // Finish Kanban Drag & Drop
  if (state.isDragging && state.dragTarget) {
    const elUnder = document.elementFromPoint(x, y);
    const container = elUnder ? elUnder.closest('.kanban-items-container') : null;
    document.querySelectorAll('.kanban-items-container').forEach(c => c.classList.remove('drag-over'));

    if (container && container !== state.dragTarget.parentElement) {
      container.appendChild(state.dragTarget);
      updateKanbanCounts();
    }
    state.dragTarget.classList.remove('dragging');
    state.dragTarget = null;
    state.isDragging = false;
    return;
  }

  // Perform Standard Click on element under cursor
  const target = document.elementFromPoint(x, y);
  if (target) {
    // Avoid double clicking on background
    const clickable = target.closest('button, .tab-btn, .color-dot, .test-target-btn, .context-menu-item, [role="tab"]');
    if (clickable) {
      clickable.click();
      clickable.classList.add('clicked');
      setTimeout(() => clickable.classList.remove('clicked'), 350);
    }
  }
}

// Right Click Action
let lastRightClickTime = 0;
function handleRightClick(x, y) {
  const now = performance.now();
  if (now - lastRightClickTime < 1000) return; // Debounce
  lastRightClickTime = now;

  const target = document.elementFromPoint(x, y);
  const contextArea = target ? target.closest('#context-zone') : null;
  if (contextArea && contextPopup) {
    contextPopup.classList.toggle('show');
  }
}

// Kanban Pill Counter Update
function updateKanbanCounts() {
  document.querySelectorAll('.kanban-col').forEach(col => {
    const count = col.querySelectorAll('.draggable-chip').length;
    const pill = col.querySelector('.count-pill');
    if (pill) pill.textContent = count;
  });
}

// Camera Lifecycle
async function startCamera() {
  initMediaPipe();

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: {
        width: { ideal: 640 },
        height: { ideal: 480 },
        facingMode: 'user'
      }
    });
    videoEl.srcObject = stream;
    await videoEl.play();

    state.isCameraActive = true;
    camPlaceholder.style.display = 'none';
    camStatusDot.classList.add('active');
    btnCamText.textContent = 'Tắt Camera';
    btnToggleCam.classList.remove('primary');

    // Run frame loop
    requestAnimationFrame(processVideoFrame);
  } catch (err) {
    console.error('Camera access error:', err);
    alert('Không thể mở Webcam: Hãy chắc chắn bạn đã cấp quyền sử dụng camera trong trình duyệt.');
  }
}

function stopCamera() {
  if (videoEl.srcObject) {
    videoEl.srcObject.getTracks().forEach(track => track.stop());
    videoEl.srcObject = null;
  }
  state.isCameraActive = false;
  camPlaceholder.style.display = 'flex';
  camStatusDot.classList.remove('active');
  btnCamText.textContent = 'Bật Camera';
  btnToggleCam.classList.add('primary');
  ctx.clearRect(0, 0, canvasEl.width, canvasEl.height);
}

// Frame Processing Loop
let lastLuxCheck = 0;
async function processVideoFrame() {
  if (!state.isCameraActive) return;

  if (videoEl.readyState >= 2 && hands) {
    await hands.send({ image: videoEl });

    // Periodic brightness check every 1.5s
    const now = performance.now();
    if (now - lastLuxCheck > 1500) {
      checkLuminance(videoEl);
      lastLuxCheck = now;
    }
  }

  requestAnimationFrame(processVideoFrame);
}

// FPS Counter
function updateFPS() {
  state.frameCount++;
  const now = performance.now();
  if (now - state.lastFrameTime >= 1000) {
    state.fps = state.frameCount;
    fpsVal.textContent = state.fps;
    state.frameCount = 0;
    state.lastFrameTime = now;
  }
}

// Slides Deck Controllers
function updateSlideView() {
  const current = slidesData[currentSlideIndex];
  slideTitleEl.textContent = current.title;
  slideBodyEl.textContent = current.body;
  slideNumEl.textContent = currentSlideIndex + 1;
}

function nextSlide() {
  currentSlideIndex = (currentSlideIndex + 1) % slidesData.length;
  updateSlideView();
}

function prevSlide() {
  currentSlideIndex = (currentSlideIndex - 1 + slidesData.length) % slidesData.length;
  updateSlideView();
}

// Calibration Modal Wizard (Chạm 4 góc)
const calibModal = document.getElementById('calibration-modal');
const calibStepText = document.getElementById('calibration-step-text');
const btnStartCalib = document.getElementById('btn-start-calib-step');
const btnCloseCalib = document.getElementById('btn-close-calib');
const targets = [
  document.getElementById('target-tl'),
  document.getElementById('target-tr'),
  document.getElementById('target-br'),
  document.getElementById('target-bl')
];
let currentCalibIdx = 0;

function startCalibration() {
  calibModal.classList.add('show');
  currentCalibIdx = 0;
  targets.forEach(t => t.style.display = 'none');
}

function runNextCalibStep() {
  targets.forEach(t => t.style.display = 'none');
  if (currentCalibIdx >= targets.length) {
    calibStepText.textContent = "Hoàn tất hiệu chỉnh! Vùng tay đã được tối ưu.";
    setTimeout(() => {
      calibModal.classList.remove('show');
      targets.forEach(t => t.style.display = 'none');
    }, 1500);
    return;
  }

  const target = targets[currentCalibIdx];
  target.style.display = 'flex';
  calibStepText.textContent = `Chạm góc ${currentCalibIdx + 1} / 4`;
  currentCalibIdx++;
}

// Event Listeners Initialization
function setupEventListeners() {
  // Camera Toggle
  btnToggleCam.addEventListener('click', () => {
    if (state.isCameraActive) {
      stopCamera();
    } else {
      startCamera();
    }
  });

  // Screen Edge Illumination Toggle
  btnScreenGlow.addEventListener('click', () => {
    state.isScreenGlowActive = !state.isScreenGlowActive;
    document.body.classList.toggle('screen-glow-active', state.isScreenGlowActive);
    btnScreenGlow.classList.toggle('glow-active', state.isScreenGlowActive);
  });

  // Calibration Buttons
  btnCalibrate.addEventListener('click', startCalibration);
  btnStartCalib.addEventListener('click', runNextCalibStep);
  btnCloseCalib.addEventListener('click', () => {
    calibModal.classList.remove('show');
    targets.forEach(t => t.style.display = 'none');
  });

  // Tuning Sliders
  rngSensitivity.addEventListener('input', (e) => {
    state.sensitivity = parseFloat(e.target.value);
    lblSensitivity.textContent = `${state.sensitivity.toFixed(1)}x`;
  });

  rngSmoothing.addEventListener('input', (e) => {
    const val = parseFloat(e.target.value);
    cursorFilter.setParams(1.0, val);
    lblSmoothing.textContent = val < 0.005 ? 'Rất mượt' : val > 0.02 ? 'Nhanh' : 'Cân bằng';
  });

  rngPinchThresh.addEventListener('input', (e) => {
    state.pinchThreshold = parseFloat(e.target.value);
    lblPinchThresh.textContent = state.pinchThreshold.toFixed(3);
  });

  chkDrawMesh.addEventListener('change', (e) => {
    state.drawLandmarks = e.target.checked;
  });

  // Tabs Switching
  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      tabBtns.forEach(b => {
        b.classList.remove('active');
        b.setAttribute('aria-selected', 'false');
      });
      tabContents.forEach(c => c.classList.remove('active'));

      btn.classList.add('active');
      btn.setAttribute('aria-selected', 'true');
      const targetTab = document.getElementById(btn.getAttribute('data-tab'));
      if (targetTab) {
        targetTab.classList.add('active');
        if (btn.getAttribute('data-tab') === 'tab-drawing') {
          resizeDrawingCanvas();
        }
      }
    });
  });

  // Test Buttons
  testBtnCounter.addEventListener('click', () => {
    clickCount++;
    clickCounterVal.textContent = clickCount;
  });

  testBtnDblClick.addEventListener('dblclick', () => {
    dblClickState.textContent = 'Thành công (Double Clicked!)';
    testBtnDblClick.style.background = 'var(--accent-purple)';
    setTimeout(() => {
      dblClickState.textContent = 'Chưa kích hoạt';
      testBtnDblClick.style.background = '';
    }, 2000);
  });

  // Whiteboard Colors & Clear
  document.querySelectorAll('.color-dot').forEach(dot => {
    dot.addEventListener('click', () => {
      document.querySelectorAll('.color-dot').forEach(d => d.classList.remove('active'));
      dot.classList.add('active');
      currentColor = dot.getAttribute('data-color');
    });
  });

  document.getElementById('btn-clear-canvas')?.addEventListener('click', () => {
    drawCtx.clearRect(0, 0, drawingCanvas.width, drawingCanvas.height);
  });

  // Slide Deck Buttons
  document.getElementById('btn-slide-next')?.addEventListener('click', nextSlide);
  document.getElementById('btn-slide-prev')?.addEventListener('click', prevSlide);
}

// Start
setupEventListeners();
updateSlideView();

// Load saved calibration from localStorage on startup
function loadSavedCalibration() {
  try {
    const saved = localStorage.getItem('handcursor_calibration');
    if (saved) {
      const config = JSON.parse(saved);
      if (config.calib && config.sensitivity !== undefined) {
        state.calib = config.calib;
        state.sensitivity = config.sensitivity;
        state.pinchThreshold = config.pinchThreshold || 0.055;

        // Update UI
        rngSensitivity.value = state.sensitivity;
        lblSensitivity.textContent = `${state.sensitivity.toFixed(1)}x`;
        rngPinchThresh.value = state.pinchThreshold;
        lblPinchThresh.textContent = state.pinchThreshold.toFixed(3);

        calibStatusText.textContent = 'Đã tải cấu hình đã lưu';
        calibStatusText.style.color = 'var(--accent-green)';
      }
    }
  } catch (e) {
    console.error('Failed to load calibration:', e);
  }
}

// Save current calibration to localStorage
function saveCalibration() {
  try {
    const config = {
      calib: state.calib,
      sensitivity: state.sensitivity,
      pinchThreshold: state.pinchThreshold
    };
    localStorage.setItem('handcursor_calibration', JSON.stringify(config));
    calibStatusText.textContent = 'Đã lưu cấu hình ✓';
    calibStatusText.style.color = 'var(--accent-green)';
  } catch (e) {
    console.error('Failed to save calibration:', e);
    calibStatusText.textContent = 'Lỗi khi lưu';
    calibStatusText.style.color = 'var(--accent-red)';
  }
}

// Reset calibration to defaults
function resetCalibration() {
  state.calib = {
    minX: 0.25,
    maxX: 0.75,
    minY: 0.25,
    maxY: 0.75,
    step: 0,
    active: false
  };
  state.sensitivity = 1.8;
  state.pinchThreshold = 0.055;

  // Update UI
  rngSensitivity.value = state.sensitivity;
  lblSensitivity.textContent = `${state.sensitivity.toFixed(1)}x`;
  rngPinchThresh.value = state.pinchThreshold;
  lblPinchThresh.textContent = state.pinchThreshold.toFixed(3);

  // Clear localStorage
  localStorage.removeItem('handcursor_calibration');
  calibStatusText.textContent = 'Đã reset về mặc định';
  calibStatusText.style.color = 'var(--text-dim)';
}

// Add calibration save/reset event listeners
if (btnSaveCalib) {
  btnSaveCalib.addEventListener('click', saveCalibration);
}
if (btnResetCalib) {
  btnResetCalib.addEventListener('click', resetCalibration);
}

// Load saved calibration on startup
loadSavedCalibration();
