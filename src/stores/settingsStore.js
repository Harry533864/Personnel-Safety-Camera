import { defineStore } from 'pinia'

// ========== 持久化工具函数 ==========
const STORAGE_KEY_CAMERA = 'camera_settings'
const STORAGE_KEY_CAMERA_STATE = 'camera_save_result'
const STORAGE_KEY_DETECTION = 'detection_settings'
const STORAGE_KEY_DETECTION_STATE = 'detection_save_result'

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

const loadFromStorage = (key, defaults) => {
  try {
    const raw = localStorage.getItem(key)
    // return raw ? { ...defaults, ...JSON.parse(raw) } : { ...defaults } // 合并保存
    return raw ? JSON.parse(raw) : { ...defaults }  // 有值直接返回，没有返回default
  } catch {
    return { ...defaults }
  }
}

const saveToStorage = (key, data) => {
  localStorage.setItem(key, JSON.stringify(data))
}

// ========== 相机设置 ==========
const CAMERA_DEFAULTS = {
  resolution: '1920x1080',
  exposure: '0',
  fps: 15,
}

export const useCameraSettingStore = defineStore('cameraSetting', {
  state: () => ({
    settings: loadFromStorage(STORAGE_KEY_CAMERA, CAMERA_DEFAULTS),
    lastSaveResult: loadFromStorage(STORAGE_KEY_CAMERA_STATE, { unset: true }),
  }),
  actions: {
    async saveSettings(settings) {
      try {
        // 模拟/实际 API 调用
        // const response = await fetch('/api/camera/settings', {
        //   method: 'POST',
        //   headers: { 'Content-Type': 'application/json' },
        //   body: JSON.stringify(settings),
        // })
        await sleep(5000);
        const response = { ok: true }
        if (response.ok) {
          this.settings = { ...settings }
          saveToStorage(STORAGE_KEY_CAMERA, this.settings)

          this.lastSaveResult = { success: true }
          saveToStorage(STORAGE_KEY_CAMERA_STATE, this.lastSaveResult)
          return true
        } else {
          this.lastSaveResult = { success: false, message: 'HTTP error' }
          saveToStorage(STORAGE_KEY_CAMERA_STATE, this.lastSaveResult)
          return false
        }
      } catch (error) {
        this.lastSaveResult = { success: false, message: error.message }
        saveToStorage(STORAGE_KEY_CAMERA_STATE, this.lastSaveResult)
        return false
      }
    },
    getSettings() {
      return { ...this.settings }
    },
    getState() {
      return { ...this.lastSaveResult }
    },
    clearResult() {
      this.lastSaveResult = { unset: true }
    },
  },
})

// ========== 检测设置 ==========
const DETECTION_DEFAULTS = {
  detectionEnabled: true,
  detectionModel: '240922',
  detectionThreshold: 0.50,
  overlapRate: 0.10,
  matchEnabled: true,
  matchThreshold: 0.50,
  matchFrequency: 5,
}

export const useDetectionSettingStore = defineStore('detectionSetting', {
  state: () => ({
    settings: loadFromStorage(STORAGE_KEY_DETECTION, DETECTION_DEFAULTS),
    lastSaveResult: loadFromStorage(STORAGE_KEY_DETECTION_STATE,  { unset: true }),
  }),
  actions: {
    async saveSettings(settings) {
      try {
        const response = await fetch('/api/camera/settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(settings),
        })
        sleep(3000);
        if (response.ok) {
          this.settings = { ...settings }
          saveToStorage(STORAGE_KEY_DETECTION, this.settings)

          this.lastSaveResult = { success: true }
          saveToStorage(STORAGE_KEY_DETECTION_STATE, this.lastSaveResult)
          return true
        } else {
          this.lastSaveResult = { success: false, message: 'HTTP error' }
          saveToStorage(STORAGE_KEY_DETECTION_STATE, this.lastSaveResult)
          return false
        }
      } catch (error) {
        this.lastSaveResult = { success: false, message: error.message }
        saveToStorage(STORAGE_KEY_DETECTION_STATE, this.lastSaveResult)
        return false
      }
    },
    getSettings() {
      return { ...this.settings }
    },
    getState() {
      return { ...this.lastSaveResult}
    },
    clearResult() {
      this.lastSaveResult = { unset: true }
    },
  },
})