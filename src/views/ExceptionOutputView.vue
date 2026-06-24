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
        <div class="form-main">
          <div class="diagram-row">
            <div class="diagram-box">
              <div class="diagram-title">40-Pin 排针图（参考）</div>
              <div class="pinout-wrapper">
                <img class="pinout-image" :src="pinoutImage" alt="40-Pin Expansion Header" />
                <div
                  v-for="m in markerStyles"
                  :key="m.key"
                  class="pinout-marker"
                  :style="m.style"
                  :title="m.title"
                ></div>
              </div>
            </div>

            <div class="pin-summary-sidebar">
              <div class="pin-summary-title">已选</div>
              <div v-if="selectedPins.length === 0" class="pin-summary-empty">暂无</div>
              <div v-else class="pin-summary-tags">
                <div v-for="pin in selectedPins" :key="pin" class="pin-summary-tag" :title="getPinLabel(pin)">
                  <span class="pin-summary-text">{{ getPinShort(pin) }}</span>
                  <button class="pin-summary-remove" type="button" @click="removePin(pin)" :disabled="isLoading">×</button>
                </div>
              </div>
            </div>
          </div>

          <div class="form-item">
            <label class="form-label">GPIO 口：</label>
            <div class="form-control-wrapper">
              <select v-model.number="draftPin" class="form-select" :disabled="isLoading">
                <option :value="0">选择新的端口</option>
                <option
                  v-for="opt in pinOptionsForSelect"
                  :key="opt.pin"
                  :value="opt.pin"
                  :disabled="opt.disabled"
                >
                  {{ opt.label }}
                </option>
              </select>

              <button class="mini-btn" type="button" @click="applyDraftPin" :disabled="isLoading || !draftPin">
                添加
              </button>
              <button class="mini-btn danger" type="button" @click="clearAllPins" :disabled="isLoading || selectedPins.length === 0">
                清空
              </button>
            </div>
          </div>

          <div class="form-item">
            <label class="form-label">输出电平：</label>
            <div class="form-control-wrapper">
              <select v-model.number="form.outputLevel" class="form-select compact" :disabled="isLoading">
                <option :value="1">高电平</option>
                <option :value="0">低电平</option>
              </select>
            </div>
          </div>

          <div class="form-item">
            <label class="form-label">持续时间：</label>
            <div class="form-control-wrapper">
              <input
                v-model.number="form.duration"
                type="number"
                class="form-input number-input compact"
                min="0"
                step="1"
                :disabled="isLoading"
              />
              <span class="unit">秒（0 表示一直保持）</span>
            </div>
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
import { computed, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { useExceptionOutputStore } from "@/stores/settingsStore";
import pinoutImage from "@/assets/jetson-40pin-pinout.svg";

const router = useRouter();
const exceptionOutputStore = useExceptionOutputStore();
const isLoading = ref(false);

const gpioOptions = [
  { pin: 7, label: "Pin 7 / GPIO (Audio MCLK) / 引脚 7 (GPIO09)" },
  { pin: 8, label: "Pin 8 / GPIO (UART1 TXD) / 引脚 8 (UART1_TXD)" },
  { pin: 10, label: "Pin 10 / GPIO (UART1 RXD) / 引脚 10 (UART1_RXD)" },
  { pin: 11, label: "Pin 11 / GPIO (UART2 RTS) / 引脚 11 (UART1_RTS*)" },
  { pin: 12, label: "Pin 12 / GPIO (Audio Clock) / 引脚 12 (I2S0_SCLK)" },
  { pin: 13, label: "Pin 13 / GPIO (SPI1 Clock) / 引脚 13 (SPI1_SCK)" },
  { pin: 15, label: "Pin 15 / GPIO (PWM1) / 引脚 15 (GPIO12)" },
  { pin: 16, label: "Pin 16 / GPIO (SPI1 CS1) / 引脚 16 (SPI1_CS1*)" },
  { pin: 18, label: "Pin 18 / GPIO (SPI0 CS0) / 引脚 18 (SPI1_CSI0)" },
  { pin: 27, label: "Pin 27 / GPIO (I2C0 SDA) / 引脚 27 (I2C0_SDA)" },
  { pin: 28, label: "Pin 28 / GPIO (I2C0 SCL) / 引脚 28 (I2C0_SCL)" },
  { pin: 29, label: "Pin 29 / GPIO (Clock #0) / 引脚 29 (GPIO01)" },
  { pin: 31, label: "Pin 31 / GPIO (Clock #1) / 引脚 31 (GPIO11)" },
  { pin: 32, label: "Pin 32 / GPIO (PWM7) / 引脚 32 (GPIO07)" },
  { pin: 33, label: "Pin 33 / GPIO / 引脚 33 (GPIO13)" },
  { pin: 35, label: "Pin 35 / GPIO (Audio I2S) / 引脚 35 (I2S0_FS)" },
  { pin: 38, label: "Pin 38 / GPIO (Audio I2S) / 引脚 38 (I2S0_DIN)" },
  { pin: 40, label: "Pin 40 / GPIO (Audio I2S) / 引脚 40 (I2S0_DOUT)" },
];

const form = reactive(exceptionOutputStore.getSettings());
const selectedPins = ref(Array.isArray(form.gpioPins) ? [...form.gpioPins] : []);
const draftPin = ref(0);

const pinOptionsForSelect = computed(() => {
  const selectedSet = new Set(selectedPins.value.map((p) => Number(p)));
  return gpioOptions.map((opt) => {
    const disabled = selectedSet.has(opt.pin);
    return {
      ...opt,
      disabled,
      label: disabled ? `${opt.label}（已选）` : opt.label,
    };
  });
});

const getPinLabel = (pin) => {
  const found = gpioOptions.find((opt) => opt.pin === Number(pin));
  return found ? found.label : `Pin ${pin}`;
};

const applyDraftPin = () => {
  if (!draftPin.value) return;
  const pin = Number(draftPin.value);
  if (!selectedPins.value.includes(pin)) {
    selectedPins.value.push(pin);
    selectedPins.value.sort((a, b) => a - b);
  }
  form.gpioPins = [...selectedPins.value];
  draftPin.value = 0;
};

const removePin = (pin) => {
  const p = Number(pin);
  selectedPins.value = selectedPins.value.filter((x) => Number(x) !== p);
  form.gpioPins = [...selectedPins.value];
  if (draftPin.value === p) draftPin.value = 0;
};

const clearAllPins = () => {
  selectedPins.value = [];
  form.gpioPins = [];
  draftPin.value = 0;
};

const markerStyles = computed(() => {
  const pins = selectedPins.value.map((p) => Number(p)).filter((p) => Number.isInteger(p) && p > 0);
  if (pins.length === 0) return [];

  const leftXPct = 350 / 900;
  const rightXPct = 570 / 900;
  const y0Pct = 140 / 760;
  const stepPct = 28 / 760;

  return pins.map((pin, idx) => {
    const isOdd = pin % 2 === 1;
    const rowIndex = Math.floor((pin - 1) / 2);
    const xPct = isOdd ? leftXPct : rightXPct;
    const yPct = y0Pct + rowIndex * stepPct;
    return {
      key: `pin-${pin}`,
      title: `Pin ${pin}`,
      style: {
        left: `${xPct * 100}%`,
        top: `${yPct * 100}%`,
        borderColor: `#1677ff`,
        boxShadow: `0 0 0 4px rgba(22, 119, 255, 0.18)`,
        background: `rgba(22, 119, 255, 0.18)`,
      },
    };
  });
});

const getPinShort = (pin) => `pin${Number(pin)}`;

const goBack = () => {
  if (isLoading.value) return;
  router.push("/");
};

const confirmSettings = async () => {
  const gpioPins = selectedPins.value.map((p) => Number(p)).filter((p) => Number.isInteger(p) && p > 0);
  const outputLevel = Number(form.outputLevel);
  const duration = Number(form.duration);

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
      gpioPins,
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
  display: flex;
  gap: 16px;
}

.settings-form.form-loading {
  opacity: 0.75;
  pointer-events: none;
}

.form-main {
  flex: 1;
  min-width: 0;
}

.diagram-row {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 20px;
}

.diagram-box {
  flex: 1;
  margin-bottom: 0;
}

.pin-summary-sidebar {
  width: 180px;
  flex-shrink: 0;
  padding-top: 14px;
}

.pin-summary-empty {
  color: #9ca3af;
  font-size: 0.9rem;
  margin-top: 8px;
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

.form-select.compact,
.form-input.compact {
  flex: 0 0 auto;
  width: 180px;
}

.form-input:focus,
.form-select:focus {
  border-color: #1677ff;
}

.number-input {
  max-width: none;
}

.unit {
  color: #999;
  font-size: 0.85rem;
  white-space: nowrap;
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
}

.diagram-title {
  font-size: 0.95rem;
  font-weight: 600;
  color: #333;
  margin-bottom: 10px;
}

.pinout-wrapper {
  position: relative;
}

.pinout-image {
  width: 100%;
  height: auto;
  border-radius: 8px;
  border: 1px solid #f3f4f6;
  background: #ffffff;
}

.pinout-marker {
  position: absolute;
  width: 18px;
  height: 18px;
  border-radius: 999px;
  border: 3px solid #1677ff;
  background: rgba(22, 119, 255, 0.15);
  transform: translate(-50%, -50%);
  pointer-events: none;
}

.pin-summary-title {
  font-size: 0.9rem;
  font-weight: 600;
  color: #333;
  margin-bottom: 8px;
}

.pin-summary-tags {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.pin-summary-tag {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid rgba(22, 119, 255, 0.28);
  background: rgba(22, 119, 255, 0.07);
}

.pin-summary-text {
  font-size: 0.92rem;
  font-weight: 700;
  color: #111827;
  text-transform: lowercase;
}

.pin-summary-remove {
  width: 20px;
  height: 20px;
  border-radius: 999px;
  border: none;
  background: rgba(239, 68, 68, 0.12);
  color: #ef4444;
  cursor: pointer;
  font-size: 14px;
  line-height: 20px;
  padding: 0;
}

.pin-summary-remove:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.mini-btn {
  padding: 10px 14px;
  border: 1px solid #d9d9d9;
  background: #ffffff;
  border-radius: 6px;
  font-size: 0.9rem;
  cursor: pointer;
  transition: all 0.2s;
}

.mini-btn:hover:not(:disabled) {
  border-color: #1677ff;
  color: #1677ff;
}

.mini-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.mini-btn.danger:hover:not(:disabled) {
  border-color: #ef4444;
  color: #ef4444;
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

  .settings-form {
    flex-direction: column;
  }

  .diagram-row {
    flex-direction: column;
  }

  .pin-summary-sidebar {
    width: 100%;
  }

  .pin-summary-tags {
    flex-direction: row;
    flex-wrap: wrap;
  }
}
</style>

<style scoped>
.settings-page {
  min-height: calc(100vh - var(--topbar-height));
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 28px 18px;
  background: transparent;
}

.settings-container {
  width: min(980px, 100%);
  overflow: hidden;
  background: var(--industrial-surface);
  border: 1px solid var(--industrial-border);
  border-radius: var(--industrial-radius);
  box-shadow: var(--industrial-shadow);
}

.settings-header {
  position: relative;
  min-height: 62px;
  display: flex;
  align-items: center;
  justify-content: space-between;
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

.settings-form {
  padding: 24px;
  gap: 20px;
}

.settings-form.form-loading {
  opacity: 0.72;
  pointer-events: none;
}

.form-main,
.diagram-box,
.tips-box,
.pin-summary-sidebar {
  background: var(--industrial-surface);
  border: 1px solid var(--industrial-border);
  border-radius: var(--industrial-radius);
  box-shadow: var(--industrial-shadow);
}

.form-main {
  padding: 18px;
}

.diagram-row {
  gap: 16px;
}

.diagram-box {
  padding: 16px;
}

.diagram-title,
.pin-summary-title {
  color: var(--industrial-text);
  font-size: 14px;
  font-weight: 800;
}

.pinout-image {
  border-color: var(--industrial-border);
  border-radius: var(--industrial-radius-sm);
}

.pinout-marker {
  border-color: var(--industrial-red);
  background: rgba(185, 28, 28, 0.12);
  box-shadow: 0 0 0 4px rgba(185, 28, 28, 0.12);
}

.pin-summary-sidebar {
  padding: 16px;
}

.pin-summary-empty {
  color: var(--industrial-faint);
}

.pin-summary-tag {
  border-color: rgba(185, 28, 28, 0.2);
  background: var(--industrial-red-soft);
}

.pin-summary-text {
  color: var(--industrial-red-dark);
}

.pin-summary-remove {
  color: var(--industrial-danger);
  background: var(--industrial-danger-soft);
}

.form-item {
  display: grid;
  grid-template-columns: 112px minmax(0, 1fr);
  align-items: center;
  gap: 14px;
  margin-bottom: 18px;
}

.form-label {
  color: var(--industrial-muted);
  font-size: 13px;
  font-weight: 700;
  text-align: right;
}

.form-control-wrapper {
  display: flex;
  align-items: center;
  gap: 10px;
}

.form-input,
.form-select {
  min-height: 36px;
  padding: 0 12px;
  color: var(--industrial-text);
  background: var(--industrial-surface-subtle);
  border: 1px solid var(--industrial-border);
  border-radius: var(--industrial-radius-sm);
}

.form-select.compact,
.form-input.compact {
  width: 180px;
}

.unit,
.tips-box {
  color: var(--industrial-muted);
}

.tips-box {
  margin-top: 12px;
  padding: 14px 16px;
  background: #fbfcfd;
}

.mini-btn {
  min-height: 36px;
  padding: 0 12px;
  color: var(--industrial-muted);
  background: var(--industrial-surface-subtle);
  border: 1px solid var(--industrial-border);
  border-radius: var(--industrial-radius-sm);
}

.mini-btn:hover:not(:disabled) {
  color: var(--industrial-red-dark);
  background: var(--industrial-red-soft);
  border-color: rgba(185, 28, 28, 0.24);
}

.mini-btn.danger:hover:not(:disabled) {
  color: var(--industrial-danger);
  border-color: rgba(197, 48, 48, 0.28);
  background: var(--industrial-danger-soft);
}

.settings-footer {
  display: flex;
  justify-content: flex-end;
  padding: 16px 24px 22px;
  border-top: 1px solid var(--industrial-border);
  background: #fbfcfd;
}

.confirm-btn {
  min-width: 112px;
  min-height: 36px;
  padding: 0 20px;
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

@media (max-width: 860px) {
  .settings-page {
    padding: 16px 12px;
  }

  .settings-form,
  .diagram-row {
    flex-direction: column;
  }

  .pin-summary-sidebar {
    width: 100%;
  }

  .form-item {
    grid-template-columns: 1fr;
    gap: 8px;
  }

  .form-label {
    text-align: left;
  }
}
</style>
