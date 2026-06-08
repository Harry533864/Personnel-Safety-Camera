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
              <div class="draw-mode-tabs" role="group" aria-label="ROI draw mode">
                <button
                  type="button"
                  :class="{ active: drawMode === 'rect' }"
                  :disabled="isSaving"
                  @click="setDrawMode('rect')"
                >
                  矩形
                </button>
                <button
                  type="button"
                  :class="{ active: drawMode === 'polygon' }"
                  :disabled="isSaving"
                  @click="setDrawMode('polygon')"
                >
                  多边形
                </button>
              </div>
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
              @click="addPolygonPoint"
              @mouseleave="handleCanvasLeave"
            />
          </div>

          <div class="button-row">
            <button class="primary-btn" @click="addDetectionRegions" :disabled="isSaving">
              {{ isSaving ? "提交中..." : "添加检测区域" }}
            </button>
            <button class="secondary-btn" @click="cancelCurrentBoxes" :disabled="isSaving">
              取消当前框
            </button>
            <button
              class="secondary-btn"
              @click="finishPolygon"
              :disabled="isSaving || drawMode !== 'polygon' || draftPolygon.length < MIN_POLYGON_POINTS"
            >
              完成多边形
            </button>
            <button class="danger-btn" @click="openConfirmClear" :disabled="isSaving">
              清除所有检测区域
            </button>
          </div>

          <div class="tips-box">
            <p>1. 鼠标按下后拖动，松开即可画出一个区域。</p>
            <p>2. 虚线框表示暂存区域，点击“添加检测区域”后才会正式生效。</p>
            <p>3. 最多只能设置 3 个区域；如果画错了，可点“取消当前框”重新画。</p>
            <p>4. 多边形模式下逐点点击画布，点击起点附近或点击“完成多边形”即可闭合。</p>
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
                  <span class="region-meta">{{ getRegionPointCount(region) }} 点</span>
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
                <span class="region-meta">{{ getRegionPointCount(region) }} 点</span>
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
const MIN_POLYGON_POINTS = 3;
const POLYGON_CLOSE_DISTANCE = 14;
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
const draftPolygon = ref([]);
const hoverPoint = ref(null);
const drawMode = ref("rect");
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

function clonePoint(point = {}) {
  return {
    x: Number(point.x) || 0,
    y: Number(point.y) || 0,
  };
}

function clonePoints(points = []) {
  return points.map((point) => clonePoint(point));
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

function rectToPoints(rect) {
  return [
    { x: rect.x, y: rect.y },
    { x: rect.x + rect.w, y: rect.y },
    { x: rect.x + rect.w, y: rect.y + rect.h },
    { x: rect.x, y: rect.y + rect.h },
  ];
}

function pointsToRect(points = []) {
  const validPoints = points.filter(
    (point) => Number.isFinite(point.x) && Number.isFinite(point.y)
  );

  if (!validPoints.length) {
    return { x: 0, y: 0, w: 0, h: 0 };
  }

  const xs = validPoints.map((point) => point.x);
  const ys = validPoints.map((point) => point.y);
  const minX = clamp(Math.min(...xs), 0, CANVAS_WIDTH);
  const maxX = clamp(Math.max(...xs), 0, CANVAS_WIDTH);
  const minY = clamp(Math.min(...ys), 0, CANVAS_HEIGHT);
  const maxY = clamp(Math.max(...ys), 0, CANVAS_HEIGHT);

  return {
    x: minX,
    y: minY,
    w: maxX - minX,
    h: maxY - minY,
  };
}

function createRegionShape({ id, tempId, points, shape = "polygon" }) {
  const clonedPoints = clonePoints(points);
  return {
    id,
    tempId,
    shape,
    rect: pointsToRect(clonedPoints),
    points: clonedPoints,
  };
}

function getRegionPoints(region = {}) {
  if (Array.isArray(region.points) && region.points.length) {
    return region.points;
  }
  if (Array.isArray(region.polygon) && region.polygon.length) {
    return region.polygon;
  }
  if (region.rect) {
    return rectToPoints(region.rect);
  }
  return [];
}

function getRegionPointCount(region) {
  return getRegionPoints(region).length;
}

function getRegionDisplayName(id) {
  return `候选区域${id}`;
}

function normalizePoint(x, y) {
  return [
    Number((clamp(x, 0, CANVAS_WIDTH) / CANVAS_WIDTH).toFixed(4)),
    Number((clamp(y, 0, CANVAS_HEIGHT) / CANVAS_HEIGHT).toFixed(4)),
  ];
}

function pointsToNormalizedPolygon(points) {
  return points.map((point) => normalizePoint(point.x, point.y));
}

function normalizedPolygonToPoints(polygon = []) {
  return polygon
    .map((point) => {
      if (!Array.isArray(point) || point.length !== 2) return null;
      const x = Number(point[0]);
      const y = Number(point[1]);
      if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
      return {
        x: clamp(x * CANVAS_WIDTH, 0, CANVAS_WIDTH),
        y: clamp(y * CANVAS_HEIGHT, 0, CANVAS_HEIGHT),
      };
    })
    .filter(Boolean);
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
    judge_method: "overlap",
    coordinate_mode: "normalized",
    polygon: pointsToNormalizedPolygon(getRegionPoints(region)),
    overlap_thres: getOverlapThreshold(),
    target: selectedTarget.value,
  };
}

function fromStoredRegion(region = {}) {
  const polygon = Array.isArray(region.polygon) ? region.polygon : [];
  if (polygon.length >= MIN_POLYGON_POINTS) {
    const points = normalizedPolygonToPoints(polygon);
    if (points.length >= MIN_POLYGON_POINTS) {
      return createRegionShape({
        shape: points.length === 4 ? "rect" : "polygon",
        points,
      });
    }
  }

  const rect = region.rect || {};
  const safeRect = {
    x: clamp(rect.x || 0, 0, CANVAS_WIDTH),
    y: clamp(rect.y || 0, 0, CANVAS_HEIGHT),
    w: clamp(rect.w || 0, 0, CANVAS_WIDTH),
    h: clamp(rect.h || 0, 0, CANVAS_HEIGHT),
  };

  return createRegionShape({
    shape: "rect",
    points: rectToPoints(safeRect),
  });
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
    if (!isSaving.value) {
      openAlert("当前没有可清除的正式检测区域");
    }
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

  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);

  ctx.strokeStyle = "rgba(143, 17, 23, 0.12)";
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

  ctx.fillStyle = "rgba(193, 18, 31, 0.035)";
  ctx.fillRect(80, 60, 180, 96);
  ctx.fillRect(690, 110, 140, 120);
  ctx.fillRect(320, 320, 220, 110);

  ctx.fillStyle = "#1f2933";
  ctx.font = "600 20px Arial";
  ctx.fillText("Current Video Frame", 28, 36);
  ctx.font = "14px Arial";
  ctx.fillStyle = "#6b7280";
  ctx.fillText(frameError.value || "当前视频帧加载中，拖拽鼠标绘制检测区域", 28, 62);
}

function drawPolygon(ctx, points, options = {}) {
  if (!points.length) return;

  const {
    strokeStyle = "#ffffff",
    fillStyle = "rgba(255, 255, 255, 0.12)",
    lineDash = [],
    label = "",
    lineWidth = 2,
    closePath = true,
    previewPoint = null,
  } = options;

  const pathPoints = previewPoint ? [...points, previewPoint] : points;

  ctx.save();
  ctx.setLineDash(lineDash);
  ctx.lineWidth = lineWidth;
  ctx.strokeStyle = strokeStyle;
  ctx.fillStyle = fillStyle;

  if (pathPoints.length > 1) {
    ctx.beginPath();
    ctx.moveTo(pathPoints[0].x, pathPoints[0].y);
    pathPoints.slice(1).forEach((point) => {
      ctx.lineTo(point.x, point.y);
    });
    if (closePath && points.length >= MIN_POLYGON_POINTS) {
      ctx.closePath();
      ctx.fill();
    }
    ctx.stroke();
  }

  ctx.setLineDash([]);
  points.forEach((point, index) => {
    ctx.beginPath();
    ctx.fillStyle = index === 0 ? "#ffffff" : strokeStyle;
    ctx.strokeStyle = strokeStyle;
    ctx.lineWidth = 2;
    ctx.arc(point.x, point.y, index === 0 ? 5 : 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
  });

  if (label) {
    const bounds = pointsToRect(points);
    ctx.font = "bold 14px Arial";
    const pillWidth = Math.max(28, 16 + ctx.measureText(label).width);
    const pillHeight = 24;
    const labelX = bounds.x;
    const labelY = Math.max(0, bounds.y - pillHeight);

    ctx.fillStyle = strokeStyle;
    ctx.fillRect(labelX, labelY, pillWidth, pillHeight);
    ctx.fillStyle = "#ffffff";
    ctx.fillText(label, labelX + 8, labelY + 17);
  }

  ctx.restore();
}

function redrawCanvas() {
  const ctx = getCanvasContext();
  if (!ctx) return;

  ctx.clearRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
  drawBackground(ctx);

  committedRegions.value.forEach((region) => {
    drawPolygon(ctx, getRegionPoints(region), {
      strokeStyle: regionColors[region.id],
      fillStyle: `${regionColors[region.id]}22`,
      label: String(region.id),
      lineWidth: 3,
    });
  });

  candidateRegions.value.forEach((region, index) => {
    drawPolygon(ctx, getRegionPoints(region), {
      strokeStyle: "#facc15",
      fillStyle: "rgba(250, 204, 21, 0.18)",
      lineDash: [8, 6],
      label: `候选 ${index + 1}`,
    });
  });

  if (draftRect.value) {
    drawPolygon(ctx, rectToPoints(draftRect.value), {
      strokeStyle: "#f8fafc",
      fillStyle: "rgba(248, 250, 252, 0.12)",
      lineDash: [10, 6],
    });
  }

  if (draftPolygon.value.length) {
    drawPolygon(ctx, draftPolygon.value, {
      strokeStyle: "#dc2626",
      fillStyle: "rgba(220, 38, 38, 0.12)",
      lineDash: [8, 6],
      closePath: false,
      previewPoint: hoverPoint.value,
      label: draftPolygon.value.length >= MIN_POLYGON_POINTS ? "待闭合" : "",
    });
  }
}

function loadSavedRegions() {
  committedRegions.value = detectionRegionStore.getRegions(selectedTarget.value).map((region) => {
    const shape = fromStoredRegion(region);
    return {
      ...shape,
      id: Number(String(region.roi_id || "").split("_").pop()) || 1,
    };
  });
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
  if (drawMode.value !== "rect" || isSaving.value) return;

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
  if (drawMode.value === "polygon") {
    if (draftPolygon.value.length && !isSaving.value) {
      hoverPoint.value = getCanvasPoint(event);
      redrawCanvas();
    }
    return;
  }

  if (!isDrawing.value || isSaving.value) return;

  const currentPoint = getCanvasPoint(event);
  draftRect.value = normalizeRect(startPoint.value, currentPoint);
  redrawCanvas();
}

function finishDraw(event) {
  if (drawMode.value !== "rect" || !isDrawing.value || isSaving.value) return;

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

  candidateRegions.value.push(
    createRegionShape({
      tempId: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      shape: "rect",
      points: rectToPoints(rect),
    })
  );
  redrawCanvas();
}

function distanceBetween(left, right) {
  const dx = left.x - right.x;
  const dy = left.y - right.y;
  return Math.sqrt(dx * dx + dy * dy);
}

function setDrawMode(mode) {
  if (isSaving.value || drawMode.value === mode) return;

  drawMode.value = mode;
  draftRect.value = null;
  draftPolygon.value = [];
  hoverPoint.value = null;
  isDrawing.value = false;
  redrawCanvas();
}

function addPolygonPoint(event) {
  if (drawMode.value !== "polygon" || isSaving.value) return;

  if (totalRegionCount.value >= MAX_REGIONS) {
    openAlert("最多只能勾选三个区域！");
    return;
  }

  const point = getCanvasPoint(event);
  const firstPoint = draftPolygon.value[0];
  if (
    firstPoint &&
    draftPolygon.value.length >= MIN_POLYGON_POINTS &&
    distanceBetween(point, firstPoint) <= POLYGON_CLOSE_DISTANCE
  ) {
    finishPolygon();
    return;
  }

  draftPolygon.value = [...draftPolygon.value, point];
  hoverPoint.value = point;
  redrawCanvas();
}

function finishPolygon() {
  if (drawMode.value !== "polygon" || isSaving.value) return;

  if (draftPolygon.value.length < MIN_POLYGON_POINTS) {
    openAlert("多边形至少需要 3 个点");
    return;
  }

  if (totalRegionCount.value >= MAX_REGIONS) {
    openAlert("最多只能勾选三个区域！");
    return;
  }

  candidateRegions.value.push(
    createRegionShape({
      tempId: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      shape: "polygon",
      points: draftPolygon.value,
    })
  );
  draftPolygon.value = [];
  hoverPoint.value = null;
  redrawCanvas();
}

function handleCanvasLeave(event) {
  if (drawMode.value === "rect") {
    finishDraw(event);
    return;
  }

  hoverPoint.value = null;
  redrawCanvas();
}

function cancelCurrentBoxes() {
  if (isSaving.value) return;

  if (!candidateRegions.value.length && !draftRect.value && !draftPolygon.value.length) {
    openAlert("当前没有正在绘制或暂存的候选区域");
    return;
  }

  candidateRegions.value = [];
  draftRect.value = null;
  draftPolygon.value = [];
  hoverPoint.value = null;
  isDrawing.value = false;
  redrawCanvas();
}

async function addDetectionRegions() {
  if (!candidateRegions.value.length || isSaving.value) {
    if (!isSaving.value) {
      openAlert("请先在画面上拖出一个新的候选区域");
    }
    return;
  }

  if (candidateRegions.value.length + committedRegions.value.length > MAX_REGIONS) {
    openAlert("最多只能勾选三个区域！");
    return;
  }

  const ids = availableIds.value.slice(0, candidateRegions.value.length);
  const pendingRegions = candidateRegions.value.map((region, index) =>
    createRegionShape({
      id: ids[index],
      shape: region.shape,
      points: getRegionPoints(region),
    })
  );
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
    draftPolygon.value = [];
    hoverPoint.value = null;
    successFeedback.value = successMessage;
    redrawCanvas();
  } finally {
    isSaving.value = false;
  }
}

async function confirmClearAll() {
  if (isSaving.value) return;

  closeModal();
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
    draftPolygon.value = [];
    hoverPoint.value = null;
    isDrawing.value = false;
    successFeedback.value = "已清除所有检测区域";
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
  draftPolygon.value = [];
  hoverPoint.value = null;
  isDrawing.value = false;
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
  flex-wrap: wrap;
}

.toolbar-label {
  white-space: nowrap;
}

.draw-mode-tabs {
  display: inline-flex;
  align-items: center;
  padding: 2px;
  gap: 2px;
  background: #f3f4f6;
  border: 1px solid #d1d5db;
  border-radius: 6px;
}

.draw-mode-tabs button {
  min-height: 28px;
  padding: 0 10px;
  color: #4b5563;
  background: transparent;
  border: 0;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  font-weight: 700;
  transition:
    background-color 0.18s ease,
    color 0.18s ease,
    box-shadow 0.18s ease;
}

.draw-mode-tabs button.active {
  color: #ffffff;
  background: #c1121f;
  box-shadow: 0 4px 10px rgba(193, 18, 31, 0.2);
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
  background: #ffffff;
  border: 1px solid var(--industrial-border);
  box-shadow: var(--industrial-shadow);
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
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  border-style: dashed;
}

.region-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.region-meta {
  margin-left: auto;
  color: #6b7280;
  font-size: 12px;
  font-weight: 700;
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

<style scoped>
.settings-page {
  min-height: calc(100vh - var(--topbar-height));
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 18px;
  background: transparent;
}

.detection-region-container,
.settings-container {
  width: min(1220px, 100%);
  overflow: hidden;
  background: var(--industrial-surface);
  border: 1px solid var(--industrial-border);
  border-radius: var(--industrial-radius);
  box-shadow: var(--industrial-shadow);
}

.settings-header {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 20px 16px 24px;
  border-bottom: 1px solid var(--industrial-border);
}

.settings-header::before {
  content: "";
  position: absolute;
  left: 0;
  top: 14px;
  bottom: 14px;
  width: 3px;
  border-radius: 0 999px 999px 0;
  background: var(--industrial-red);
}

.settings-title {
  margin: 0;
  color: var(--industrial-text);
  font-size: 18px;
  font-weight: 800;
}

.settings-subtitle {
  margin: 6px 0 0;
  color: var(--industrial-muted);
  font-size: 12px;
}

.close-btn {
  width: 34px;
  height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--industrial-muted);
  background: var(--industrial-surface-subtle);
  border: 1px solid var(--industrial-border);
  border-radius: var(--industrial-radius-sm);
}

.close-btn:hover:not(:disabled) {
  color: var(--industrial-red-dark);
  background: var(--industrial-red-soft);
  border-color: rgba(185, 28, 28, 0.24);
}

.detection-region-layout,
.settings-form {
  padding: 18px;
  gap: 16px;
  background: #fbfcfd;
}

.canvas-panel,
.region-side-panel,
.panel-card,
.region-list-panel,
.info-card,
.region-card,
.roi-card,
.empty-panel,
.panel-toolbar,
.tips-box {
  background: var(--industrial-surface);
  border: 1px solid var(--industrial-border);
  border-radius: var(--industrial-radius);
  box-shadow: var(--industrial-shadow);
}

.canvas-panel {
  overflow: hidden;
}

.panel-toolbar {
  min-height: 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  margin-bottom: 12px;
  color: var(--industrial-muted);
  font-size: 12px;
  font-weight: 700;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.toolbar-label {
  color: var(--industrial-faint);
  font-size: 12px;
}

.target-select,
.form-select,
.form-input,
.number-input {
  min-height: 34px;
  padding: 0 10px;
  color: var(--industrial-text);
  background: var(--industrial-surface-subtle);
  border: 1px solid var(--industrial-border);
  border-radius: var(--industrial-radius-sm);
}

.canvas-wrapper,
.video-wrapper,
.draw-area {
  background:
    linear-gradient(90deg, rgba(143, 17, 23, 0.055) 1px, transparent 1px),
    linear-gradient(180deg, rgba(31, 41, 51, 0.045) 1px, transparent 1px),
    #ffffff;
  background-size: 32px 32px;
  border: 1px solid var(--industrial-border);
  border-radius: var(--industrial-radius);
  overflow: hidden;
}

.video-placeholder,
.canvas-placeholder {
  color: var(--industrial-muted);
  background: #ffffff;
}

.region-side-panel {
  padding: 14px;
}

.panel-title,
.region-list-title,
.roi-title,
.card-title {
  color: var(--industrial-text);
  font-size: 14px;
  font-weight: 800;
}

.panel-title::before,
.region-list-title::before,
.card-title::before {
  content: "";
  display: inline-block;
  width: 3px;
  height: 14px;
  margin-right: 8px;
  border-radius: 999px;
  vertical-align: -2px;
  background: var(--industrial-red);
}

.roi-card {
  padding: 12px;
  transition:
    border-color var(--motion-normal),
    background-color var(--motion-normal),
    box-shadow var(--motion-normal);
}

.roi-card:hover {
  border-color: rgba(185, 28, 28, 0.24);
  box-shadow: var(--industrial-shadow-hover);
}

.roi-card.active,
.selected,
.active {
  border-color: rgba(185, 28, 28, 0.36);
  background: var(--industrial-red-soft);
}

.action-btn,
.mini-btn,
.toolbar-btn,
.clear-btn,
.confirm-btn,
.secondary-btn {
  min-height: 34px;
  padding: 0 12px;
  border-radius: var(--industrial-radius-sm);
  border: 1px solid var(--industrial-border);
  background: var(--industrial-surface-subtle);
  color: var(--industrial-muted);
}

.action-btn:hover:not(:disabled),
.mini-btn:hover:not(:disabled),
.toolbar-btn:hover:not(:disabled),
.secondary-btn:hover:not(:disabled) {
  color: var(--industrial-red-dark);
  background: var(--industrial-red-soft);
  border-color: rgba(185, 28, 28, 0.24);
}

.confirm-btn,
.primary-btn {
  color: #ffffff;
  background: var(--industrial-red);
  border-color: var(--industrial-red);
  font-weight: 800;
}

.confirm-btn:hover:not(:disabled),
.primary-btn:hover:not(:disabled) {
  background: var(--industrial-red-dark);
  border-color: var(--industrial-red-dark);
}

.clear-btn,
.danger,
.danger-btn {
  color: var(--industrial-danger);
  background: var(--industrial-danger-soft);
  border-color: rgba(197, 48, 48, 0.28);
}

.settings-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 16px 20px 22px;
  border-top: 1px solid var(--industrial-border);
  background: #fbfcfd;
}

.tips-box,
.empty-panel {
  color: var(--industrial-muted);
}

@media (max-width: 980px) {
  .settings-page {
    padding: 12px;
  }

  .detection-region-layout,
  .settings-form {
    flex-direction: column;
  }
}
</style>
