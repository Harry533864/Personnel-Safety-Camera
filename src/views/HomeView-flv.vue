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
     <!-- 去掉了`controls`和`loop`属性 -->
    <div class="camera-view-area">
      <div class="video-container" ref="videoContainer">
        <video 
          ref="videoPlayer"
          class="video-player"
          autoplay
          muted
          playsinline
        ></video>
        
        <!-- 检测区域叠加层 -->
        <div class="detection-overlay" v-if="showDetectionOverlay">
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
          <p>请检查摄像头！</p>
          <!-- <p class="hint">或点击上方按钮进行设置</p> -->
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
          实时预览
        </span>
        <span class="info-item resolution-info" v-if="videoResolution">
          {{ videoResolution }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import flvjs from 'flv.js';
import { ref, onMounted, onUnmounted, watch } from "vue";
import { useRouter } from "vue-router";
import { useCameraSettingStore, useDetectionSettingStore } from '@/stores/settingsStore';

const router = useRouter();
const videoPlayer = ref(null);
const videoContainer = ref(null);
const videoLoaded = ref(false);
const videoResolution = ref("");
const currentTime = ref("");
const showDetectionOverlay = ref(false);
const networkSpeed = ref("0.0");
const networkStatus = ref("normal");

// 接收视频流
let flvPlayer = null;
const flvUrl = 'http://192.168.0.102:8888/live/stream.flv';
const errorMessage = ref("");

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

// 初始化 FLV 播放器
const initFlvPlayer = () => {
  const videoEl = videoPlayer.value;
  if (!videoEl) return;

  // 清理旧实例
  destroyFlvPlayer();

  if (!flvjs.isSupported()) {
    errorMessage.value = "当前浏览器不支持 FLV 播放";
    console.error('flv.js is not supported');
    return;
  }

  try {
    flvPlayer = flvjs.createPlayer({
      type: 'flv',
      url: flvUrl,
      isLive: true,
      cors: true,
      enableWorker: true,
      enableStashBuffer: false,
      stashInitialSize: 128,
      lazyLoad: false,
      lazyLoadMaxDuration: 0,
      seekType: 'range',
    });

    flvPlayer.on(flvjs.Events.MEDIA_INFO, (mediaInfo) => {
      console.log('FLV Media Info:', mediaInfo);
      if (mediaInfo.width && mediaInfo.height) {
        videoResolution.value = `${mediaInfo.width}x${mediaInfo.height}`;
      }
    });

    flvPlayer.on(flvjs.Events.LOADING_COMPLETE, () => {
      console.log('FLV loading complete');
    });

    flvPlayer.on(flvjs.Events.RENDERED_FRAME, () => {
      videoLoaded.value = true;
      errorMessage.value = "";
      console.log('First frame rendered');
    });

    flvPlayer.on(flvjs.Events.ERROR, (errorType, errorDetail, errorInfo) => {
      console.error('FLV Player Error:', errorType, errorDetail, errorInfo);
      videoLoaded.value = false;
      errorMessage.value = `播放错误: ${errorType}`;
      
      // 自动重连
      if (reconnectTimer) clearTimeout(reconnectTimer);
      reconnectTimer = setTimeout(() => {
        console.log('尝试重新连接...');
        initFlvPlayer();
      }, 3000);
    });

    flvPlayer.attachMediaElement(videoEl);
    flvPlayer.load();
    flvPlayer.play();

  } catch (err) {
    console.error('初始化 FLV 播放器失败:', err);
    errorMessage.value = "播放器初始化失败";
    videoLoaded.value = false;
  }
};

// 销毁 FLV 播放器
const destroyFlvPlayer = () => {
  if (flvPlayer) {
    flvPlayer.pause();
    flvPlayer.unload();
    flvPlayer.detachMediaElement();
    flvPlayer.destroy();
    flvPlayer = null;
  }
};

// watch(
//   () => cameraSettingStore.lastSaveResult,
//   (newResult) => {
//     if (newResult) {
//       if (newResult.success) {
//         cameraState.value = { active: true, inactive: false, unset: false };
//         console.log('后端设置成功...');
//       } else {
//         cameraState.value = { active: false, inactive: true, unset: false };
//         console.error('后端设置失败', newResult.message);
//       }
//       cameraSettingStore.clearResult();
//     }
//   },

//   { immediate: true }
// );

// watch(
//   () => detectionSettingStore.lastSaveResult,
//   (newResult) => {
//     if (newResult) {
//       if (newResult.success) {
//         detectionState.value = { active: true, inactive: false, unset: false };
//         console.log('后端设置成功...');
//       } else {
//         detectionState.value = { active: false, inactive: true, unset: false };
//         console.error('后端设置失败', newResult.message);
//       }
//       detectionSettingStore.clearResult();
//     }
//   },

//   { immediate: true }
// );

onMounted(() => {
  updateTime();
  timeInterval = setInterval(updateTime, 1000);
  speedInterval = setInterval(simulateNetworkSpeed, 2000);

//   初始化 FLV 播放器
  initFlvPlayer();

  if (videoPlayer.value) {
    videoPlayer.value.addEventListener("loadeddata", () => {
      if (!flvPlayer) { // 仅当没有 FLV 播放器时
        videoLoaded.value = true;
        const w = videoPlayer.value.videoWidth;
        const h = videoPlayer.value.videoHeight;
        if (w && h) {
          videoResolution.value = `${w}x${h}`;
        }
      }
    });
    
    videoPlayer.value.addEventListener("error", () => {
      if (!flvPlayer) {
        videoLoaded.value = false;
      }
    });
  }
  
// //   检查视频是否正常播放
//   if (videoPlayer.value) {
//     videoPlayer.value.addEventListener("loadeddata", () => {
//       videoLoaded.value = true;
//       const w = videoPlayer.value.videoWidth;
//       const h = videoPlayer.value.videoHeight;
//       if (w && h) {
//         videoResolution.value = `${w}x${h}`;
//       }
//     });
    
//     videoPlayer.value.addEventListener("error", () => {
//       videoLoaded.value = false;
//     });
//   }
  
});

onUnmounted(() => {
  destroyFlvPlayer();
  if (timeInterval) clearInterval(timeInterval);
  if (speedInterval) clearInterval(speedInterval);
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

/* Operation Bar */
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

/* Status Indicator */
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

/* 相机预览 */
.camera-view-area {
  /* width: auto; */
  /* height: 88%; */
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
  width: 90%;
  height: auto;
  max-height: 100%;
  object-fit: cover;  /* 等比例覆盖，填满区域 */
}

/* Detection Overlay */
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

/* Video Placeholder */
.video-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #8b949e;
  gap: 12px;
  text-align: center;
  padding: 20px;
}

.video-placeholder p {
  margin: 0;
  font-size: 0.9rem;
}

.video-placeholder .hint {
  font-size: 0.8rem;
  color: #6e7681;
}

/* Video Info Bar */
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

/* Responsive */
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