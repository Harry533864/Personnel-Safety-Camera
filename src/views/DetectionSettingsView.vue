<template>
  <div class="settings-page">
    <div class="settings-container">
      <div class="settings-header">
        <h2 class="settings-title">检测设置</h2>
        <button class="close-btn" @click="goBack" :disabled="isLoading">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      </div>
      
      <div class="settings-form" :class="{ 'form-loading': isLoading }">
        <div class="form-item">
          <label class="form-label">检测启用：</label>
          <div class="form-control-wrapper">
            <label class="toggle-switch">
              <input type="checkbox" v-model="settings.detectionEnabled" :disabled="isLoading" />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>

        <div class="form-item">
          <label class="form-label">检测模型：</label>
          <div class="form-control-wrapper">
            <select
              v-model="settings.detectionModel"
              class="form-select"
              :disabled="isLoading || modelsLoading"
            >
              <option
                v-for="model in modelOptions"
                :key="model"
                :value="model"
              >
                {{ model }}
              </option>
            </select>
            <span class="unit" v-if="modelsLoading">加载中</span>
          </div>
        </div>

        <div class="form-item">
          <label class="form-label">检测阈值：</label>
          <div class="form-control-wrapper">
            <input 
              type="number" 
              v-model.number="settings.detectionThreshold" 
              class="form-input"
              min="0"
              max="1"
              step="0.01"
              :disabled="isLoading"
            />
            <span class="unit">Confidence</span>
          </div>
        </div>

        <div class="form-item">
          <label class="form-label">重叠率：</label>
          <div class="form-control-wrapper">
            <input 
              type="number" 
              v-model.number="settings.overlapRate" 
              class="form-input"
              min="0"
              max="1"
              step="0.01"
              :disabled="isLoading"
            />
            <span class="unit">IoU</span>
          </div>
        </div>

        <!-- <div class="form-item">
          <label class="form-label">匹配启用：</label>
          <div class="form-control-wrapper">
            <label class="toggle-switch">
              <input type="checkbox" v-model="settings.matchEnabled" :disabled="isLoading" />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>

        <div class="form-item">
          <label class="form-label">匹配阈值：</label>
          <div class="form-control-wrapper">
            <input 
              type="number" 
              v-model.number="settings.matchThreshold" 
              class="form-input"
              min="0"
              max="1"
              step="0.01"
              :disabled="isLoading"
            />
          </div>
        </div>

        <div class="form-item">
          <label class="form-label">匹配频率：</label>
          <div class="form-control-wrapper">
            <input 
              type="number" 
              v-model.number="settings.matchFrequency" 
              class="form-input number-input"
              min="1"
              max="30"
              step="1"
              :disabled="isLoading"
            />
            <span class="unit">Hz</span>
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
        </div> -->
      </div>

      <div class="settings-footer">
        <button class="confirm-btn" @click="confirmSettings" :disabled="isLoading">
          <span v-if="isLoading" class="spinner"></span>
          <span>{{ isLoading ? '保存中...' : '确认' }}</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, reactive, onMounted } from "vue";
import { useRouter } from "vue-router";
import { useDetectionSettingStore, useModelManagementStore } from '@/stores/settingsStore'

const router = useRouter();
const detectionSettingStore = useDetectionSettingStore()
const modelManagementStore = useModelManagementStore()
const settings = reactive(detectionSettingStore.getSettings());
const isLoading = ref(false);
const modelsLoading = ref(false);
const modelOptions = computed(() => {
  const models = modelManagementStore.getModels();
  if (models.length) {
    return models;
  }
  return settings.detectionModel ? [settings.detectionModel] : [];
});

const goBack = () => {
  if (isLoading.value) return;
  router.push("/");
};

const confirmSettings = async () => {
  isLoading.value = true;
  try {
    const success = await detectionSettingStore.saveSettings(settings);
    if (success) {
      router.push("/");
    } else {
      alert('设置失败，请重试');
    }
  } catch (e) {
    alert('设置参数时发生异常：' + e.message);
  } finally {
    isLoading.value = false;
  }

  // 返回首页
  router.push("/");
};

onMounted(async () => {
  if (modelManagementStore.getModels().length) {
    return;
  }

  modelsLoading.value = true;
  await modelManagementStore.fetchModels();
  modelsLoading.value = false;
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

.form-input:focus {
  border-color: #1677ff;
}

.form-input:disabled {
  background: #f5f5f5;
  cursor: not-allowed;
}

.number-input {
  max-width: 120px;
}

.unit {
  color: #999;
  font-size: 0.85rem;
  min-width: 30px;
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

.toggle-switch input:disabled + .toggle-slider {
  opacity: 0.6;
  cursor: not-allowed;
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
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-width: 100px;
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
