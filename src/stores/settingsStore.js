import { defineStore } from 'pinia'

// 从环境变量中获取后端路由ip
const API_URL = import.meta.env.VITE_FLASK_BACKEND_URL;

export function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ========== 持久化工具函数 ==========
const STORAGE_KEY_CAMERA = 'camera_settings'
const STORAGE_KEY_CAMERA_STATE = 'camera_save_result'
const STORAGE_KEY_DETECTION = 'detection_settings'
const STORAGE_KEY_DETECTION_STATE = 'detection_save_result'
const STORAGE_KEY_DETECTION_REGION = 'detection_region_settings'
const STORAGE_KEY_DETECTION_REGION_STATE = 'detection_region_save_result'

const cloneValue = (value) => JSON.parse(JSON.stringify(value))

const normalizeDetectionRegionData = (raw) => {
  const defaults = {
    currentTarget: 'all',
    byTarget: {
      all: [],
      high: [],
      low: [],
    },
  }

  if (!raw) {
    return cloneValue(defaults)
  }

  if (Array.isArray(raw)) {
    return {
      currentTarget: 'all',
      byTarget: {
        all: cloneValue(raw),
        high: [],
        low: [],
      },
    }
  }

  return {
    currentTarget: raw.currentTarget || 'all',
    byTarget: {
      all: Array.isArray(raw.byTarget?.all) ? cloneValue(raw.byTarget.all) : [],
      high: Array.isArray(raw.byTarget?.high) ? cloneValue(raw.byTarget.high) : [],
      low: Array.isArray(raw.byTarget?.low) ? cloneValue(raw.byTarget.low) : [],
    },
  }
}

const loadFromStorage = (key, defaults) => {
  try {
    const raw = localStorage.getItem(key)
    return raw ? JSON.parse(raw) : cloneValue(defaults)
  } catch {
    return cloneValue(defaults)
  }
}

const saveToStorage = (key, data) => {
  localStorage.setItem(key, JSON.stringify(data))
}

// ========== 相机设置 ==========
const CAMERA_DEFAULTS = {
  resolution: '1920x1080',
  exposure: '0',
  fps: '15',
  target: 'high',
}

export const useCameraSettingStore = defineStore('cameraSetting', {
  state: () => ({
    settings: loadFromStorage(STORAGE_KEY_CAMERA, CAMERA_DEFAULTS),
    lastSaveResult: loadFromStorage(STORAGE_KEY_CAMERA_STATE, { unset: true }),
  }),
  actions: {
    async saveSettings(settings) {
      // 用临时对象记录本次实际要保存的值，失败回滚为旧值
      const finalSettings = { ...settings }
      const messages = []
      let exposureSuccess = true
      let resolutionSuccess = true

      try {
        if (settings.exposure !== this.settings.exposure) {
          console.log("设置曝光...")
          try {
            const response = await fetch(`${API_URL}/api/stream/exposure`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                value: parseInt(settings.exposure),
                target: settings.target || CAMERA_DEFAULTS.target
              }),
            })
            const data = await response.json()
            if (data.status === 'success') {
              // 成功，保留新值
            } else {
              throw new Error(data.message || '曝光设置失败')
            }
          } catch (err) {
            // 接口异常或业务失败，回滚曝光值
            finalSettings.exposure = this.settings.exposure
            exposureSuccess = false
            messages.push(`曝光设置失败: ${err.message}`)
          }
        }

        // ---- 处理分辨率 ----
        if (settings.resolution !== this.settings.resolution) {
          console.log("设置分辨率...")
          try {
            const [width, height] = settings.resolution.split('x').map(Number)
            const response = await fetch(`${API_URL}/api/stream/resolution`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                width,
                height,
                target: settings.target
              }),
            })
            const data = await response.json()
            if (data.status === 'success') {
              // 成功，保留新值
            } else {
              throw new Error(data.message || '分辨率设置失败')
            }
          } catch (err) {
            // 回滚分辨率
            finalSettings.resolution = this.settings.resolution
            resolutionSuccess = false
            messages.push(`分辨率设置失败: ${err.message}`)
          }
        }

        // ---- 更新 store 和持久化 ----
        const allSuccess = exposureSuccess && resolutionSuccess
        if (allSuccess) {
          // 全部成功：完全替换 settings
          this.settings = { ...finalSettings }
        } else {
          // 部分成功：只写入成功的字段（失败的已回滚为旧值）
          this.settings = { ...finalSettings }
        }

        saveToStorage(STORAGE_KEY_CAMERA, this.settings)
        this.lastSaveResult = {
          success: allSuccess,
          message: messages.length ? messages.join('；') : (allSuccess ? '保存成功' : '')
        }
        saveToStorage(STORAGE_KEY_CAMERA_STATE, this.lastSaveResult)

        return allSuccess
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
  target: 'all',
}

// TODO 调试检测接口
export const useDetectionSettingStore = defineStore('detectionSetting', {
  state: () => ({
    settings: loadFromStorage(STORAGE_KEY_DETECTION, DETECTION_DEFAULTS),
    lastSaveResult: loadFromStorage(STORAGE_KEY_DETECTION_STATE, { unset: true }),
  }),
  actions: {
    async saveSettings(settings) {
      try {
        const response = await fetch(`${API_URL}/api/detection/region`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ...settings,
            target: settings.target || DETECTION_DEFAULTS.target
          }),
        })

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }

        const data = await response.json()
        if (data.status === 'success') {
          this.settings = { ...settings }
          saveToStorage(STORAGE_KEY_DETECTION, this.settings)
          this.lastSaveResult = { success: true }
          saveToStorage(STORAGE_KEY_DETECTION_STATE, this.lastSaveResult)
          return true
        } else {
          throw new Error(data.message || '保存失败')
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
      return { ...this.lastSaveResult }
    },
    clearResult() {
      this.lastSaveResult = { unset: true }
    },
  },
})

// ========== 检测区域 ==========
const DETECTION_REGION_DEFAULTS = {
  currentTarget: 'all',
  byTarget: {
    all: [],
    high: [],
    low: [],
  },
}

export const useDetectionRegionStore = defineStore('detectionRegion', {
  state: () => ({
    data: normalizeDetectionRegionData(
      loadFromStorage(STORAGE_KEY_DETECTION_REGION, DETECTION_REGION_DEFAULTS)
    ),
    lastSaveResult: loadFromStorage(STORAGE_KEY_DETECTION_REGION_STATE, { unset: true }),
  }),
  actions: {
    async fetchRegions() {
      try {
        const response = await fetch(`${API_URL}/api/detection/regions`, {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
        })

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }

        const data = await response.json()
        const rois = Array.isArray(data?.rois)
          ? data.rois
          : (Array.isArray(data?.config?.rois) ? data.config.rois : [])

        const nextData = {
          currentTarget: this.data.currentTarget || 'all',
          byTarget: {
            all: [],
            high: [],
            low: [],
          },
        }

        rois.forEach((roi) => {
          const target = ['all', 'high', 'low'].includes(roi?.target) ? roi.target : 'all'
          nextData.byTarget[target].push(cloneValue(roi))
        })

        this.data = nextData
        saveToStorage(STORAGE_KEY_DETECTION_REGION, this.data)
        return cloneValue(rois)
      } catch (error) {
        this.lastSaveResult = { success: false, message: error.message }
        saveToStorage(STORAGE_KEY_DETECTION_REGION_STATE, this.lastSaveResult)
        return null
      }
    },
    async saveRegions(rois, options = {}) {
      const target = options.target || this.data.currentTarget || 'all'
      const clear = Boolean(options.clear)

      try {
        const response = await fetch(`${API_URL}/api/detection/regions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            target,
            clear,
            rois: clear ? [] : cloneValue(rois),
          }),
        })

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }

        const data = await response.json()
        if (data.status === 'success') {
          this.data.currentTarget = target
          this.data.byTarget[target] = clear ? [] : cloneValue(rois)
          saveToStorage(STORAGE_KEY_DETECTION_REGION, this.data)
          this.lastSaveResult = { success: true, message: data.message || '保存成功' }
          saveToStorage(STORAGE_KEY_DETECTION_REGION_STATE, this.lastSaveResult)
          return true
        }

        throw new Error(data.message || '检测区域保存失败')
      } catch (error) {
        this.lastSaveResult = { success: false, message: error.message }
        saveToStorage(STORAGE_KEY_DETECTION_REGION_STATE, this.lastSaveResult)
        return false
      }
    },
    async clearRegions(options = {}) {
      return this.saveRegions([], { ...options, clear: true })
    },
    getRegions(target = this.data.currentTarget || 'all') {
      return cloneValue(this.data.byTarget[target] || [])
    },
    getCurrentTarget() {
      return this.data.currentTarget || 'all'
    },
    setCurrentTarget(target) {
      this.data.currentTarget = target || 'all'
      saveToStorage(STORAGE_KEY_DETECTION_REGION, this.data)
    },
    getState() {
      return { ...this.lastSaveResult }
    },
    clearResult() {
      this.lastSaveResult = { unset: true }
    },
  },
})
