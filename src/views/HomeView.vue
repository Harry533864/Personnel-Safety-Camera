<template>
  <div class="monitor-page">
    <div class="operation-bar">
      <div class="operation-bar-left">
        <div class="page-title-group">
          <h2 class="page-title">相机页面</h2>
          <div class="jetson-discovery">
            <button
              class="jetson-scan-btn"
              type="button"
              :disabled="isScanningJetson"
              @click="scanJetsons"
              title="扫描在线设备"
            >
              <span class="scan-dot" :class="{ scanning: isScanningJetson }"></span>
              {{ isScanningJetson ? '扫描中' : '扫描设备' }}
            </button>
            <span class="jetson-current" :class="{ online: activeJetsonOnline }">
              {{ activeJetsonLabel }}
            </span>
            <div class="jetson-results" v-if="showJetsonResults && discoveredJetsons.length">
              <button
                v-for="device in discoveredJetsons"
                :key="device.api"
                class="jetson-result"
                type="button"
                @click="selectJetson(device)"
              >
                <span>{{ device.label }}</span>
                <strong>{{ device.host }}</strong>
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="operation-bar-right">
        <div class="operation-actions">
          <button 
          class="operation-btn" 
          :class="{ active: cameraState.active, inactive: cameraState.inactive, unset: cameraState.unset }"
          @click="goToCameraSettings"
          title="相机设置"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 6h4l2-3h6l2 3h3a2 2 0 0 1 2 2v5"></path>
            <path d="M1 8v11a2 2 0 0 0 2 2h11"></path>
            <circle cx="12" cy="13" r="4"></circle>
            <circle cx="18.9" cy="18.9" r="1.55"></circle>
            <path d="M18.9 16.1v.95"></path>
            <path d="M18.9 20.75v.95"></path>
            <path d="M16.1 18.9h.95"></path>
            <path d="M20.75 18.9h.95"></path>
            <path d="M16.92 16.92l.67.67"></path>
            <path d="M20.22 20.22l.67.67"></path>
            <path d="M20.89 16.92l-.67.67"></path>
            <path d="M16.92 20.89l.67-.67"></path>
          </svg>
        </button>

          <button 
          class="operation-btn" 
          :class="{ active: detectionState.active, inactive: detectionState.inactive, unset: detectionState.unset }"
          @click="goToDetectionSettings"
          title="检测设置"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="3" width="7" height="7"></rect>
            <rect x="14" y="3" width="7" height="7"></rect>
            <rect x="14" y="14" width="7" height="7"></rect>
            <rect x="3" y="14" width="7" height="7"></rect>
          </svg>
        </button>

          <button
          class="operation-btn"
          :class="{ active: detectionRegionState.active, inactive: detectionRegionState.inactive, unset: detectionRegionState.unset }"
          @click="goToDetectionRegion"
          title="检测区域"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 3h6"></path>
            <path d="M3 3v6"></path>
            <path d="M21 3h-6"></path>
            <path d="M21 3v6"></path>
            <path d="M3 21h6"></path>
            <path d="M3 21v-6"></path>
            <path d="M21 21h-6"></path>
            <path d="M21 21v-6"></path>
            <path d="M12 8v8"></path>
            <path d="M8 12h8"></path>
          </svg>
        </button>

          <button
          class="operation-btn"
          :class="{ active: modelManagementState.active, inactive: modelManagementState.inactive, unset: modelManagementState.unset }"
          @click="goToModelManagement"
          title="模型管理"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 16V4"></path>
            <path d="M7 9l5-5 5 5"></path>
            <path d="M4 20h16"></path>
          </svg>
        </button>

          <button
          class="operation-btn"
          :class="{ active: exceptionOutputState.active, inactive: exceptionOutputState.inactive, unset: exceptionOutputState.unset }"
          @click="goToExceptionOutput"
          title="异常检测配置"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
            <path d="M12 9v4"></path>
            <path d="M12 17h.01"></path>
          </svg>
        </button>

        </div>

        <div class="status-indicator fps-indicator" :class="currentFpsClass">
          <span class="status-dot"></span>
          <span class="status-text">{{ currentFps || '-- fps' }}</span>
        </div>

        <div class="status-indicator" :class="networkStatus">
          <span class="status-dot"></span>
          <span class="status-text">{{ networkSpeed }} MB/s</span>
        </div>
      </div>
    </div>

    <!-- 相机画面预览 -->
    <div class="camera-view-area">
      <div class="video-container" ref="videoContainer">
        <video
          v-show="videoLoaded"
          ref="videoPlayer"
          class="video-player"
          autoplay
          muted
          playsinline
        ></video>

        <!-- 视频加载失败的显示层 -->
        <div class="video-placeholder" v-if="!videoLoaded">
          <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" opacity="0.3">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
            <circle cx="8.5" cy="8.5" r="1.5"></circle>
            <polyline points="21 15 16 10 5 21"></polyline>
          </svg>
          <p>{{ errorMessage || '视频加载中...' }}</p>
          <button @click="manualReconnect" v-if="manualReconnectVisiable" class="reconnect-btn">重新连接</button>
        </div>
      </div>

      <!-- 系统提示信息 -->
      <div class="video-info-bar">
        <span class="info-item">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"></circle>
            <polyline points="12 6 12 12 16 14"></polyline>
          </svg>
          {{ currentTime }}
        </span>
        <span class="info-item">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
            <circle cx="12" cy="12" r="3"></circle>
          </svg>
          {{ videoLoaded ? '实时预览' : '连接中...' }}
        </span>
        <span class="info-item resolution-info" v-if="videoResolution">
          {{ videoResolution }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, reactive, onMounted, onUnmounted, nextTick } from "vue";
import { useRouter } from "vue-router";
import {
  useCameraSettingStore,
  useDetectionRegionStore,
  useDetectionSettingStore,
  useModelManagementStore,
  useExceptionOutputStore,
} from '@/stores/settingsStore';

const router = useRouter();
const videoPlayer = ref(null);
const videoLoaded = ref(false);
const videoResolution = ref("");
const currentFps = ref("");
const currentFpsValue = ref(0);
const currentTime = ref("");
const networkSpeed = ref("0.0");
const networkStatus = ref("normal");
const errorMessage = ref("");

const JETSON_ENDPOINT_STORAGE_KEY = "jetson_runtime_endpoint";

const getStoredJetsonEndpoint = () => {
  try {
    return JSON.parse(localStorage.getItem(JETSON_ENDPOINT_STORAGE_KEY) || "null");
  } catch {
    return null;
  }
};

const normalizeBaseUrl = (url, fallbackPort) => {
  if (!url) return "";
  try {
    const parsed = new URL(url);
    return `${parsed.protocol}//${parsed.hostname}:${parsed.port || fallbackPort}`;
  } catch {
    return "";
  }
};

const makeEndpoint = (host) => ({
  host,
  label: host === "192.168.55.1" ? "USB TCP" : "LAN TCP",
  api: `http://${host}:5000`,
  stream: `http://${host}:8889`,
});

const storedEndpoint = getStoredJetsonEndpoint();
const storedLanEndpoint = storedEndpoint?.host === "10.10.10.2" ? storedEndpoint : null;
const apiBaseUrl = ref(
  storedLanEndpoint?.api || normalizeBaseUrl(import.meta.env.VITE_FLASK_BACKEND_URL, "5000")
);
const streamBaseUrl = ref(
  storedLanEndpoint?.stream || normalizeBaseUrl(import.meta.env.VITE_VIDEO_STREAM_URL, "8889")
);
const discoveredJetsons = ref([]);
const isScanningJetson = ref(false);
const showJetsonResults = ref(false);
const activeJetsonOnline = ref(false);

let pc = null;

// 监听`设置相机`的返回结果
const cameraSettingStore = useCameraSettingStore()
const detectionSettingStore = useDetectionSettingStore()
const detectionRegionStore = useDetectionRegionStore()
const modelManagementStore = useModelManagementStore()
const exceptionOutputStore = useExceptionOutputStore()

/*
  用于表达各种案件设置的状态
  true:  已启用 -> 绿色
  false: 失败  -> 红色
  null: 默认值 -> 灰色
 */
const cameraState = ref({"active": false, "inactive": false, "unset": true})
const detectionState = ref({"active": false, "inactive": false, "unset": true})
const detectionRegionState = ref({"active": false, "inactive": false, "unset": true})
const modelManagementState = ref({"active": false, "inactive": false, "unset": true})
const exceptionOutputState = ref({"active": false, "inactive": false, "unset": true})

let timeInterval = null;
let speedInterval = null;
let runtimeStatusInterval = null;
let videoFrameCallbackId = null;
let fpsFallbackInterval = null;
let firstFrameTimer = null;
let fpsSample = { frames: 0, time: 0 };

// 重连机制
let reconnectAttempts = 0;
let reconnectTimer = null;
let isConnecting = false;
let manualReconnectVisiable = false;
const MAX_RECONNECT_ATTEMPTS = 60;
const BASE_RECONNECT_DELAY = 1000;
const MAX_RECONNECT_DELAY = 5000;

const activeJetsonLabel = computed(() => {
  try {
    return new URL(apiBaseUrl.value).host;
  } catch {
    return "未连接";
  }
});

const goToCameraSettings = () => {
  router.push("/camera-settings");
};

const goToDetectionSettings = () => {
  router.push("/detection-settings");
};

const goToDetectionRegion = () => {
  router.push("/detection-region");
};

const goToModelManagement = () => {
  router.push("/model-management");
};

const goToExceptionOutput = () => {
  router.push("/exception-output");
};

const updateTime = () => {
  const now = new Date();
  currentTime.value = now.toLocaleTimeString("zh-CN", { 
    hour: "2-digit", 
    minute: "2-digit", 
    second: "2-digit",
    hour12: false 
  });
};

// 模拟网速
const simulateNetworkSpeed = () => {
  const speed = (Math.random() * 3 + 0.5).toFixed(1);
  networkSpeed.value = speed;
  if (parseFloat(speed) > 2.5) {
    networkStatus.value = "good";
  } else if (parseFloat(speed) > 1.0) {
    networkStatus.value = "normal";
  } else {
    networkStatus.value = "poor";
  }
};

const loadFromSaveState = (saveState, curState) => {
  if (saveState) {
    if (saveState.success) {
      curState.value = { active: true, inactive: false, unset: false };
    } else if (saveState.unset) {
      curState.value = { active: false, inactive: false, unset: true };
    } else {
      curState.value = { active: false, inactive: true, unset: false };
    }
  }
};

const formatFps = (value) => {
  const fps = Number(value);
  if (!Number.isFinite(fps) || fps <= 0) return "";
  return `${Math.round(fps)} fps`;
};

const setCurrentFps = (value) => {
  const fps = Number(value);
  if (!Number.isFinite(fps) || fps <= 0) return;
  currentFpsValue.value = fps;
  currentFps.value = formatFps(fps);
};

const currentFpsClass = computed(() => ({
  danger: currentFpsValue.value > 0 && currentFpsValue.value < 10,
}));

const getHostFromUrl = (url) => {
  try {
    return new URL(url).hostname;
  } catch {
    return "";
  }
};

const buildJetsonCandidates = () => {
  const hosts = new Set();
  const addHost = (host) => {
    if (/^(\d{1,3}\.){3}\d{1,3}$/.test(host)) hosts.add(host);
  };

  addHost(getHostFromUrl(apiBaseUrl.value));
  addHost(getHostFromUrl(import.meta.env.VITE_FLASK_BACKEND_URL));
  addHost("10.10.10.2");

  const pageHost = window.location.hostname;
  if (pageHost.startsWith("10.10.10.")) addHost(pageHost);

  const subnetPrefixes = new Set(["10.10.10"]);
  const pageMatch = pageHost.match(/^(\d{1,3}\.\d{1,3}\.\d{1,3})\.\d{1,3}$/);
  if (pageMatch) subnetPrefixes.add(pageMatch[1]);

  for (const prefix of subnetPrefixes) {
    for (let i = 1; i <= 254; i += 1) {
      hosts.add(`${prefix}.${i}`);
    }
  }

  return Array.from(hosts).map(makeEndpoint);
};

const probeJetson = async (endpoint, timeoutMs = 700) => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(`${endpoint.api}/api/runtime/status`, {
      method: "GET",
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok) return null;

    const payload = await response.json();
    if (payload.status !== "success") return null;

    return {
      ...endpoint,
      camera: payload.data?.camera,
      streamStatus: (payload.data?.streams || []).find((item) => item.name === "cam_high"),
    };
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
};

const applyJetsonEndpoint = async (device, reconnectNow = true) => {
  apiBaseUrl.value = device.api;
  streamBaseUrl.value = device.stream;
  activeJetsonOnline.value = true;
  showJetsonResults.value = false;

  localStorage.setItem(
    JETSON_ENDPOINT_STORAGE_KEY,
    JSON.stringify({
      api: device.api,
      stream: device.stream,
      host: device.host,
      label: device.label,
    })
  );

  const source = device.streamStatus || device.camera;
  if (source?.width && source?.height) {
    videoResolution.value = `${source.width}x${source.height}`;
  }

  if (reconnectNow) {
    reconnectAttempts = 0;
    manualReconnectVisiable = false;
    await reconnect();
  }
};

const scanJetsons = async () => {
  if (isScanningJetson.value) return;

  isScanningJetson.value = true;
  showJetsonResults.value = false;
  discoveredJetsons.value = [];

  const candidates = buildJetsonCandidates();
  const found = [];
  const batchSize = 24;

  for (let i = 0; i < candidates.length; i += batchSize) {
    const batch = candidates.slice(i, i + batchSize);
    const results = await Promise.all(batch.map((endpoint) => probeJetson(endpoint)));

    for (const result of results) {
      if (result && !found.some((item) => item.host === result.host)) {
        found.push(result);
        discoveredJetsons.value = [...found];
      }
    }
  }

  isScanningJetson.value = false;
  showJetsonResults.value = true;

  if (found.length) {
    const preferred =
      found.find((item) => item.host === "10.10.10.2") ||
      found.find((item) => item.host === getHostFromUrl(apiBaseUrl.value)) ||
      found[0];
    await applyJetsonEndpoint(preferred, !videoLoaded.value);
  }
};

const selectJetson = async (device) => {
  await applyJetsonEndpoint(device, true);
};

const connectPreferredDevice = async () => {
  const candidates = [];
  const addCandidate = (endpoint) => {
    if (!endpoint?.host) return;
    if (!candidates.some((item) => item.host === endpoint.host)) {
      candidates.push(endpoint);
    }
  };

  addCandidate(makeEndpoint("10.10.10.2"));
  addCandidate(makeEndpoint(getHostFromUrl(import.meta.env.VITE_FLASK_BACKEND_URL)));
  addCandidate(makeEndpoint(getHostFromUrl(apiBaseUrl.value)));

  for (const candidate of candidates) {
    const device = await probeJetson(candidate, 1000);
    if (device) {
      await applyJetsonEndpoint(device, false);
      return true;
    }
  }

  return false;
};

const syncRuntimeStreamStatus = async () => {
  if (!apiBaseUrl.value) return;

  try {
    const response = await fetch(`${apiBaseUrl.value}/api/runtime/status`, {
      method: "GET",
      cache: "no-store",
    });
    const payload = await response.json();
    if (!response.ok || payload.status !== "success") {
      activeJetsonOnline.value = false;
      return;
    }

    activeJetsonOnline.value = true;

    const highStream = (payload.data?.streams || []).find((stream) => stream.name === "cam_high");
    const camera = payload.data?.camera;
    const source = highStream || camera;
    if (!source) return;

    if (source.width && source.height) {
      videoResolution.value = `${source.width}x${source.height}`;
    }

    if (!videoLoaded.value && !isConnecting && !reconnectTimer) {
      reconnectAttempts = Math.min(reconnectAttempts, 3);
      scheduleReconnect();
    }

  } catch {
    activeJetsonOnline.value = false;
    // Keep the last known display value when runtime status is temporarily unavailable.
  }
};

const startFpsMonitor = () => {
  const video = videoPlayer.value;
  if (!video) return;

  stopFpsMonitor();

  fpsSample = { frames: 0, time: 0 };

  if (typeof video.requestVideoFrameCallback !== "function") {
    fpsFallbackInterval = setInterval(() => {
      if (typeof video.getVideoPlaybackQuality !== "function") return;

      const quality = video.getVideoPlaybackQuality();
      const frames = Number(quality.totalVideoFrames || 0);
      const time = performance.now();

      if (fpsSample.frames > 0 && time > fpsSample.time) {
        const deltaFrames = frames - fpsSample.frames;
        const deltaTime = (time - fpsSample.time) / 1000;
        if (deltaFrames >= 0 && deltaTime > 0) {
          setCurrentFps(deltaFrames / deltaTime);
        }
      }

      fpsSample = { frames, time };
    }, 1000);
    return;
  }

  const update = (_now, metadata) => {
    const frames = Number(metadata.presentedFrames || 0);
    const time = performance.now();

    if (fpsSample.frames && time > fpsSample.time) {
      const deltaFrames = frames - fpsSample.frames;
      const deltaTime = (time - fpsSample.time) / 1000;
      if (deltaTime >= 0.8 && deltaFrames > 0) {
        setCurrentFps(deltaFrames / deltaTime);
        fpsSample = { frames, time };
      }
    } else {
      fpsSample = { frames, time };
    }

    videoFrameCallbackId = video.requestVideoFrameCallback(update);
  };

  videoFrameCallbackId = video.requestVideoFrameCallback(update);
};

const stopFpsMonitor = () => {
  const video = videoPlayer.value;
  if (
    video &&
    videoFrameCallbackId !== null &&
    typeof video.cancelVideoFrameCallback === "function"
  ) {
    video.cancelVideoFrameCallback(videoFrameCallbackId);
  }
  videoFrameCallbackId = null;
  if (fpsFallbackInterval) {
    clearInterval(fpsFallbackInterval);
    fpsFallbackInterval = null;
  }
  fpsSample = { frames: 0, time: 0 };
};

// 关闭现有连接
const closeWebRTC = () => {
  stopFpsMonitor();
  if (firstFrameTimer) {
    clearTimeout(firstFrameTimer);
    firstFrameTimer = null;
  }
  const video = videoPlayer.value;
  if (video) {
    video.onloadedmetadata = null;
    video.onplaying = null;
    video.pause();
    video.srcObject = null;
  }
  if (pc) {
    pc.ontrack = null;
    pc.onconnectionstatechange = null;
    pc.close();
    pc = null;
  }
  videoLoaded.value = false;
};

// 触发重连（带退避）
const scheduleReconnect = () => {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
    errorMessage.value = '连接失败，请刷新页面后再次尝试连接或手动重连.';

    manualReconnectVisiable = true;
    return;
  }
  const delay = Math.min(BASE_RECONNECT_DELAY * Math.pow(2, reconnectAttempts), MAX_RECONNECT_DELAY);
  reconnectTimer = setTimeout(() => {
    reconnect();
  }, delay);
};

// 实际执行重连
const reconnect = async () => {
  if (isConnecting) return;
  isConnecting = true;
  closeWebRTC();
  try {
    await initWebRTC();

    // 连接成功
    reconnectAttempts = 0;
    manualReconnectVisiable = false;
  } catch (err) {
    reconnectAttempts++;
    scheduleReconnect();
  } finally {
    isConnecting = false;
  }
};

// 处理连接失败（网络断开 or 远端错误）
const handleConnectionFailed = () => {
  if (videoLoaded.value === false && reconnectAttempts === 0) {
    // 初次失败立即开始重连
    scheduleReconnect();
  } else if (videoLoaded.value === true) {
    // 原本连接正常，突然断开
    videoLoaded.value = false;
    errorMessage.value = '视频流中断，正在重连...';
    scheduleReconnect();
  }
};

// ---------- WebRTC 初始化 ----------
const initWebRTC = async () => {
  if (!videoPlayer.value) return;
  // 先关闭可能存在的旧连接
  closeWebRTC();

  try {
    // 创建 RTCPeerConnection
    pc = new RTCPeerConnection({
      iceServers: []
    });

    // 添加只接收视频的 Transceiver
    pc.addTransceiver("video", { direction: "recvonly" });

    // 当接收到远程视频轨道时，附加到 video 元素
    pc.ontrack = (event) => {
      if (event.track.kind === "video") {
        const stream = new MediaStream([event.track]);
        const video = videoPlayer.value;
        video.srcObject = stream;
        errorMessage.value = "等待视频画面...";
        currentFps.value = "";
        currentFpsValue.value = 0;

        const markVideoReady = () => {
          if (firstFrameTimer) {
            clearTimeout(firstFrameTimer);
            firstFrameTimer = null;
          }
          videoLoaded.value = true;
          errorMessage.value = "";
          startFpsMonitor();
        };

        video.onloadedmetadata = () => {
          if (video.videoWidth && video.videoHeight) {
            videoResolution.value = `${video.videoWidth}x${video.videoHeight}`;
          }
          video.play().catch(() => {});
        };
        video.onplaying = markVideoReady;

        firstFrameTimer = setTimeout(() => {
          if (!videoLoaded.value) {
            errorMessage.value = "视频画面未返回，正在重连...";
            handleConnectionFailed();
          }
        }, 10000);

        video.play().catch(() => {});

        // 监听分辨率变化（当视频元数据加载后）
        event.track.onunmute = () => {
          setTimeout(() => {
            const settings = event.track.getSettings();
            if (settings.width && settings.height) {
              videoResolution.value = `${settings.width}x${settings.height}`;
            }
          }, 500);
        };
      }
    };

    // 创建 Offer（SDP）
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);

    // 等待 ICE 候选收集完成（一次性发送，避免 Trickle ICE 复杂度）
    await new Promise(resolve => {
      if (pc.iceGatheringState === "complete") {
        resolve();
      } else {
        pc.onicegatheringstatechange = () => {
          if (pc.iceGatheringState === "complete") resolve();
        };
      }
    });

    // 发送 Offer SDP 到 WHEP 端点
    const response = await fetch(`${streamBaseUrl.value}/cam_high/whep`, {
      method: "POST",
      headers: { "Content-Type": "application/sdp" },
      body: pc.localDescription.sdp
    });

    if (!response.ok) {
      throw new Error(`WHEP 请求失败: ${response.status}`);
    }

    // 获取 Answer SDP
    const answerSDP = await response.text();
    await pc.setRemoteDescription(new RTCSessionDescription({
      type: "answer",
      sdp: answerSDP
    }));

    // 监听连接状态
    pc.onconnectionstatechange = () => {
      if (!pc) return;
      const state = pc.connectionState;

      if (state === 'failed' || state === 'disconnected') {
        handleConnectionFailed();
      } else if (state === 'connected') {
        // 连接恢复时重置重试次数
        reconnectAttempts = 0;
        if (reconnectTimer) {
          clearTimeout(reconnectTimer);
          reconnectTimer = null;
        }
      }
    };

  } catch (err) {
    console.error("WebRTC 初始化失败:", err);
    videoLoaded.value = false;
    errorMessage.value = "WebRTC 连接失败";

    // 尝试重连
    closeWebRTC();
    throw err;
  }
};

// 手动重连
const manualReconnect = () => {
  if (isConnecting) return;

  // 重置重试计数，立即重连
  reconnectAttempts = 0;
  if (reconnectTimer) clearTimeout(reconnectTimer);
  reconnect();
};

onMounted(async () => {
  updateTime();
  timeInterval = setInterval(updateTime, 1000);
  speedInterval = setInterval(simulateNetworkSpeed, 2000);

  await nextTick();
  // initWebRTC();

  const saveCameraState = cameraSettingStore.getState();
  const saveDetectionState = detectionSettingStore.getState();
  const saveDetectionRegionState = detectionRegionStore.getState();
  const saveModelManagementState = modelManagementStore.getState();
  const saveExceptionOutputState = exceptionOutputStore.getState();
  loadFromSaveState(saveCameraState, cameraState);
  loadFromSaveState(saveDetectionState, detectionState);
  loadFromSaveState(saveDetectionRegionState, detectionRegionState);
  loadFromSaveState(saveModelManagementState, modelManagementState);
  loadFromSaveState(saveExceptionOutputState, exceptionOutputState);

  await connectPreferredDevice();
  reconnect();
  syncRuntimeStreamStatus();
  runtimeStatusInterval = setInterval(syncRuntimeStreamStatus, 3000);

  // 尝试获取设置的分辨率值
  const saveCameraSettings = cameraSettingStore.getSettings();
  if (!videoResolution.value && saveCameraSettings.resolution) {
    videoResolution.value = `${saveCameraSettings.resolution}`;
  }
});

onUnmounted(() => {
  clearInterval(timeInterval);
  clearInterval(speedInterval);
  if (runtimeStatusInterval) clearInterval(runtimeStatusInterval);
  if (reconnectTimer) clearTimeout(reconnectTimer);
  closeWebRTC();
});
</script>

<style scoped>
.monitor-page {
  width: 100%;
  height: calc(100vh - var(--topbar-height));
  min-height: 620px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px;
  overflow: hidden;
  background: transparent;
}

.operation-bar {
  position: relative;
  min-height: 58px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 10px 14px 10px 18px;
  background: var(--industrial-surface);
  border: 1px solid var(--industrial-border);
  border-radius: var(--industrial-radius);
  box-shadow: var(--industrial-shadow);
  flex-shrink: 0;
}

.operation-bar::before {
  content: "";
  position: absolute;
  left: 0;
  top: 12px;
  bottom: 12px;
  width: 3px;
  border-radius: 0 999px 999px 0;
  background: var(--industrial-red);
}

.operation-bar-left,
.operation-bar-right,
.page-title-group,
.operation-actions,
.status-indicator,
.info-item {
  display: flex;
  align-items: center;
}

.operation-bar-left {
  min-width: 0;
}

.operation-bar-right {
  flex-shrink: 0;
  gap: 12px;
}

.page-title {
  margin: 0;
  color: var(--industrial-text);
  font-size: 18px;
  font-weight: 800;
  letter-spacing: 0;
  flex-shrink: 0;
}

.page-title::after {
  content: "实时视觉检测";
  display: block;
  margin-top: 2px;
  color: var(--industrial-faint);
  font-size: 12px;
  font-weight: 600;
}

.page-title-group {
  position: relative;
  gap: 12px;
  min-width: 0;
}

.jetson-discovery {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.jetson-scan-btn {
  height: 30px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0 10px;
  color: var(--industrial-success);
  background: var(--industrial-success-soft);
  border: 1px solid rgba(47, 133, 90, 0.24);
  border-radius: var(--industrial-radius-sm);
  font-size: 12px;
  font-weight: 800;
  cursor: pointer;
  box-shadow: var(--industrial-shadow);
}

.jetson-scan-btn:disabled {
  cursor: wait;
  opacity: 0.78;
}

.scan-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--industrial-success);
}

.scan-dot.scanning {
  animation: scan-pulse 0.8s ease-in-out infinite;
}

.jetson-current {
  max-width: 170px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  color: var(--industrial-muted);
  font-family: "Roboto Mono", Consolas, monospace;
  font-size: 12px;
  font-weight: 700;
}

.jetson-current.online {
  color: var(--industrial-success);
}

.jetson-results {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  z-index: 20;
  min-width: 220px;
  display: grid;
  gap: 6px;
  padding: 8px;
  background: #ffffff;
  border: 1px solid var(--industrial-border);
  border-radius: var(--industrial-radius-sm);
  box-shadow: var(--industrial-shadow-hover);
}

.jetson-result {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 30px;
  padding: 0 8px;
  color: var(--industrial-muted);
  background: var(--industrial-surface-subtle);
  border: 1px solid transparent;
  border-radius: var(--industrial-radius-sm);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.jetson-result:hover {
  color: var(--industrial-success);
  background: var(--industrial-success-soft);
  border-color: rgba(47, 133, 90, 0.18);
}

.jetson-result strong {
  color: inherit;
  font-family: "Roboto Mono", Consolas, monospace;
}

@keyframes scan-pulse {
  0%,
  100% {
    transform: scale(1);
    opacity: 0.55;
  }
  50% {
    transform: scale(1.45);
    opacity: 1;
  }
}

.operation-actions {
  gap: 8px;
  flex-wrap: wrap;
}

.operation-btn {
  width: 38px;
  height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  color: var(--industrial-muted);
  background: var(--industrial-surface-subtle);
  border: 1px solid var(--industrial-border);
  border-radius: var(--industrial-radius-sm);
  cursor: pointer;
  box-shadow: var(--industrial-shadow);
}

.operation-btn:hover {
  color: var(--industrial-red-dark);
  background: var(--industrial-red-soft);
  border-color: rgba(185, 28, 28, 0.25);
  box-shadow: var(--industrial-shadow-hover);
}

.operation-btn.active {
  color: var(--industrial-success);
  background: var(--industrial-success-soft);
  border-color: rgba(47, 133, 90, 0.28);
}

.operation-btn.inactive {
  color: var(--industrial-danger);
  background: var(--industrial-danger-soft);
  border-color: rgba(197, 48, 48, 0.3);
}

.operation-btn.unset {
  color: var(--industrial-muted);
  background: #f3f5f7;
}

.status-indicator {
  gap: 7px;
  min-height: 32px;
  padding: 0 10px;
  color: var(--industrial-muted);
  background: var(--industrial-surface-subtle);
  border: 1px solid var(--industrial-border);
  border-radius: var(--industrial-radius-sm);
  font-size: 12px;
  font-weight: 700;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--industrial-success);
}

.status-indicator.poor .status-dot {
  background: var(--industrial-danger);
}

.status-indicator.normal .status-dot {
  background: var(--industrial-warning);
}

.fps-indicator {
  color: var(--industrial-success);
  background: var(--industrial-success-soft);
  border-color: rgba(47, 133, 90, 0.22);
}

.fps-indicator .status-dot {
  background: var(--industrial-success);
}

.fps-indicator.danger {
  color: var(--industrial-danger);
  background: var(--industrial-danger-soft);
  border-color: rgba(197, 48, 48, 0.24);
}

.fps-indicator.danger .status-dot {
  background: var(--industrial-danger);
}

.camera-view-area {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--industrial-surface);
  border: 1px solid var(--industrial-border);
  border-radius: var(--industrial-radius);
  box-shadow: var(--industrial-shadow-hover);
}

.video-container {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: auto;
  background:
    linear-gradient(90deg, rgba(143, 17, 23, 0.055) 1px, transparent 1px),
    linear-gradient(180deg, rgba(31, 41, 51, 0.045) 1px, transparent 1px),
    #ffffff;
  background-size: 32px 32px;
}

.video-player {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: transparent;
}

.video-placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 24px;
  color: var(--industrial-muted);
  text-align: center;
  background: #ffffff;
}

.video-placeholder p {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
}

.video-info-bar {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 9px 14px;
  color: var(--industrial-muted);
  background: #ffffff;
  border-top: 1px solid var(--industrial-border);
  font-size: 12px;
  flex-shrink: 0;
  flex-wrap: wrap;
}

.info-item {
  gap: 5px;
  min-height: 24px;
  padding: 0 8px;
  border-radius: 999px;
  background: var(--industrial-success-soft);
  color: var(--industrial-success);
}

.resolution-info {
  color: var(--industrial-success);
  font-family: "Roboto Mono", Consolas, monospace;
  font-weight: 700;
}

.reconnect-btn {
  margin-top: 8px;
  min-height: 34px;
  padding: 0 14px;
  color: #ffffff;
  background: var(--industrial-red);
  border: 1px solid var(--industrial-red);
  border-radius: var(--industrial-radius-sm);
  cursor: pointer;
}

.reconnect-btn:hover {
  background: var(--industrial-red-dark);
  border-color: var(--industrial-red-dark);
}

@media (max-width: 768px) {
  .monitor-page {
    padding: 12px;
    gap: 12px;
  }

  .operation-bar {
    align-items: flex-start;
    flex-direction: column;
  }

  .operation-bar-right {
    width: 100%;
    justify-content: space-between;
    flex-wrap: wrap;
  }
}

@media (max-width: 480px) {
  .status-text {
    display: none;
  }
}
</style>
