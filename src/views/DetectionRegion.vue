<template>
  <div class="settings-page detection-region-page">
    <div class="settings-container detection-region-container">
      <div class="settings-header">
        <div>
          <h2 class="settings-title">检测区域设置</h2>
          <p class="settings-subtitle">
            鼠标拖拽框选区域，最多 3 个，编号固定为 1 / 2 / 3，并按最小空闲编号优先分配。
          </p>
        </div>
        <button class="close-btn" @click="goBack" :disabled="isSaving">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      </div>

      <div class="settings-form detection-region-layout" :class="{ 'form-loading': isSaving }">
        <div class="canvas-panel">
          <div class="panel-toolbar">
            <span>{{ `原视频分辨率：${sourceResolution.width} x ${sourceResolution.height}` }}</span>
            <div class="toolbar-actions">
              <span class="toolbar-label">作用域：</span>
              <select v-model="selectedTarget" class="target-select" :disabled="isSaving">
                <option value="all">所有分支</option>
                <option value="high">高分辨率分支</option>
                <option value="low">低分辨率分支</option>
              </select>
            </div>
          </div>

          <div class="canvas-frame">
            <video
              ref="frameVideoRef"
              class="frame-video"
              autoplay
              muted
              playsinline
            ></video>
            <canvas
              ref="canvasRef"
              :width="CANVAS_WIDTH"
              :height="CANVAS_HEIGHT"
              @mousedown="beginDraw"
              @mousemove="updateDraw"
              @mouseup="finishDraw"
              @mouseleave="finishDraw"
            />
          </div>

          <div class="button-row">
            <button class="primary-btn" @click="addDetectionRegions" :disabled="isSaving">
              {{ isSaving ? "提交中..." : "添加检测区域" }}
            </button>
            <button class="secondary-btn" @click="cancelCurrentBoxes" :disabled="isSaving">
              取消当前框
            </button>
            <button class="danger-btn" @click="openConfirmClear" :disabled="isSaving">
              清除所有检测区域
            </button>
          </div>

          <div class="tips-box">
            <p>1. 鼠标按下后拖动，松开即可画出一个区域。</p>
            <p>2. 虚线框表示暂存区域，点击“添加检测区域”后才会正式生效。</p>
            <p>3. 最多只能设置 3 个区域；如果画错了，可点“取消当前框”重新画。</p>
          </div>
        </div>

        <aside class="info-panel">
          <div class="info-card">
            <h3>正式检测区域</h3>
            <div v-if="committedRegions.length" class="region-list">
              <div v-for="region in committedRegions" :key="region.id" class="region-card">
                <div class="region-title">
                  <span class="region-dot" :style="{ backgroundColor: regionColors[region.id] }"></span>
                  <strong>{{ getRegionDisplayName(region.id) }}</strong>
                </div>
              </div>
            </div>
            <p v-else class="empty-text">暂无正式区域</p>
          </div>

          <div class="info-card">
            <h3>候选区域</h3>
            <div v-if="candidateRegions.length" class="region-list">
              <div v-for="(region, index) in candidateRegions" :key="region.tempId" class="region-card candidate">
                <strong>{{ getRegionDisplayName(index + 1) }}</strong>
              </div>
            </div>
            <p v-else class="empty-text">暂无候选区域</p>
          </div>

          <div class="info-card">
            <h3>保存状态</h3>
            <p class="status-text" :class="saveStatusClass">{{ saveStatusText }}</p>
          </div>
        </aside>
      </div>
    </div>

    <div v-if="modalState.visible" class="modal-mask" @click.self="closeModal">
      <div class="modal-card">
        <button class="modal-close" @click="closeModal">✕</button>
        <h3>{{ modalState.title }}</h3>
        <p>{{ modalState.message }}</p>
        <div class="modal-actions">
          <button
            v-if="modalState.type === 'confirm'"
            class="secondary-btn"
            @click="closeModal"
          >
            取消
          </button>
          <button
            v-if="modalState.type === 'confirm'"
            class="danger-btn"
            @click="confirmClearAll"
          >
            确定
          </button>
          <button
            v-else
            class="primary-btn"
            @click="closeModal"
          >
            确定
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import {
  useCameraSettingStore,
  useDetectionSettingStore,
  useDetectionRegionStore,
} from "@/stores/settingsStore";

const CANVAS_WIDTH = 960;
const CANVAS_HEIGHT = 540;
const MAX_REGIONS = 3;
const MIN_RECT_SIZE = 10;
const STREAM_URL = import.meta.env.VITE_VIDEO_STREAM_URL;
const MEDIAMTX_WHEP_URL = `${STREAM_URL}/cam_high/whep`;
const regionColors = {
  1: "#22c55e",
  2: "#3b82f6",
  3: "#f97316",
};

const router = useRouter();
const cameraSettingStore = useCameraSettingStore();
const detectionSettingStore = useDetectionSettingStore();
const detectionRegionStore = useDetectionRegionStore();

const canvasRef = ref(null);
const frameVideoRef = ref(null);
const isDrawing = ref(false);
const isSaving = ref(false);
const frameLoaded = ref(false);
const frameError = ref("");
const startPoint = ref({ x: 0, y: 0 });
const draftRect = ref(null);
const candidateRegions = ref([]);
const committedRegions = ref([]);
const successFeedback = ref("");
let framePc = null;
let frameRefreshTimer = null;

const modalState = ref({
  visible: false,
  type: "alert",
  title: "",
  message: "",
});

const totalRegionCount = computed(
  () => candidateRegions.value.length + committedRegions.value.length
);

const availableIds = computed(() => {
  const usedIds = new Set(committedRegions.value.map((region) => region.id));
  return [1, 2, 3].filter((id) => !usedIds.has(id));
});

const selectedTarget = ref(detectionRegionStore.getCurrentTarget() || "all");

const sourceResolution = computed(() => {
  const value = cameraSettingStore.settings.resolution || "1920x1080";
  const [width, height] = value.split("x").map(Number);
  return {
    width: width || 1920,
    height: height || 1080,
  };
});

const saveStatusText = computed(() => {
  const state = detectionRegionStore.getState();
  if (state.unset) {
    return "尚未提交检测区域";
  }
  if (state.success) {
    return successFeedback.value || state.message || "最近一次提交成功";
  }
  return `最近一次提交失败：${state.message || "未知错误"}`;
});

const saveStatusClass = computed(() => {
  const state = detectionRegionStore.getState();
  if (state.unset) return "status-muted";
  return state.success ? "status-success" : "status-error";
});

function cloneRect(rect) {
  return { x: rect.x, y: rect.y, w: rect.w, h: rect.h };
}

function getCanvasContext() {
  return canvasRef.value ? canvasRef.value.getContext("2d") : null;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function getCanvasPoint(event) {
  const rect = canvasRef.value.getBoundingClientRect();
  const scaleX = CANVAS_WIDTH / rect.width;
  const scaleY = CANVAS_HEIGHT / rect.height;

  return {
    x: clamp((event.clientX - rect.left) * scaleX, 0, CANVAS_WIDTH),
    y: clamp((event.clientY - rect.top) * scaleY, 0, CANVAS_HEIGHT),
  };
}

function normalizeRect(start, end) {
  const x = Math.min(start.x, end.x);
  const y = Math.min(start.y, end.y);
  const w = Math.abs(end.x - start.x);
  const h = Math.abs(end.y - start.y);
  return { x, y, w, h };
}

function getRegionDisplayName(id) {
  return `候选区域${id}`;
}

function normalizePoint(x, y) {
  return [
    Number((x / CANVAS_WIDTH).toFixed(4)),
    Number((y / CANVAS_HEIGHT).toFixed(4)),
  ];
}

function rectToPolygon(rect) {
  return [
    normalizePoint(rect.x, rect.y),
    normalizePoint(rect.x + rect.w, rect.y),
    normalizePoint(rect.x + rect.w, rect.y + rect.h),
    normalizePoint(rect.x, rect.y + rect.h),
  ];
}

function getOverlapThreshold() {
  const overlap = Number(detectionSettingStore.settings.overlapRate);
  return Number.isFinite(overlap) ? overlap : 0.2;
}

function toBackendRoi(region) {
  return {
    roi_id: `hazard_${region.id}`,
    name: `ROI${region.id}`,
    enabled: true,
    roi_type: "forbidden_zone",
    judge_method: "foot_point",
    coordinate_mode: "normalized",
    polygon: rectToPolygon(region.rect),
    overlap_thres: getOverlapThreshold(),
  };
}

function fromStoredRegion(region = {}) {
  const polygon = Array.isArray(region.polygon) ? region.polygon : [];
  if (polygon.length >= 4) {
    const xs = polygon.map((point) => Number(point[0]) * CANVAS_WIDTH);
    const ys = polygon.map((point) => Number(point[1]) * CANVAS_HEIGHT);

    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);

    return {
      x: clamp(minX, 0, CANVAS_WIDTH),
      y: clamp(minY, 0, CANVAS_HEIGHT),
      w: clamp(maxX - minX, 0, CANVAS_WIDTH),
      h: clamp(maxY - minY, 0, CANVAS_HEIGHT),
    };
  }

  const rect = region.rect || {};
  return {
    x: clamp(rect.x || 0, 0, CANVAS_WIDTH),
    y: clamp(rect.y || 0, 0, CANVAS_HEIGHT),
    w: clamp(rect.w || 0, 0, CANVAS_WIDTH),
    h: clamp(rect.h || 0, 0, CANVAS_HEIGHT),
  };
}

function openAlert(message) {
  modalState.value = {
    visible: true,
    type: "alert",
    title: "提示",
    message,
  };
}

function openConfirmClear() {
  if (!committedRegions.value.length || isSaving.value) {
    return;
  }

  modalState.value = {
    visible: true,
    type: "confirm",
    title: "清除确认",
    message: "确认清除所有检测区域吗？",
  };
}

function closeModal() {
  modalState.value.visible = false;
}

function closeFrameStream() {
  if (frameRefreshTimer) {
    clearInterval(frameRefreshTimer);
    frameRefreshTimer = null;
  }

  if (framePc) {
    framePc.ontrack = null;
    framePc.close();
    framePc = null;
  }

  if (frameVideoRef.value) {
    frameVideoRef.value.srcObject = null;
  }
}

async function initFrameStream() {
  if (!frameVideoRef.value) return;

  closeFrameStream();
  frameLoaded.value = false;
  frameError.value = "";

  try {
    framePc = new RTCPeerConnection({
      iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
    });

    framePc.addTransceiver("video", { direction: "recvonly" });

    framePc.ontrack = (event) => {
      if (event.track.kind !== "video") return;

      const stream = new MediaStream([event.track]);
      frameVideoRef.value.srcObject = stream;

      frameVideoRef.value.onloadeddata = () => {
        frameLoaded.value = true;
        redrawCanvas();
      };

      event.track.onunmute = () => {
        frameLoaded.value = true;
        redrawCanvas();
      };
    };

    const offer = await framePc.createOffer();
    await framePc.setLocalDescription(offer);

    await new Promise((resolve) => {
      if (framePc.iceGatheringState === "complete") {
        resolve();
        return;
      }
      framePc.onicegatheringstatechange = () => {
        if (framePc?.iceGatheringState === "complete") {
          resolve();
        }
      };
    });

    const response = await fetch(MEDIAMTX_WHEP_URL, {
      method: "POST",
      headers: { "Content-Type": "application/sdp" },
      body: framePc.localDescription.sdp,
    });

    if (!response.ok) {
      throw new Error(`WHEP 请求失败: ${response.status}`);
    }

    const answerSDP = await response.text();
    await framePc.setRemoteDescription(
      new RTCSessionDescription({
        type: "answer",
        sdp: answerSDP,
      })
    );

    frameRefreshTimer = setInterval(() => {
      if (frameLoaded.value) {
        redrawCanvas();
      }
    }, 200);
  } catch (error) {
    frameError.value = "当前视频帧加载失败，已切换为示意底图";
    frameLoaded.value = false;
    closeFrameStream();
  }
}

function drawBackground(ctx) {
  const video = frameVideoRef.value;
  if (frameLoaded.value && video && video.readyState >= 2) {
    ctx.drawImage(video, 0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
    return;
  }

  const gradient = ctx.createLinearGradient(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
  gradient.addColorStop(0, "#0f172a");
  gradient.addColorStop(1, "#1e293b");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);

  ctx.strokeStyle = "rgba(148, 163, 184, 0.16)";
  ctx.lineWidth = 1;
  for (let x = 0; x <= CANVAS_WIDTH; x += 48) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, CANVAS_HEIGHT);
    ctx.stroke();
  }
  for (let y = 0; y <= CANVAS_HEIGHT; y += 48) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(CANVAS_WIDTH, y);
    ctx.stroke();
  }

  ctx.fillStyle = "rgba(255, 255, 255, 0.06)";
  ctx.fillRect(80, 60, 180, 96);
  ctx.fillRect(690, 110, 140, 120);
  ctx.fillRect(320, 320, 220, 110);

  ctx.fillStyle = "#e2e8f0";
  ctx.font = "600 20px Arial";
  ctx.fillText("Current Video Frame", 28, 36);
  ctx.font = "14px Arial";
  ctx.fillStyle = "rgba(226, 232, 240, 0.8)";
  ctx.fillText(frameError.value || "当前视频帧加载中，拖拽鼠标绘制检测区域", 28, 62);
}

function drawRect(ctx, rect, options = {}) {
  const {
    strokeStyle = "#ffffff",
    fillStyle = "rgba(255, 255, 255, 0.12)",
    lineDash = [],
    label = "",
    lineWidth = 2,
  } = options;

  ctx.save();
  ctx.setLineDash(lineDash);
  ctx.lineWidth = lineWidth;
  ctx.strokeStyle = strokeStyle;
  ctx.fillStyle = fillStyle;
  ctx.fillRect(rect.x, rect.y, rect.w, rect.h);
  ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);

  if (label) {
    ctx.setLineDash([]);
    ctx.font = "bold 14px Arial";
    const pillWidth = Math.max(28, 16 + ctx.measureText(label).width);
    const pillHeight = 24;
    ctx.fillStyle = strokeStyle;
    ctx.fillRect(rect.x, Math.max(0, rect.y - pillHeight), pillWidth, pillHeight);
    ctx.fillStyle = "#ffffff";
    ctx.fillText(label, rect.x + 8, Math.max(17, rect.y - 7));
  }
  ctx.restore();
}

function redrawCanvas() {
  const ctx = getCanvasContext();
  if (!ctx) return;

  ctx.clearRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
  drawBackground(ctx);

  committedRegions.value.forEach((region) => {
    drawRect(ctx, region.rect, {
      strokeStyle: regionColors[region.id],
      fillStyle: `${regionColors[region.id]}22`,
      label: String(region.id),
      lineWidth: 3,
    });
  });

  candidateRegions.value.forEach((region, index) => {
    drawRect(ctx, region.rect, {
      strokeStyle: "#facc15",
      fillStyle: "rgba(250, 204, 21, 0.18)",
      lineDash: [8, 6],
      label: `候选 ${index + 1}`,
    });
  });

  if (draftRect.value) {
    drawRect(ctx, draftRect.value, {
      strokeStyle: "#f8fafc",
      fillStyle: "rgba(248, 250, 252, 0.12)",
      lineDash: [10, 6],
    });
  }
}

function loadSavedRegions() {
  committedRegions.value = detectionRegionStore.getRegions(selectedTarget.value).map((region) => ({
    id: Number(String(region.roi_id || "").split("_").pop()) || 1,
    rect: fromStoredRegion(region),
  }));
}

async function syncRegionsFromServer() {
  const rois = await detectionRegionStore.fetchRegions();
  if (rois === null) {
    return false;
  }
  loadSavedRegions();
  redrawCanvas();
  return true;
}

function beginDraw(event) {
  if (isSaving.value) return;

  if (totalRegionCount.value >= MAX_REGIONS) {
    openAlert("最多只能勾选三个区域！");
    return;
  }

  const point = getCanvasPoint(event);
  startPoint.value = point;
  draftRect.value = { x: point.x, y: point.y, w: 0, h: 0 };
  isDrawing.value = true;
  redrawCanvas();
}

function updateDraw(event) {
  if (!isDrawing.value || isSaving.value) return;

  const currentPoint = getCanvasPoint(event);
  draftRect.value = normalizeRect(startPoint.value, currentPoint);
  redrawCanvas();
}

function finishDraw(event) {
  if (!isDrawing.value || isSaving.value) return;

  const endPoint = getCanvasPoint(event);
  const rect = normalizeRect(startPoint.value, endPoint);
  isDrawing.value = false;
  draftRect.value = null;

  if (rect.w < MIN_RECT_SIZE || rect.h < MIN_RECT_SIZE) {
    redrawCanvas();
    return;
  }

  if (totalRegionCount.value >= MAX_REGIONS) {
    openAlert("最多只能勾选三个区域！");
    redrawCanvas();
    return;
  }

  candidateRegions.value.push({
    tempId: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    rect,
  });
  redrawCanvas();
}

function cancelCurrentBoxes() {
  if (isSaving.value) return;

  candidateRegions.value = [];
  draftRect.value = null;
  isDrawing.value = false;
  redrawCanvas();
}

async function addDetectionRegions() {
  if (!candidateRegions.value.length || isSaving.value) {
    return;
  }

  if (candidateRegions.value.length + committedRegions.value.length > MAX_REGIONS) {
    openAlert("最多只能勾选三个区域！");
    return;
  }

  const ids = availableIds.value.slice(0, candidateRegions.value.length);
  const pendingRegions = candidateRegions.value.map((region, index) => ({
    id: ids[index],
    rect: cloneRect(region.rect),
  }));
  const nextCommitted = [...committedRegions.value, ...pendingRegions].sort(
    (left, right) => left.id - right.id
  );
  const payload = nextCommitted.map((region) => toBackendRoi(region));
  const successMessage = pendingRegions.map((region) => `${getRegionDisplayName(region.id)}保存成功`).join(" / ");

  isSaving.value = true;
  try {
    const success = await detectionRegionStore.saveRegions(payload, {
      target: selectedTarget.value,
    });
    if (!success) {
      const state = detectionRegionStore.getState();
      successFeedback.value = "";
      openAlert(state.message || "检测区域保存失败");
      return;
    }

    await syncRegionsFromServer();
    committedRegions.value = committedRegions.value.length ? committedRegions.value : nextCommitted;
    candidateRegions.value = [];
    successFeedback.value = successMessage;
    redrawCanvas();
  } finally {
    isSaving.value = false;
  }
}

async function confirmClearAll() {
  if (isSaving.value) return;

  isSaving.value = true;
  try {
    const success = await detectionRegionStore.clearRegions({
      target: selectedTarget.value,
    });
    if (!success) {
      const state = detectionRegionStore.getState();
      successFeedback.value = "";
      openAlert(state.message || "清除检测区域失败");
      return;
    }

    await syncRegionsFromServer();
    committedRegions.value = [];
    candidateRegions.value = [];
    draftRect.value = null;
    successFeedback.value = "已清除所有检测区域";
    closeModal();
    redrawCanvas();
  } finally {
    isSaving.value = false;
  }
}

function goBack() {
  if (isSaving.value) return;
  router.push("/");
}

onMounted(async () => {
  await nextTick();
  await initFrameStream();
  await syncRegionsFromServer();
  loadSavedRegions();
  redrawCanvas();
});

watch(selectedTarget, async () => {
  detectionRegionStore.setCurrentTarget(selectedTarget.value);
  candidateRegions.value = [];
  draftRect.value = null;
  successFeedback.value = "";
  await syncRegionsFromServer();
});

onUnmounted(() => {
  closeFrameStream();
});
</script>

<style scoped>
.settings-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
  padding: 20px;
}

.settings-container {
  width: 100%;
  max-width: 1320px;
  background: #ffffff;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  overflow: hidden;
}

.settings-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  padding: 20px 24px;
  border-bottom: 1px solid #e8e8e8;
}

.settings-title {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
  color: #333;
}

.settings-subtitle {
  margin: 8px 0 0;
  color: #666;
  font-size: 0.95rem;
}

.close-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: #666;
  padding: 4px;
  border-radius: 4px;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.close-btn:hover:not(:disabled) {
  background: #f0f0f0;
  color: #333;
}

.settings-form {
  padding: 24px;
  transition: opacity 0.2s;
}

.settings-form.form-loading {
  opacity: 0.7;
  pointer-events: none;
}

.detection-region-layout {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(320px, 1fr);
  gap: 20px;
}

.canvas-panel,
.info-card {
  border: 1px solid #e8e8e8;
  border-radius: 10px;
  background: #ffffff;
}

.canvas-panel {
  padding: 18px;
}

.panel-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  color: #555;
  font-size: 0.9rem;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toolbar-label {
  white-space: nowrap;
}

.target-select {
  min-width: 150px;
  padding: 6px 10px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  background: #fff;
  color: #333;
}

.canvas-frame {
  position: relative;
  overflow: hidden;
  border-radius: 12px;
  background: #0f172a;
}

.frame-video {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}

canvas {
  display: block;
  width: 100%;
  max-width: 100%;
  cursor: crosshair;
}

.button-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 16px;
}

.primary-btn,
.secondary-btn,
.danger-btn {
  border: none;
  border-radius: 6px;
  padding: 10px 18px;
  font-size: 0.95rem;
  cursor: pointer;
  transition: all 0.2s;
}

.primary-btn {
  background: #1677ff;
  color: #ffffff;
}

.primary-btn:hover:not(:disabled) {
  background: #4096ff;
}

.secondary-btn {
  background: #f3f4f6;
  color: #333;
}

.secondary-btn:hover:not(:disabled) {
  background: #e5e7eb;
}

.danger-btn {
  background: #dc2626;
  color: #ffffff;
}

.danger-btn:hover:not(:disabled) {
  background: #ef4444;
}

button:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.tips-box {
  margin-top: 16px;
  padding: 14px 16px;
  border-radius: 8px;
  background: #f5f9ff;
  color: #335;
}

.tips-box p + p {
  margin-top: 6px;
}

.info-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.info-card {
  padding: 16px;
}

.info-card h3 {
  margin: 0 0 12px;
  font-size: 1rem;
  color: #333;
}

.region-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.region-card {
  padding: 12px;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  background: #fafafa;
}

.region-card.candidate {
  border-style: dashed;
}

.region-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.region-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
}

.empty-text {
  color: #888;
}

.status-text {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 500;
}

.status-success {
  color: #15803d;
}

.status-error {
  color: #dc2626;
}

.status-muted {
  color: #666;
}

.modal-mask {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: rgba(15, 23, 42, 0.45);
}

.modal-card {
  position: relative;
  width: min(420px, 100%);
  padding: 24px 24px 20px;
  border-radius: 14px;
  background: #ffffff;
  box-shadow: 0 16px 48px rgba(15, 23, 42, 0.2);
}

.modal-card h3 {
  margin: 0 0 12px;
  color: #111827;
  font-size: 1.2rem;
  font-weight: 600;
}

.modal-card p {
  color: #374151;
}

.modal-close {
  position: absolute;
  top: 12px;
  right: 12px;
  border: none;
  background: transparent;
  color: #6b7280;
  font-size: 18px;
  cursor: pointer;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
}

@media (max-width: 1024px) {
  .detection-region-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .settings-page {
    padding: 12px;
  }

  .settings-header,
  .settings-form {
    padding: 16px;
  }

  .panel-toolbar,
  .button-row {
    flex-direction: column;
  }

  .toolbar-actions,
  .target-select {
    width: 100%;
  }

  .primary-btn,
  .secondary-btn,
  .danger-btn {
    width: 100%;
  }
}
</style>
