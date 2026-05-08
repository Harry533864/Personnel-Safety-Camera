<template>
  <div class="settings-page">
    <div class="settings-container">
      <div class="settings-header">
        <h2 class="settings-title">相机设置</h2>
        <button class="close-btn" @click="goBack">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      </div>
      
      <div class="settings-form" :class="{ 'form-loading': isLoading }">
        <div class="form-item">
          <label class="form-label">分辨率：</label>
          <div class="form-control-wrapper">
            <select v-model="settings.resolution" class="form-select">
              <option value="1920x1080">1920 x 1080</option>
              <option value="1280x720">1280 x 720</option>
              <option value="1024x576">1024 x 576</option>
            </select>
            <span class="unit">Pix</span>
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
            <span class="unit">1 ~ 10000 us；0表示自动。</span>
          </div>
        </div>

        <div class="form-item">
          <label class="form-label">帧率：</label>
          <div class="form-control-wrapper">
            <select v-model="settings.fps" class="form-select">
              <option value="60">60</option>
              <option value="45">45</option>
              <option value="30">30</option>
              <option value="15">15</option>
            </select>
            <span class="unit">fps</span>
          </div>
        </div>

        <div class="form-item">
          <label class="form-label">作用域：</label>
          <div class="form-control-wrapper">
            <select v-model="settings.target" class="form-select">
              <option value="high">高分辨率分支（默认）</option>
              <option value="low">低分辨率分支</option>
              <option value="all">所有分支</option>
            </select>
            <span class="unit"></span>
          </div>
        </div>

      </div>

      <div class="settings-footer">
        <button class="confirm-btn" @click="confirmSettings" :disabled="isLoading">
          <span v-if="isLoading"></span>
          <span>{{ isLoading ? '保存中...' : '确认' }}</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onUnmounted } from "vue";
import { useRouter } from "vue-router";
import { useCameraSettingStore } from '@/stores/settingsStore'

const router = useRouter();
const cameraSettingStore = useCameraSettingStore();
const settings = reactive(cameraSettingStore.getSettings());    // 从 store 加载已保存的设置，无则使用默认值
const isLoading = ref(false);
let pendingTimer = null;

const goBack = () => {
  if (isLoading.value) return;
  router.push("/");
};

const confirmSettings = async () => {
  // 如果已经有定时器在等待，直接返回，防止重复触发
  if (pendingTimer) return;

  isLoading.value = true;
  try {
    const success = await cameraSettingStore.saveSettings(settings);
    if (success) {
      // 保存成功，等待 3 秒再跳转
      pendingTimer = setTimeout(() => {
        router.push("/");
        pendingTimer = null;
      }, 5000);
    } else {
      alert('保存失败，请重试');
      isLoading.value = false;
    }
  } catch (e) {
    alert('保存异常：' + e.message);
    isLoading.value = false;
  }

  // 返回首页
  // router.push("/");
};

// 校验曝光值
const validateExposure = () => {
  let val = settings.exposure
  if (val === null || val === undefined || isNaN(val)) {
    settings.exposure = 1000
  } else if (val < 0) {
    settings.exposure = 0
  } else if (val > 10000) {
    settings.exposure = 10000
  }
};

onUnmounted(() => {
  if (pendingTimer) clearTimeout(pendingTimer);
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
  background: #ffffff;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  width: 100%;
  max-width: 500px;
  padding: 0;
  overflow: hidden;
}

.settings-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid #e8e8e8;
}

.settings-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: #333;
  margin: 0;
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

.close-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.settings-form {
  padding: 24px;
  transition: opacity 0.2s;
}

.settings-form.form-loading {
  opacity: 0.6;
  pointer-events: none;
}

.form-item {
  display: flex;
  align-items: center;
  margin-bottom: 20px;
  gap: 16px;
}

.form-item:last-child {
  margin-bottom: 0;
}

.form-label {
  min-width: 80px;
  font-size: 0.95rem;
  color: #555;
  text-align: right;
  flex-shrink: 0;
}

.form-control-wrapper {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
}

.form-select,
.form-input {
  flex: 1;
  padding: 10px 14px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  font-size: 0.95rem;
  color: #333;
  background: #fff;
  outline: none;
  transition: border-color 0.2s;
}

.form-select:focus,
.form-input:focus {
  border-color: #1677ff;
}

.unit {
  color: #999;
  font-size: 0.85rem;
  min-width: 30px;
}

.rotation-control {
  display: flex;
  align-items: center;
  gap: 8px;
}

.number-input {
  max-width: 120px;
  text-align: center;
}

.rotation-buttons {
  display: flex;
  gap: 4px;
}

.rot-btn {
  width: 32px;
  height: 32px;
  border: 1px solid #d9d9d9;
  background: #fff;
  border-radius: 4px;
  cursor: pointer;
  font-size: 1rem;
  color: #555;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.rot-btn:hover {
  border-color: #1677ff;
  color: #1677ff;
}

/* Toggle Switch */
.toggle-switch {
  position: relative;
  display: inline-block;
  width: 44px;
  height: 24px;
}

.toggle-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #ccc;
  transition: 0.3s;
  border-radius: 24px;
}

.toggle-slider:before {
  position: absolute;
  content: "";
  height: 18px;
  width: 18px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  transition: 0.3s;
  border-radius: 50%;
}

.toggle-switch input:checked + .toggle-slider {
  background-color: #1677ff;
}

.toggle-switch input:checked + .toggle-slider:before {
  transform: translateX(20px);
}

.settings-footer {
  padding: 16px 24px 24px;
  display: flex;
  justify-content: flex-end;
}

.confirm-btn {
  padding: 10px 32px;
  background: #1677ff;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 0.95rem;
  cursor: pointer;
  transition: background 0.2s;
}

.confirm-btn:hover:not(:disabled) {
  background: #4096ff;
}

.confirm-btn:disabled {
  opacity: 0.75;
  cursor: not-allowed;
}

@media (max-width: 576px) {
  .settings-container {
    max-width: 100%;
  }
  
  .form-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }
  
  .form-label {
    text-align: left;
    min-width: auto;
  }
  
  .form-control-wrapper {
    width: 100%;
  }
}
</style>
