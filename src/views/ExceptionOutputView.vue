<template>
  <div class="settings-page">
    <div class="settings-container">
      <div class="settings-header">
        <h2 class="settings-title">异常检测配置</h2>
        <button class="close-btn" @click="goBack" :disabled="isLoading">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      </div>

      <div class="settings-form" :class="{ 'form-loading': isLoading }">
        <div class="diagram-box">
          <div class="diagram-title">40-Pin 排针图（参考）</div>
          <img class="pinout-image" :src="pinoutImage" alt="40-Pin Expansion Header" />
        </div>

        <div class="form-item">
          <label class="form-label">GPIO 口：</label>
          <div class="form-control-wrapper">
            <select v-model.number="form.gpio" class="form-select" :disabled="isLoading">
              <option v-for="opt in gpioOptions" :key="opt.pin" :value="opt.pin">
                {{ opt.label }}
              </option>
            </select>
          </div>
        </div>

        <div class="form-item">
          <label class="form-label">输出电平：</label>
          <div class="form-control-wrapper">
            <select v-model.number="form.outputLevel" class="form-select" :disabled="isLoading">
              <option :value="1">高电平</option>
              <option :value="0">低电平</option>
            </select>
            <span class="unit">触发报警时输出</span>
          </div>
        </div>

        <div class="form-item">
          <label class="form-label">持续时间：</label>
          <div class="form-control-wrapper">
            <input
              v-model.number="form.duration"
              type="number"
              class="form-input number-input"
              min="0"
              step="1"
              :disabled="isLoading"
            />
            <span class="unit">秒（0 表示一直保持）</span>
          </div>
        </div>

        <div class="tips-box">
          <p>注意：这里的 GPIO 口使用物理引脚编号（Header Pin #）。如果你把某些脚拿去做 GPIO，可能会占用 UART/SPI/I2S 的默认功能。</p>
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
import { reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { useExceptionOutputStore } from "@/stores/settingsStore";
import pinoutImage from "@/assets/jetson-40pin-pinout.svg";

const router = useRouter();
const exceptionOutputStore = useExceptionOutputStore();
const isLoading = ref(false);

const gpioOptions = [
  { pin: 7, label: "Pin 7 / GPIO (Audio MCLK) / 引脚 7 (GPIO09)" },
  { pin: 11, label: "Pin 11 / GPIO (UART2 RTS) / 引脚 11 (UART1_RTS*)" },
  { pin: 12, label: "Pin 12 / GPIO (Audio Clock) / 引脚 12 (I2S0_SCLK)" },
  { pin: 13, label: "Pin 13 / GPIO (SPI1 Clock) / 引脚 13 (SPI1_SCK)" },
  { pin: 15, label: "Pin 15 / GPIO (PWM1) / 引脚 15 (GPIO12)" },
  { pin: 16, label: "Pin 16 / GPIO (SPI1 CS1) / 引脚 16 (SPI1_CS1*)" },
  { pin: 18, label: "Pin 18 / GPIO (SPI0 CS0) / 引脚 18 (SPI1_CSI0)" },
  { pin: 29, label: "Pin 29 / GPIO (Clock #0) / 引脚 29 (GPIO01)" },
  { pin: 31, label: "Pin 31 / GPIO (Clock #1) / 引脚 31 (GPIO11)" },
  { pin: 32, label: "Pin 32 / GPIO (PWM7) / 引脚 32 (GPIO07)" },
  { pin: 33, label: "Pin 33 / GPIO / 引脚 33 (GPIO13)" },
  { pin: 35, label: "Pin 35 / GPIO (Audio I2S) / 引脚 35 (I2S0_FS)" },
  { pin: 38, label: "Pin 38 / GPIO (Audio I2S) / 引脚 38 (I2S0_DIN)" },
  { pin: 40, label: "Pin 40 / GPIO (Audio I2S) / 引脚 40 (I2S0_DOUT)" },
];

const form = reactive(exceptionOutputStore.getSettings());

const goBack = () => {
  if (isLoading.value) return;
  router.push("/");
};

const confirmSettings = async () => {
  const gpio = Number(form.gpio);
  const outputLevel = Number(form.outputLevel);
  const duration = Number(form.duration);

  if (!Number.isInteger(gpio) || gpio <= 0) {
    alert("请选择有效 GPIO 口（Pin 编号）");
    return;
  }

  if (![0, 1].includes(outputLevel)) {
    alert("输出电平只能选高电平或低电平");
    return;
  }

  if (!Number.isFinite(duration) || duration < 0) {
    alert("持续时间必须是大于等于 0 的数字");
    return;
  }

  isLoading.value = true;
  try {
    const success = await exceptionOutputStore.saveSettings({
      gpio,
      outputLevel,
      duration: Math.floor(duration),
    });
    if (success) {
      alert("异常输出配置已更新");
      router.push("/");
    } else {
      alert(exceptionOutputStore.getState().message || "保存失败，请重试");
    }
  } finally {
    isLoading.value = false;
  }
};
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
.form-select {
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
.form-select:focus {
  border-color: #1677ff;
}

.number-input {
  max-width: 160px;
}

.unit {
  color: #999;
  font-size: 0.85rem;
  min-width: 140px;
}

.tips-box {
  margin-top: 8px;
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

.diagram-box {
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  background: #ffffff;
  padding: 14px 16px;
  margin-bottom: 20px;
}

.diagram-title {
  font-size: 0.95rem;
  font-weight: 600;
  color: #333;
  margin-bottom: 10px;
}

.pinout-image {
  width: 100%;
  height: auto;
  border-radius: 8px;
  border: 1px solid #f3f4f6;
  background: #ffffff;
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
}
</style>
