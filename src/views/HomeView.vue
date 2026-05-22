<template>
  <div class="monitor-page">
    <div class="operation-bar">
      <div class="operation-bar-left">
        <div class="page-title-group">
          <h2 class="page-title">相机页面</h2>
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
const currentTime = ref("");
const networkSpeed = ref("0.0");
const networkStatus = ref("normal");
const errorMessage = ref("");

// WebRTC 相关
const STREAM_URL = import.meta.env.VITE_VIDEO_STREAM_URL
const MEDIAMTX_WHEP_URL = `${STREAM_URL}/cam_high/whep`;   // 推流电脑 IP，使用时修改
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

// 重连机制
let reconnectAttempts = 0;
let reconnectTimer = null;
let isConnecting = false;
let manualReconnectVisiable = false;
const MAX_RECONNECT_ATTEMPTS = 5;
const BASE_RECONNECT_DELAY = 1000;

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

// 关闭现有连接
const closeWebRTC = () => {
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
  const delay = BASE_RECONNECT_DELAY * Math.pow(2, reconnectAttempts);
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
    errorMessage.value = '';
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
      iceServers: [{ urls: "stun:stun.l.google.com:19302" }]  // 可加 TURN
    });

    // 添加只接收视频的 Transceiver
    pc.addTransceiver("video", { direction: "recvonly" });

    // 当接收到远程视频轨道时，附加到 video 元素
    pc.ontrack = (event) => {
      if (event.track.kind === "video") {
        const stream = new MediaStream([event.track]);
        videoPlayer.value.srcObject = stream;
        videoLoaded.value = true;
        errorMessage.value = "";

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
    const response = await fetch(MEDIAMTX_WHEP_URL, {
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
    handleConnectionFailed();
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

  initWebRTC();

  // 尝试获取设置的分辨率值
  const saveCameraSettings = cameraSettingStore.getSettings();
  if (!videoResolution.value && saveCameraSettings.resolution) {
    videoResolution.value = `${saveCameraSettings.resolution}`;
  }
});

onUnmounted(() => {
  clearInterval(timeInterval);
  clearInterval(speedInterval);
  if (reconnectTimer) clearTimeout(reconnectTimer);
  closeWebRTC();
});
</script>

<style scoped>
.monitor-page {
  width: 100%;
  height: calc(100vh - 56px);
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: #0d1117;
  overflow: hidden;
  margin: 0;
  padding: 0;
}

.operation-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 16px;
  background: #161b22;
  border-bottom: 1px solid #30363d;
  flex-shrink: 0;
  gap: 16px;
}

.operation-bar-left {
  display: flex;
  align-items: center;
  min-width: 0;
}

.operation-bar-right {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-title-group {
  display: flex;
  align-items: center;
}

.page-title {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  color: #e6edf3;
}

.operation-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.operation-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 36px;
  padding: 0;
  background: #21262d;
  border: 1px solid #30363d;
  border-radius: 6px;
  color: #8b949e;
  cursor: pointer;
  transition: all 0.2s;
}

.operation-btn:hover {
  background: #30363d;
  color: #c9d1d9;
  border-color: #8b949e;
}

.operation-btn.active {
  background: #238636;
  color: #ffffff;
  border-color: #238636;
}

.operation-btn.inactive {
  background: #f5030f;
  color: #ffffff;
  border-color: #f5030f;
}

.operation-btn.unset {
  background: #525151ef;
  color: #ffffff;
  border-color: #525151ef;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 0.8rem;
  color: #8b949e;
  background: #21262d;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #3fb950;
  animation: pulse 2s infinite;
}

.status-indicator.poor .status-dot {
  background: #f85149;
}

.status-indicator.normal .status-dot {
  background: #d29922;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.camera-view-area {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
  background: #000;
}

.video-container {
  flex: 1;
  min-height: 0;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: auto;
}

.video-player {
  display: block;
}

.video-placeholder {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #8b949e;
  gap: 12px;
  text-align: center;
  padding: 20px;
  background: #0d1117;
}

.video-placeholder p {
  margin: 0;
  font-size: 0.9rem;
}

.video-info-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 6px 16px;
  background: #161b22;
  border-top: 1px solid #30363d;
  font-size: 0.8rem;
  color: #8b949e;
  flex-shrink: 0;
  flex-wrap: wrap;
}

.info-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.resolution-info {
  color: #58a6ff;
  font-weight: 500;
}

.reconnect-btn {
  margin-top: 12px;
  padding: 6px 12px;
  background: #238636;
  border: none;
  border-radius: 6px;
  color: white;
  cursor: pointer;
}
.reconnect-btn:hover {
  background: #2ea043;
}

@media (max-width: 768px) {
  .operation-bar {
    padding: 6px 10px;
  }

  .operation-btn {
    width: 36px;
    height: 34px;
  }

  .video-info-bar {
    padding: 4px 10px;
    gap: 10px;
  }
}

@media (max-width: 480px) {
  .status-text {
    display: none;
  }

  .operation-bar {
    gap: 10px;
  }

  .operation-bar-right {
    gap: 8px;
  }
}
</style>
