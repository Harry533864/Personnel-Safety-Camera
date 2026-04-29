<template>
  <div class="monitor-page">
    <!-- Camera Operation Bar -->
    <div class="operation-bar">
      <div class="operation-bar-left">
        <button 
          class="operation-btn" 
          :class="{ active: cameraState.active, inactive: cameraState.inactive, unset: cameraState.unset }"
          @click="goToCameraSettings"
          title="相机设置"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path>
            <circle cx="12" cy="13" r="4"></circle>
          </svg>
          <span class="btn-label">相机设置</span>
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
          <span class="btn-label">检测设置</span>
        </button>
      </div>

      <div class="operation-bar-right">
        <div class="status-indicator" :class="networkStatus">
          <span class="status-dot"></span>
          <span class="status-text">{{ networkSpeed }} MB/s</span>
        </div>
      </div>
    </div>

    <!-- 相机画面预览 -->
    <div class="camera-view-area">
      <div class="video-container" ref="videoContainer">
        <!-- ✅ WebRTC 视频播放：使用 ref 获取 DOM，手动设置 srcObject -->
        <video
          v-show="videoLoaded"
          ref="videoPlayer"
          class="video-player"
          autoplay
          muted
          playsinline
        ></video>

        <!-- 检测区域叠加层 -->
        <div class="detection-overlay" v-if="showDetectionOverlay && videoLoaded">
          <div class="region-marker" style="left: 20%; top: 30%; width: 25%; height: 30%;">
            <span class="region-label">检测区域 1</span>
          </div>
        </div>

        <!-- Placeholder when no video -->
        <div class="video-placeholder" v-if="!videoLoaded">
          <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" opacity="0.3">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
            <circle cx="8.5" cy="8.5" r="1.5"></circle>
            <polyline points="21 15 16 10 5 21"></polyline>
          </svg>
          <p>{{ errorMessage || '视频加载中...' }}</p>
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
import { ref, onMounted, onUnmounted, nextTick } from "vue";
import { useRouter } from "vue-router";
import Hls from "hls.js";
import { useCameraSettingStore, useDetectionSettingStore } from '@/stores/settingsStore';

const router = useRouter();
const videoPlayer = ref(null);
const videoLoaded = ref(false);
const videoResolution = ref("");
const currentTime = ref("");
const showDetectionOverlay = ref(false);
const networkSpeed = ref("0.0");
const networkStatus = ref("normal");
const errorMessage = ref("");

// ---------- HLS 配置 ----------
const HLS_URL = "http://192.168.0.102:8080/stream.m3u8"; // 与推流电脑 IP 一致
let hls = null;

// 监听`设置相机`的返回结果
const cameraSettingStore = useCameraSettingStore()
const detectionSettingStore = useDetectionSettingStore()

/*
  用于表达各种案件设置的状态
  true:  已启用 -> 绿色
  false: 失败  -> 红色
  null: 默认值 -> 灰色
 */
// const saveCameraState = reactive(cameraSettingStore.getState());
const cameraState = ref({"active": false, "inactive": false, "unset": true})
const detectionState = ref({"active": false, "inactive": false, "unset": true})

// 状态持久化

let timeInterval = null;
let speedInterval = null;

const goToCameraSettings = () => {
  router.push("/camera-settings");
};

const goToDetectionSettings = () => {
  router.push("/detection-settings");
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

const initHls = () => {
  if (!videoPlayer.value) return;

  const video = videoPlayer.value;

  // 判断浏览器是否原生支持 HLS (如 Safari)
  if (video.canPlayType("application/vnd.apple.mpegurl")) {
    video.src = HLS_URL;
    video.addEventListener("loadedmetadata", () => {
      videoLoaded.value = true;
      errorMessage.value = "";
      videoResolution.value = `${video.videoWidth}x${video.videoHeight}`;
    });
    video.addEventListener("error", (e) => {
      console.error("视频错误", e);
      videoLoaded.value = false;
      errorMessage.value = "视频源加载失败";
    });
  }
  // 其他浏览器使用 hls.js
  else if (Hls.isSupported()) {
    hls = new Hls({
      enableWorker: true,
      lowLatencyMode: false,   // 可根据需要开启低延迟
      backBufferLength: 90      // 保持一定回放缓冲区
    });
    hls.loadSource(HLS_URL);
    hls.attachMedia(video);

    hls.on(Hls.Events.MANIFEST_PARSED, () => {
      videoLoaded.value = true;
      errorMessage.value = "";
      video.play().catch(e => console.warn("自动播放受限:", e));
    });

    hls.on(Hls.Events.ERROR, (event, data) => {
      if (data.fatal) {
        switch (data.type) {
          case Hls.ErrorTypes.NETWORK_ERROR:
            errorMessage.value = "网络错误，正在尝试重连...";
            hls.startLoad();
            break;
          case Hls.ErrorTypes.MEDIA_ERROR:
            errorMessage.value = "媒体错误，尝试恢复...";
            hls.recoverMediaError();
            break;
          default:
            errorMessage.value = "HLS 加载失败";
            videoLoaded.value = false;
            break;
        }
      }
    });
  }
  // 完全不支持 HLS
  else {
    errorMessage.value = "当前浏览器不支持播放视频流";
  }
};

const checkResolution = () => {
  const video = videoPlayer.value;
  if (video && video.videoWidth && video.videoHeight) {
    videoResolution.value = `${video.videoWidth}x${video.videoHeight}`;
  }
};

onMounted(async () => {
  updateTime();
  timeInterval = setInterval(updateTime, 1000);
  speedInterval = setInterval(simulateNetworkSpeed, 2000);
//   resolutionInterval = setInterval(checkResolution, 1000);

  // 等待 DOM 渲染后初始化 HLS
  await nextTick();
  initHls();
});

onUnmounted(() => {
  if (timeInterval) clearInterval(timeInterval);
  if (speedInterval) clearInterval(speedInterval);
//   if (resolutionInterval) clearInterval(resolutionInterval);

  // 销毁 hls 实例
  if (hls) {
    hls.destroy();
    hls = null;
  }
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
  gap: 8px;
  flex-wrap: wrap;
}

.operation-bar-right {
  flex-shrink: 0;
}

.operation-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: #21262d;
  border: 1px solid #30363d;
  border-radius: 6px;
  color: #8b949e;
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
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

.btn-label {
  display: inline;
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
  overflow: hidden;
}

.video-player {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.detection-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  pointer-events: none;
}

.region-marker {
  position: absolute;
  border: 2px solid #3fb950;
  background: rgba(63, 185, 80, 0.1);
  border-radius: 4px;
}

.region-label {
  position: absolute;
  top: -20px;
  left: 0;
  background: #3fb950;
  color: #000;
  padding: 2px 6px;
  font-size: 0.7rem;
  border-radius: 3px;
  white-space: nowrap;
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

@media (max-width: 768px) {
  .operation-bar {
    padding: 6px 10px;
  }
  
  .btn-label {
    display: none;
  }
  
  .operation-btn {
    padding: 6px;
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
  
  .operation-bar-right {
    display: none;
  }
}
</style>