<template>
  <div class="settings-page">
    <div class="settings-container">
      <div class="settings-header">
        <h2 class="settings-title">上传模型</h2>
        <button class="close-btn" @click="goBack" :disabled="isUploading">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      </div>

      <div class="settings-form" :class="{ 'form-loading': isUploading }">
        <div class="form-item">
          <label class="form-label">模型名称：</label>
          <div class="form-control-wrapper">
            <input
              v-model.trim="form.modelName"
              type="text"
              class="form-input"
              placeholder="请输入模型名称"
              :disabled="isUploading"
            />
          </div>
        </div>

        <div class="form-item">
          <label class="form-label">权重文件：</label>
          <div class="form-control-wrapper file-control">
            <input
              ref="engineInputRef"
              type="file"
              class="file-input"
              accept=".engine"
              :disabled="isUploading"
              @change="handleEngineFileChange"
            />
            <span class="file-name">{{ form.engineFile?.name || '请选择 .engine 文件' }}</span>
          </div>
        </div>

        <div class="form-item">
          <label class="form-label">类别文件：</label>
          <div class="form-control-wrapper file-control">
            <input
              ref="txtInputRef"
              type="file"
              class="file-input"
              accept=".txt"
              :disabled="isUploading"
              @change="handleTxtFileChange"
            />
            <span class="file-name">{{ form.txtFile?.name || '请选择 .txt 文件' }}</span>
          </div>
        </div>

        <div class="progress-panel" v-if="isUploading || uploadProgress > 0">
          <div class="progress-header">
            <span>{{ isUploading ? '上传中...' : '上传完成' }}</span>
            <span>{{ uploadProgress }}%</span>
          </div>
          <div class="progress-track">
            <div class="progress-fill" :style="{ width: `${uploadProgress}%` }"></div>
          </div>
        </div>

        <div class="tips-box">
          <p>注意：模型名称不能重复。</p>
        </div>

        <div class="list-panel">
          <div class="list-header">
            <h3 class="list-title">已上传模型</h3>
            <button class="refresh-btn" @click="refreshModels" :disabled="isUploading || isRefreshing">
              {{ isRefreshing ? '刷新中...' : '刷新列表' }}
            </button>
          </div>

          <div v-if="modelRows.length" class="table-wrapper">
            <table class="model-table">
              <thead>
                <tr>
                  <th>模型名称</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="model in modelRows" :key="model">
                  <td>{{ model }}</td>
                  <td>已上传</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="empty-text">
            暂无已上传模型
          </div>
        </div>
      </div>

      <div class="settings-footer">
        <button class="confirm-btn" @click="submitUpload" :disabled="isUploading">
          <span>{{ isUploading ? '上传中...' : '开始上传' }}</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { useDetectionSettingStore, useModelManagementStore } from "@/stores/settingsStore";

const router = useRouter();
const modelManagementStore = useModelManagementStore();
const detectionSettingStore = useDetectionSettingStore();

const form = reactive({
  modelName: "",
  engineFile: null,
  txtFile: null,
});

const engineInputRef = ref(null);
const txtInputRef = ref(null);
const isRefreshing = ref(false);

const modelRows = computed(() => modelManagementStore.getModels());
const uploadProgress = computed(() => modelManagementStore.uploadProgress);
const isUploading = computed(() => modelManagementStore.isUploading);

const goBack = () => {
  if (isUploading.value) return;
  router.push("/");
};

const resetFileInput = (inputRef) => {
  if (inputRef.value) {
    inputRef.value.value = "";
  }
};

const handleEngineFileChange = (event) => {
  const file = event.target.files?.[0] || null;

  if (file && !file.name.toLowerCase().endsWith(".engine")) {
    alert("权重文件必须是 .engine 后缀");
    form.engineFile = null;
    resetFileInput(engineInputRef);
    return;
  }

  form.engineFile = file;
};

const handleTxtFileChange = (event) => {
  const file = event.target.files?.[0] || null;

  if (file && !file.name.toLowerCase().endsWith(".txt")) {
    alert("类别名称文件必须是 .txt 后缀");
    form.txtFile = null;
    resetFileInput(txtInputRef);
    return;
  }

  form.txtFile = file;
};

const refreshModels = async () => {
  isRefreshing.value = true;
  const models = await modelManagementStore.fetchModels();
  isRefreshing.value = false;

  if (models === null) {
    alert(modelManagementStore.getState().message || "获取模型列表失败");
  }
};

const submitUpload = async () => {
  if (!form.modelName) {
    alert("请输入模型名称");
    return;
  }

  if (!form.engineFile) {
    alert("请选择 .engine 权重文件");
    return;
  }

  if (!form.txtFile) {
    alert("请选择 .txt 类别名称文件");
    return;
  }

  const result = await modelManagementStore.uploadModel({
    modelName: form.modelName,
    engineFile: form.engineFile,
    txtFile: form.txtFile,
  });

  alert(result.message);

  if (!result.success) {
    return;
  }

  const currentDetectionSettings = detectionSettingStore.getSettings();
  if (!currentDetectionSettings.detectionModel) {
    currentDetectionSettings.detectionModel = form.modelName;
    detectionSettingStore.settings = { ...currentDetectionSettings };
  }

  form.modelName = "";
  form.engineFile = null;
  form.txtFile = null;
  resetFileInput(engineInputRef);
  resetFileInput(txtInputRef);
};

onMounted(async () => {
  modelManagementStore.resetProgress();
  await modelManagementStore.fetchModels();
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
  max-width: 720px;
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
  opacity: 0.75;
  pointer-events: none;
}

.form-item {
  display: flex;
  align-items: center;
  margin-bottom: 20px;
  gap: 16px;
}

.form-label {
  min-width: 88px;
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

.form-input,
.file-input {
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

.form-input:focus,
.file-input:focus {
  border-color: #1677ff;
}

.file-control {
  flex-direction: column;
  align-items: stretch;
}

.file-name {
  color: #666;
  font-size: 0.88rem;
  word-break: break-all;
}

.progress-panel {
  margin-bottom: 20px;
  padding: 14px 16px;
  border-radius: 8px;
  background: #f7faff;
  border: 1px solid #d9e9ff;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  color: #333;
  font-size: 0.92rem;
}

.progress-track {
  width: 100%;
  height: 10px;
  background: #e5e7eb;
  border-radius: 999px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #1677ff, #52a2ff);
  transition: width 0.2s ease;
}

.tips-box {
  margin-bottom: 20px;
  padding: 14px 16px;
  border-radius: 8px;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  color: #666;
  font-size: 0.9rem;
  line-height: 1.8;
}

.tips-box p {
  margin: 0;
}

.list-panel {
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  overflow: hidden;
}

.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px;
  border-bottom: 1px solid #f0f0f0;
  background: #fafafa;
}

.list-title {
  margin: 0;
  font-size: 1rem;
  color: #333;
}

.refresh-btn {
  padding: 6px 12px;
  background: #ffffff;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  color: #333;
  cursor: pointer;
}

.refresh-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.table-wrapper {
  overflow-x: auto;
}

.model-table {
  width: 100%;
  border-collapse: collapse;
}

.model-table th,
.model-table td {
  padding: 12px 16px;
  border-bottom: 1px solid #f0f0f0;
  text-align: left;
  font-size: 0.92rem;
  color: #333;
}

.model-table th {
  background: #fff;
  color: #666;
  font-weight: 600;
}

.empty-text {
  padding: 24px 16px;
  text-align: center;
  color: #999;
  font-size: 0.92rem;
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
  min-width: 112px;
}

.confirm-btn:hover:not(:disabled) {
  background: #4096ff;
}

.confirm-btn:disabled {
  opacity: 0.75;
  cursor: not-allowed;
}

@media (max-width: 768px) {
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

  .list-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }
}
</style>
