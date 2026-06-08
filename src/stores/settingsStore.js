import { defineStore } from 'pinia'

// 从环境变量中获取后端路由ip
const JETSON_ENDPOINT_STORAGE_KEY = 'jetson_runtime_endpoint'

const normalizeBaseUrl = (url, fallbackPort) => {
  if (!url) return ''
  try {
    const parsed = new URL(url)
    return `${parsed.protocol}//${parsed.hostname}:${parsed.port || fallbackPort}`
  } catch {
    return ''
  }
}

const configuredApiUrl = normalizeBaseUrl(import.meta.env.VITE_FLASK_BACKEND_URL, '5000')
const configuredApiHost = (() => {
  try {
    return new URL(configuredApiUrl).hostname
  } catch {
    return ''
  }
})()
const configuredCameraHosts = new Set(
  [
    configuredApiHost,
    ...(import.meta.env.VITE_CAMERA_CANDIDATE_HOSTS || '')
      .split(',')
      .map((host) => host.trim())
      .filter(Boolean),
  ].filter(Boolean)
)

const isCurrentDeploymentEndpoint = (endpoint) => {
  if (!endpoint?.api) return false

  try {
    const savedHost = new URL(endpoint.api).hostname
    return savedHost === configuredApiHost ||
      endpoint.configuredApi === configuredApiUrl ||
      endpoint.configuredHost === configuredApiHost
  } catch {
    return false
  }
}

const getApiUrl = () => {
  try {
    const saved = JSON.parse(localStorage.getItem(JETSON_ENDPOINT_STORAGE_KEY) || 'null')
    if (
      saved?.api &&
      configuredCameraHosts.has(new URL(saved.api).hostname) &&
      isCurrentDeploymentEndpoint(saved)
    ) {
      return saved.api
    }
  } catch {
    // Ignore malformed localStorage data and use the configured fallback.
  }

  return configuredApiUrl || import.meta.env.VITE_FLASK_BACKEND_URL
}

export function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

const formatApiError = (err) => err?.message || '请求失败'

// ========== 持久化工具函数 ==========
const STORAGE_KEY_CAMERA = 'camera_settings'
const STORAGE_KEY_CAMERA_STATE = 'camera_save_result'
const STORAGE_KEY_DETECTION = 'detection_settings'
const STORAGE_KEY_DETECTION_STATE = 'detection_save_result'
const STORAGE_KEY_DETECTION_REGION = 'detection_region_settings'
const STORAGE_KEY_DETECTION_REGION_STATE = 'detection_region_save_result'
const STORAGE_KEY_MODEL_LIST = 'model_management_list'
const STORAGE_KEY_MODEL_UPLOAD_STATE = 'model_upload_result'
const STORAGE_KEY_EXCEPTION_OUTPUT = 'exception_output_settings'
const STORAGE_KEY_EXCEPTION_OUTPUT_STATE = 'exception_output_save_result'

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

const clearStorage = () => {
  // 清除全部
  // localStorage.clear();

  // 清除指定 key
  localStorage.removeItem(STORAGE_KEY_DETECTION_REGION);
  localStorage.removeItem(STORAGE_KEY_DETECTION_REGION_STATE);
}

// ========== 相机设置 ==========
const CAMERA_DEFAULTS = {
  resolution: '1920x1080',
  exposure: '0',
  gain: '0',
  whiteBalance: 'continuous',
  fps: '60',
  target: 'high',
}

const normalizeCameraSettings = (raw = {}) => {
  const width = Number(raw.width)
  const height = Number(raw.height)
  const resolution = raw.resolution === 'max'
    ? 'max'
    : (raw.resolution || (width > 0 && height > 0 ? `${width}x${height}` : CAMERA_DEFAULTS.resolution))
  const whiteBalance = raw.whiteBalance || raw.white_balance || CAMERA_DEFAULTS.whiteBalance

  return {
    ...CAMERA_DEFAULTS,
    ...raw,
    resolution: String(resolution),
    exposure: String(raw.exposure ?? CAMERA_DEFAULTS.exposure),
    gain: String(raw.gain ?? CAMERA_DEFAULTS.gain),
    whiteBalance: String(whiteBalance),
    fps: String(raw.fps ?? CAMERA_DEFAULTS.fps),
    target: String(raw.target || CAMERA_DEFAULTS.target),
  }
}

export const useCameraSettingStore = defineStore('cameraSetting', {
  state: () => ({
    settings: normalizeCameraSettings(loadFromStorage(STORAGE_KEY_CAMERA, CAMERA_DEFAULTS)),
    lastSaveResult: loadFromStorage(STORAGE_KEY_CAMERA_STATE, { unset: true }),
  }),
  actions: {
    async fetchSettings() {
      try {
        const response = await fetch(`${getApiUrl()}/api/stream/config`, {
          method: 'GET',
          cache: 'no-store',
        })
        const data = await response.json().catch(() => ({}))
        if (!response.ok || data.status !== 'success') {
          throw new Error(data.message || `HTTP ${response.status}`)
        }

        this.settings = normalizeCameraSettings(data.data || {})
        saveToStorage(STORAGE_KEY_CAMERA, this.settings)
        return { ...this.settings }
      } catch (error) {
        this.lastSaveResult = {
          success: false,
          message: formatApiError(error),
        }
        saveToStorage(STORAGE_KEY_CAMERA_STATE, this.lastSaveResult)
        return { ...this.settings }
      }
    },
    async saveSettings(settings) {
      // 用临时对象记录本次实际要保存的值，失败回滚为旧值
      const finalSettings = normalizeCameraSettings(settings)
      const messages = []
      let exposureSuccess = true
      let gainSuccess = true
      let whiteBalanceSuccess = true
      let resolutionSuccess = true
      let fpsSuccess = true

      try {
        if (settings.exposure !== this.settings.exposure) {
          console.log("设置曝光...")
          try {
            const response = await fetch(`${getApiUrl()}/api/stream/exposure`, {
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

        // ---- 处理增益 ----
        if (settings.gain !== this.settings.gain) {
          console.log("Setting gain...")
          try {
            const response = await fetch(`${getApiUrl()}/api/stream/gain`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                value: parseFloat(settings.gain),
                target: settings.target || CAMERA_DEFAULTS.target
              }),
            })
            const data = await response.json()
            if (data.status === 'success') {
              // Success; keep the new value.
            } else {
              throw new Error(data.message || 'Gain setting failed')
            }
          } catch (err) {
            finalSettings.gain = this.settings.gain
            gainSuccess = false
            messages.push(`Gain setting failed: ${err.message}`)
          }
        }

        // ---- 处理分辨率 ----
        if (settings.whiteBalance !== this.settings.whiteBalance) {
          try {
            const response = await fetch(`${getApiUrl()}/api/stream/white_balance`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                mode: settings.whiteBalance || CAMERA_DEFAULTS.whiteBalance,
                target: settings.target || CAMERA_DEFAULTS.target
              }),
            })
            const data = await response.json()
            if (data.status !== 'success') {
              throw new Error(data.message || 'White balance setting failed')
            }
          } catch (err) {
            finalSettings.whiteBalance = this.settings.whiteBalance
            whiteBalanceSuccess = false
            messages.push(`White balance setting failed: ${err.message}`)
          }
        }

        const shouldApplyResolution = settings.resolution === 'max' || settings.resolution !== this.settings.resolution
        if (shouldApplyResolution) {
          console.log("设置分辨率...")
          try {
            const resolutionPayload = settings.resolution === 'max'
              ? { mode: 'max' }
              : (() => {
                  const [width, height] = settings.resolution.split('x').map(Number)
                  return { width, height }
                })()
            const response = await fetch(`${getApiUrl()}/api/stream/resolution`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                ...resolutionPayload,
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

        // ---- 处理帧率 ----
        if (settings.fps !== this.settings.fps) {
          console.log("设置帧率...")
          try {
            const response = await fetch(`${getApiUrl()}/api/stream/fps`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                value: parseInt(settings.fps),
                target: settings.target || CAMERA_DEFAULTS.target
              }),
            })
            const data = await response.json()
            if (data.status === 'success') {
              // 成功，保留新值
            } else {
              throw new Error(data.message || '帧率设置失败')
            }
          } catch (err) {
            // 接口异常或业务失败，回滚曝光值
            finalSettings.fps = this.settings.fps
            fpsSuccess = false
            messages.push(`帧率设置失败: ${err.message}`)
          }
        }

        // ---- 更新 store 和持久化 ----
        const allSuccess = exposureSuccess && gainSuccess && whiteBalanceSuccess && resolutionSuccess && fpsSuccess
        if (allSuccess) {
          // 全部成功：完全替换 settings
          this.settings = normalizeCameraSettings(finalSettings)
        } else {
          // 部分成功：只写入成功的字段（失败的已回滚为旧值）
          this.settings = normalizeCameraSettings(finalSettings)
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
      return normalizeCameraSettings(this.settings)
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
  detectionModel: 'ASV_person_FP16',
  detectionThreshold: 0.50,
  overlapRate: 0.10,
  // matchEnabled: true,
  // matchThreshold: 0.50,
  // matchFrequency: 5,
  target: 'all',
}

const normalizeDetectionModelName = (modelName) => {
  const name = String(modelName || '').trim()
  if (!name || name === 'YOLO11') {
    return DETECTION_DEFAULTS.detectionModel
  }
  return name
}

const normalizeDetectionSettings = (raw = {}) => {
  const detectionThreshold = Number(raw.detectionThreshold)
  const overlapRate = Number(raw.overlapRate)

  return {
    ...DETECTION_DEFAULTS,
    ...raw,
    detectionEnabled: typeof raw.detectionEnabled === 'boolean'
      ? raw.detectionEnabled
      : DETECTION_DEFAULTS.detectionEnabled,
    detectionModel: normalizeDetectionModelName(raw.detectionModel),
    detectionThreshold: Number.isFinite(detectionThreshold)
      ? detectionThreshold
      : DETECTION_DEFAULTS.detectionThreshold,
    overlapRate: Number.isFinite(overlapRate)
      ? overlapRate
      : DETECTION_DEFAULTS.overlapRate,
    target: raw.target || DETECTION_DEFAULTS.target,
  }
}

export const useDetectionSettingStore = defineStore('detectionSetting', {
  state: () => ({
    settings: normalizeDetectionSettings(loadFromStorage(STORAGE_KEY_DETECTION, DETECTION_DEFAULTS)),
    lastSaveResult: loadFromStorage(STORAGE_KEY_DETECTION_STATE, { unset: true }),
  }),
  actions: {
    async fetchSettings() {
      try {
        const response = await fetch(`${getApiUrl()}/api/detection/config`, {
          method: 'GET',
          headers: { Accept: 'application/json' },
        })

        const data = await response.json()
        if (!response.ok || data.status !== 'success') {
          throw new Error(data.message || `HTTP ${response.status}`)
        }

        this.settings = normalizeDetectionSettings(data.data || {})
        saveToStorage(STORAGE_KEY_DETECTION, this.settings)
        return { ...this.settings }
      } catch (error) {
        this.lastSaveResult = { success: false, message: error.message }
        saveToStorage(STORAGE_KEY_DETECTION_STATE, this.lastSaveResult)
        return null
      }
    },
    async saveSettings(settings) {
      try {
        const nextSettings = normalizeDetectionSettings(settings)
        const response = await fetch(`${getApiUrl()}/api/detection/detect`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ...nextSettings,
            target: nextSettings.target || DETECTION_DEFAULTS.target
          }),
        })

        const data = await response.json()
        if (!response.ok) {
          throw new Error(data.message || `HTTP ${response.status}`)
        }

        if (data.status === 'success') {
          this.settings = { ...nextSettings }
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
      return normalizeDetectionSettings(this.settings)
    },
    setSettings(settings) {
      this.settings = normalizeDetectionSettings(settings)
      saveToStorage(STORAGE_KEY_DETECTION, this.settings)
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

// ========== 模型管理 ==========
const MODEL_MANAGEMENT_DEFAULTS = {
  models: [],
}

export const useModelManagementStore = defineStore('modelManagement', {
  state: () => ({
    models: loadFromStorage(STORAGE_KEY_MODEL_LIST, MODEL_MANAGEMENT_DEFAULTS.models),
    uploadProgress: 0,
    isUploading: false,
    lastUploadResult: loadFromStorage(STORAGE_KEY_MODEL_UPLOAD_STATE, { unset: true }),
  }),
  actions: {
    async fetchModels() {
      try {
        const response = await fetch(`${getApiUrl()}/api/models/list`, {
          method: 'GET',
          headers: { Accept: 'application/json' },
        })

        const data = await response.json()

        if (!response.ok || data.status !== 'success') {
          throw new Error(data.message || `HTTP ${response.status}`)
        }

        this.models = Array.isArray(data.models) ? [...data.models] : []
        saveToStorage(STORAGE_KEY_MODEL_LIST, this.models)
        return [...this.models]
      } catch (error) {
        this.lastUploadResult = { success: false, message: error.message }
        saveToStorage(STORAGE_KEY_MODEL_UPLOAD_STATE, this.lastUploadResult)
        return null
      }
    },
    async uploadModel({ modelName, engineFile, txtFile }) {
      this.isUploading = true
      this.uploadProgress = 0

      try {
        const result = await new Promise((resolve, reject) => {
          const xhr = new XMLHttpRequest()
          const formData = new FormData()

          formData.append('model_name', modelName)
          formData.append('engine_file', engineFile)
          formData.append('txt_file', txtFile)

          xhr.upload.addEventListener('progress', (event) => {
            if (event.lengthComputable && event.total > 0) {
              this.uploadProgress = Math.round((event.loaded / event.total) * 100)
            }
          })

          xhr.addEventListener('load', () => {
            let data = {}

            try {
              data = xhr.responseText ? JSON.parse(xhr.responseText) : {}
            } catch {
              data = {}
            }

            if (xhr.status >= 200 && xhr.status < 300 && data.status === 'success') {
              resolve(data)
            } else {
              reject(new Error(data.message || `HTTP ${xhr.status}`))
            }
          })

          xhr.addEventListener('error', () => {
            reject(new Error('上传模型失败: 网络连接异常'))
          })

          xhr.addEventListener('abort', () => {
            reject(new Error('上传已取消'))
          })

          xhr.open('POST', `${getApiUrl()}/api/models/upload`)
          xhr.send(formData)
        })

        this.uploadProgress = 100
        this.lastUploadResult = { success: true, message: result.message || '上传成功' }
        saveToStorage(STORAGE_KEY_MODEL_UPLOAD_STATE, this.lastUploadResult)
        await this.fetchModels()
        return { success: true, message: result.message || '上传成功', data: result.data || null }
      } catch (error) {
        this.lastUploadResult = { success: false, message: error.message }
        saveToStorage(STORAGE_KEY_MODEL_UPLOAD_STATE, this.lastUploadResult)
        return { success: false, message: error.message }
      } finally {
        this.isUploading = false
      }
    },
    async deleteModel(modelName) {
      if (!confirm(`确定要删除模型 ${modelName} 吗？`)) return { success: false, message: '已取消删除' };
      
      try {
        const response = await fetch(`${getApiUrl()}/api/models/delete`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model_name: modelName }),
        })

        const data = await response.json()

        if (!response.ok || data.status !== 'success') {
          throw new Error(data.message || `HTTP ${response.status}`)
        }

        await this.fetchModels()
        return { success: true, message: data.message || '删除成功' }
      } catch (error) {
        return { success: false, message: error.message }
      }
    },
    getModels() {
      return [...this.models]
    },
    getState() {
      return { ...this.lastUploadResult }
    },
    clearResult() {
      this.lastUploadResult = { unset: true }
      saveToStorage(STORAGE_KEY_MODEL_UPLOAD_STATE, this.lastUploadResult)
    },
    resetProgress() {
      this.uploadProgress = 0
      this.isUploading = false
    },
  },
})

// ========== 异常输出配置 ==========
const EXCEPTION_OUTPUT_DEFAULTS = {
  gpioPins: [7],
  outputLevel: 1,
  duration: 0,
}

export const useExceptionOutputStore = defineStore('exceptionOutput', {
  state: () => ({
    settings: loadFromStorage(STORAGE_KEY_EXCEPTION_OUTPUT, EXCEPTION_OUTPUT_DEFAULTS),
    lastSaveResult: loadFromStorage(STORAGE_KEY_EXCEPTION_OUTPUT_STATE, { unset: true }),
  }),
  actions: {
    async saveSettings(settings) {
      const gpioPinsRaw = settings?.gpioPins
      const gpioPins = Array.isArray(gpioPinsRaw)
        ? gpioPinsRaw.map((p) => Number(p)).filter((p) => Number.isInteger(p) && p > 0)
        : [Number(gpioPinsRaw)].filter((p) => Number.isInteger(p) && p > 0)

      const payload = {
        gpio: gpioPins,
        output_level: Number(settings.outputLevel),
        duration: Number(settings.duration),
      }

      try {
        const response = await fetch(`${getApiUrl()}/api/detection/exception_output`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        })

        const data = await response.json()
        if (!response.ok) {
          throw new Error(data.message || `HTTP ${response.status}`)
        }

        if (data.status === 'success') {
          this.settings = { ...settings }
          saveToStorage(STORAGE_KEY_EXCEPTION_OUTPUT, this.settings)
          this.lastSaveResult = { success: true, message: data.message || '保存成功' }
          saveToStorage(STORAGE_KEY_EXCEPTION_OUTPUT_STATE, this.lastSaveResult)
          return true
        }

        throw new Error(data.message || '保存失败')
      } catch (error) {
        this.lastSaveResult = { success: false, message: error.message }
        saveToStorage(STORAGE_KEY_EXCEPTION_OUTPUT_STATE, this.lastSaveResult)
        return false
      }
    },
    getSettings() {
      const s = { ...this.settings }
      if (Array.isArray(s.gpioPins)) return s
      if (Number.isInteger(s.gpio)) {
        return {
          gpioPins: [Number(s.gpio)],
          outputLevel: Number.isFinite(s.outputLevel) ? Number(s.outputLevel) : 1,
          duration: Number.isFinite(s.duration) ? Number(s.duration) : 0,
        }
      }
      return { ...EXCEPTION_OUTPUT_DEFAULTS }
    },
    getState() {
      return { ...this.lastSaveResult }
    },
    clearResult() {
      this.lastSaveResult = { unset: true }
      saveToStorage(STORAGE_KEY_EXCEPTION_OUTPUT_STATE, this.lastSaveResult)
    },
  },
})

// ========== 检测区域 ==========
const DETECTION_REGION_DEFAULTS = {
  currentTarget: 'all',
  byTarget: {
    all: [(0, 0), (1280, 720)],
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
        const response = await fetch(`${getApiUrl()}/api/detection/fetch_regions`, {
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
        const response = await fetch(`${getApiUrl()}/api/detection/save_regions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            target,
            clear,
            rois: clear ? [] : cloneValue(rois),
          }),
        })

        const data = await response.json()
        if (!response.ok) {
          throw new Error(data.message || `HTTP ${response.status}`)
        }

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

export const useRuntimeStatusStore = defineStore('runtimeStatus', {
  state: () => ({
    data: null,
    loading: false,
    error: '',
    lastUpdated: null,
  }),
  getters: {
    backendOnline: (state) => Boolean(state.data && !state.error),
    cameraOnline: (state) => Boolean(state.data?.camera?.camera_opened),
    streamList: (state) => Array.isArray(state.data?.streams) ? state.data.streams : [],
    modelLoaded() {
      return this.streamList.some((stream) => stream.model_loaded)
    },
    writerOnline() {
      return this.streamList.some((stream) => stream.writer_opened)
    },
    statusClass() {
      if (this.error) return 'danger'
      if (!this.data) return 'warning'
      if (!this.cameraOnline) return 'warning'
      return 'success'
    },
    statusText() {
      if (this.error) return '后端离线'
      if (!this.data) return this.loading ? '连接中' : '未连接'
      if (!this.cameraOnline) return '等待相机'
      if (!this.writerOnline) return '推流待恢复'
      return '后端已连接'
    },
    backendHost() {
      try {
        return new URL(getApiUrl()).host
      } catch {
        return getApiUrl() || '未配置'
      }
    },
  },
  actions: {
    async fetchStatus() {
      this.loading = true
      try {
        const response = await fetch(`${getApiUrl()}/api/runtime/status`, {
          method: 'GET',
          cache: 'no-store',
        })

        const payload = await response.json().catch(() => ({}))
        if (!response.ok || payload.status !== 'success') {
          throw new Error(payload.message || `HTTP ${response.status}`)
        }

        this.data = payload.data || null
        this.error = ''
        this.lastUpdated = new Date().toISOString()
        return this.data
      } catch (error) {
        this.error = formatApiError(error)
        return null
      } finally {
        this.loading = false
      }
    },
  },
})
