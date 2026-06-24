<template>
  <div class="settings-page">
    <div class="settings-container">
      <div class="settings-header">
        <div>
          <h2 class="settings-title">相机设置</h2>
          <p class="settings-subtitle">采集规格与画面参数</p>
        </div>
        <button class="close-btn" @click="goBack" :disabled="isLoading" aria-label="关闭">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      </div>

      <div class="settings-form" :class="{ 'form-loading': isLoading }">
        <div class="form-item">
          <label class="form-label">分辨率：</label>
          <div class="form-control-wrapper">
            <select v-model="settings.resolution" class="form-select" @change="handleResolutionChange">
              <option
                v-for="option in resolutionOptions"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
              </option>
            </select>
            <span class="unit">Pix</span>
          </div>
        </div>

        <div class="form-item">
          <label class="form-label">帧率：</label>
          <div class="form-control-wrapper">
            <select v-model="settings.fps" class="form-select">
              <option v-for="option in fpsOptions" :key="option" :value="String(option)">
                {{ option }}
              </option>
            </select>
            <span class="unit">fps</span>
          </div>
        </div>

        <div class="form-item">
          <label class="form-label">曝光时间：</label>
          <div class="form-control-wrapper">
            <input
              type="number"
              v-model.number="settings.exposure"
              class="form-input"
              min="0"
              max="10000"
              step="1"
              @change="validateExposure"
            />
            <span class="unit">0 自动；1-10000 us</span>
          </div>
        </div>

        <div class="form-item">
          <label class="form-label">画面增益：</label>
          <div class="form-control-wrapper">
            <input
              type="number"
              v-model.number="settings.gain"
              class="form-input"
              min="0"
              max="255"
              step="1"
              @change="validateGain"
            />
            <span class="unit">0-255</span>
          </div>
        </div>

        <div class="form-item">
          <label class="form-label">白平衡：</label>
          <div class="form-control-wrapper">
            <select v-model="settings.whiteBalance" class="form-select">
              <option value="continuous">自动连续</option>
              <option value="off">手动锁定</option>
            </select>
            <span class="unit">推荐自动</span>
          </div>
        </div>

        <div class="form-item">
          <label class="form-label">抗频闪：</label>
          <div class="form-control-wrapper">
            <select v-model="settings.powerLineFrequency" class="form-select">
              <option value="1">50 Hz</option>
              <option value="2">60 Hz</option>
              <option value="0">关闭</option>
            </select>
            <span class="unit">工频补偿</span>
          </div>
        </div>
      </div>

      <div class="settings-footer">
        <button class="confirm-btn" @click="confirmSettings" :disabled="isLoading">
          <span>{{ isLoading ? '保存中...' : '确认' }}</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, reactive, onMounted, onUnmounted } from "vue";
import { useRouter } from "vue-router";
import { useCameraSettingStore } from "@/stores/settingsStore";

const router = useRouter();
const cameraSettingStore = useCameraSettingStore();
const settings = reactive(cameraSettingStore.getSettings());
const isLoading = ref(false);
let pendingTimer = null;

const resolutionOptions = [
  { value: "2592x1944", label: "2592 x 1944（500万全视野）", maxFps: 30 },
  { value: "2048x1536", label: "2048 x 1536（300万全视野）", maxFps: 30 },
  { value: "2592x1440", label: "2592 x 1440（宽幅高清）", maxFps: 30 },
  { value: "2304x1296", label: "2304 x 1296（300万宽幅）", maxFps: 30 },
  { value: "1920x1080", label: "1920 x 1080（200万高清）", maxFps: 60 },
  { value: "1600x900", label: "1600 x 900（高清预览）", maxFps: 60 },
  { value: "1280x720", label: "1280 x 720（720P预览）", maxFps: 60 },
  { value: "1024x576", label: "1024 x 576（低延迟预览）", maxFps: 60 },
  { value: "640x360", label: "640 x 360（低带宽预览）", maxFps: 60 },
];

const fpsOptions = computed(() => {
  const option = resolutionOptions.find((item) => item.value === settings.resolution);
  const maxFps = option?.maxFps || 60;
  return [60, 30, 15].filter((fps) => fps <= maxFps);
});

const normalizeFpsForResolution = () => {
  const option = resolutionOptions.find((item) => item.value === settings.resolution);
  if (!option) return;
  const currentFps = Number(settings.fps || 0);
  if (currentFps > option.maxFps) {
    settings.fps = String(option.maxFps);
  }
};

const handleResolutionChange = () => {
  normalizeFpsForResolution();
};

const goBack = () => {
  if (isLoading.value) return;
  router.push("/");
};

onMounted(async () => {
  isLoading.value = true;
  try {
    const remoteSettings = await cameraSettingStore.fetchSettings();
    Object.assign(settings, remoteSettings, { target: "high" });
    normalizeFpsForResolution();
  } finally {
    isLoading.value = false;
  }
});

const confirmSettings = async () => {
  if (pendingTimer) return;

  normalizeFpsForResolution();
  settings.target = "high";
  isLoading.value = true;
  try {
    const success = await cameraSettingStore.saveSettings(settings);
    if (success) {
      pendingTimer = setTimeout(() => {
        router.push("/");
        pendingTimer = null;
      }, 1500);
      return;
    }

    alert(cameraSettingStore.getState().message || "保存失败，请重试");
    isLoading.value = false;
  } catch (e) {
    alert("保存异常：" + e.message);
    isLoading.value = false;
  }
};

const validateExposure = () => {
  const val = Number(settings.exposure);
  if (!Number.isFinite(val)) {
    settings.exposure = 0;
  } else if (val < 0) {
    settings.exposure = 0;
  } else if (val > 10000) {
    settings.exposure = 10000;
  } else {
    settings.exposure = Math.round(val);
  }
};

const validateGain = () => {
  const val = Number(settings.gain);
  if (!Number.isFinite(val)) {
    settings.gain = 0;
  } else if (val < 0) {
    settings.gain = 0;
  } else if (val > 255) {
    settings.gain = 255;
  } else {
    settings.gain = Math.round(val);
  }
};

onUnmounted(() => {
  if (pendingTimer) clearTimeout(pendingTimer);
});
</script>

<style scoped>
.settings-page {
  min-height: calc(100vh - var(--topbar-height));
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 32px 18px;
  background: transparent;
}

.settings-container {
  width: min(720px, 100%);
  overflow: hidden;
  background: var(--industrial-surface);
  border: 1px solid var(--industrial-border);
  border-radius: var(--industrial-radius);
  box-shadow: var(--industrial-shadow);
}

.settings-header {
  position: relative;
  min-height: 68px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px 16px 24px;
  border-bottom: 1px solid var(--industrial-border);
  background: var(--industrial-surface);
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
  margin: 4px 0 0;
  color: var(--industrial-muted);
  font-size: 12px;
  font-weight: 600;
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

.close-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.settings-form {
  display: grid;
  gap: 16px;
  padding: 24px;
  background: var(--industrial-surface);
}

.settings-form.form-loading {
  opacity: 0.68;
  pointer-events: none;
}

.form-item {
  display: grid;
  grid-template-columns: 112px minmax(0, 1fr);
  align-items: center;
  gap: 14px;
}

.form-label {
  color: var(--industrial-muted);
  font-size: 13px;
  font-weight: 800;
  text-align: right;
}

.form-control-wrapper {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 126px;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.form-select,
.form-input {
  min-height: 38px;
  width: 100%;
  padding: 0 12px;
  color: var(--industrial-text);
  background: var(--industrial-surface-subtle);
  border: 1px solid var(--industrial-border);
  border-radius: var(--industrial-radius-sm);
  outline: none;
}

.form-select:focus,
.form-input:focus {
  border-color: var(--industrial-red);
  box-shadow: 0 0 0 3px rgba(220, 38, 38, 0.12);
}

.unit {
  color: var(--industrial-muted);
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

.settings-footer {
  display: flex;
  justify-content: flex-end;
  padding: 16px 24px 22px;
  border-top: 1px solid var(--industrial-border);
  background: #fbfcfd;
}

.confirm-btn {
  min-width: 108px;
  min-height: 38px;
  padding: 0 22px;
  color: #ffffff;
  background: var(--industrial-red);
  border: 1px solid var(--industrial-red);
  border-radius: var(--industrial-radius-sm);
  font-weight: 800;
}

.confirm-btn:hover:not(:disabled) {
  background: var(--industrial-red-dark);
  border-color: var(--industrial-red-dark);
  box-shadow: var(--industrial-shadow-hover);
}

.confirm-btn:disabled {
  opacity: 0.72;
  cursor: not-allowed;
}

@media (max-width: 640px) {
  .settings-page {
    padding: 16px 12px;
  }

  .form-item {
    grid-template-columns: 1fr;
    align-items: stretch;
    gap: 8px;
  }

  .form-label {
    text-align: left;
  }

  .form-control-wrapper {
    grid-template-columns: 1fr;
  }
}
</style>
