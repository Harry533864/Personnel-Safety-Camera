import { defineStore } from 'pinia'

// 从环境变量中获取后端路由ip
const JETSON_ENDPOINT_STORAGE_KEY = 'jetson_runtime_endpoint'
const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '::1'])

const normalizeBaseUrl = (value) => String(value || '').trim().replace(/\/+$/, '')

const getUrlHost = (value) => {
  try {
    return new URL(value).hostname
  } catch {
    return ''
  }
}

const isLocalApiUrl = (value) => LOCAL_HOSTS.has(getUrlHost(value))

const getStoredEndpoint = () => {
  try {
    return JSON.parse(localStorage.getItem(JETSON_ENDPOINT_STORAGE_KEY) || 'null')
  } catch {
    return null
  }
}

const pushUniqueUrl = (items, value) => {
  const normalized = normalizeBaseUrl(value)
  if (normalized && !items.includes(normalized)) {
    items.push(normalized)
  }
}

export const getApiUrl = () => {
  const configured = normalizeBaseUrl(import.meta.env.VITE_FLASK_BACKEND_URL)
  const configuredIsJetson = configured && !isLocalApiUrl(configured)
  if (configuredIsJetson) {
    return configured
  }

  const saved = getStoredEndpoint()
  const savedApi = normalizeBaseUrl(saved?.api)

  if (savedApi) {
    const savedIsLocal = isLocalApiUrl(savedApi)
    if (!savedIsLocal) {
      return savedApi
    }
  }

  return configured
}

export const getApiUrlCandidates = () => {
  const urls = []
  pushUniqueUrl(urls, getApiUrl())

  if (typeof window !== 'undefined' && window.location?.hostname) {
    const { protocol, hostname } = window.location
    if (protocol === 'http:' || protocol === 'https:') {
      pushUniqueUrl(urls, `${protocol}//${hostname}:5000`)
    }

    if (['localhost', '127.0.0.1', '::1'].includes(hostname)) {
      pushUniqueUrl(urls, 'http://127.0.0.1:5000')
      pushUniqueUrl(urls, 'http://localhost:5000')
    }
  }

  return urls
}

export const getHardwareApiUrlCandidates = () => {
  const urls = []
  const saved = getStoredEndpoint()
  const configured = normalizeBaseUrl(import.meta.env.VITE_FLASK_BACKEND_URL)
  const configuredIsJetson = configured && !isLocalApiUrl(configured)

  pushUniqueUrl(urls, configured)

  if (
    !configuredIsJetson
    &&
    saved?.api
    && !isLocalApiUrl(saved.api)
  ) {
    pushUniqueUrl(urls, saved.api)
  }

  if (typeof window !== 'undefined' && window.location?.hostname) {
    const { protocol, hostname } = window.location
    if (!LOCAL_HOSTS.has(hostname) && (protocol === 'http:' || protocol === 'https:')) {
      pushUniqueUrl(urls, `${protocol}//${hostname}:5000`)
    }
  }

  return urls.length ? urls : getApiUrlCandidates()
}

export const rememberApiUrl = (api, options = {}) => {
  if (typeof localStorage === 'undefined') return
  if (options.hardware && isLocalApiUrl(api)) return

  try {
    const saved = getStoredEndpoint() || {}
    localStorage.setItem(
      JETSON_ENDPOINT_STORAGE_KEY,
      JSON.stringify({
        ...saved,
        api: normalizeBaseUrl(api),
      })
    )
  } catch {
    localStorage.setItem(
      JETSON_ENDPOINT_STORAGE_KEY,
      JSON.stringify({ api: normalizeBaseUrl(api) })
    )
  }
}

const fetchJsonFromApiCandidates = async (path, options = {}, candidates = getApiUrlCandidates()) => {
  const failures = []

  for (const baseUrl of candidates) {
    try {
      const response = await fetch(`${baseUrl}${path}`, options)
      const text = await response.text()
      const data = text ? JSON.parse(text) : {}

      if (!response.ok) {
        throw new Error(data.message || `HTTP ${response.status}`)
      }

      rememberApiUrl(baseUrl, { hardware: !isLocalApiUrl(baseUrl) })
      return { response, data, baseUrl }
    } catch (error) {
      failures.push(`${baseUrl}: ${error.message}`)
    }
  }

  throw new Error(failures.join('; ') || 'Failed to fetch')
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
const DEFAULT_ROI_RESOLUTION = '1920x1080'

const isResolutionKey = (value) => /^\d+x\d+$/.test(String(value || ''))

const normalizeResolutionKey = (value) => (
  isResolutionKey(value) ? String(value) : DEFAULT_ROI_RESOLUTION
)

const normalizeDetectionRegionData = (raw) => {
  const defaults = {
    currentTarget: DEFAULT_ROI_RESOLUTION,
    byTarget: {
      [DEFAULT_ROI_RESOLUTION]: [],
    },
  }

  if (!raw) {
    return cloneValue(defaults)
  }

  if (Array.isArray(raw)) {
    return {
      currentTarget: DEFAULT_ROI_RESOLUTION,
      byTarget: {
        [DEFAULT_ROI_RESOLUTION]: cloneValue(raw),
      },
    }
  }

  const sourceProfiles = raw.byResolution || raw.byTarget || {}
  const byTarget = {}
  Object.entries(sourceProfiles).forEach(([key, regions]) => {
    if (Array.isArray(regions)) {
      byTarget[normalizeResolutionKey(key)] = cloneValue(regions)
    }
  })

  if (Array.isArray(raw.byTarget?.all) && !byTarget[DEFAULT_ROI_RESOLUTION]?.length) {
    byTarget[DEFAULT_ROI_RESOLUTION] = cloneValue(raw.byTarget.all)
  }

  return {
    currentTarget: normalizeResolutionKey(raw.currentTarget),
    byTarget: Object.keys(byTarget).length ? byTarget : cloneValue(defaults.byTarget),
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
  powerLineFrequency: '1',
  fps: '60',
  target: 'high',
}

const normalizeCameraSettings = (raw = {}) => {
  const whiteBalance = raw.whiteBalance || raw.white_balance || CAMERA_DEFAULTS.whiteBalance
  const powerLineFrequency = raw.powerLineFrequency
    ?? raw.power_line_frequency
    ?? CAMERA_DEFAULTS.powerLineFrequency

  return {
    resolution: String(raw.resolution || CAMERA_DEFAULTS.resolution).replace(/\s+/g, ''),
    exposure: String(raw.exposure ?? CAMERA_DEFAULTS.exposure),
    gain: String(raw.gain ?? CAMERA_DEFAULTS.gain),
    whiteBalance: String(whiteBalance || CAMERA_DEFAULTS.whiteBalance),
    powerLineFrequency: String(powerLineFrequency ?? CAMERA_DEFAULTS.powerLineFrequency),
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
          headers: { Accept: 'application/json' },
          cache: 'no-store',
        })
        const data = await response.json()
        if (!response.ok || data.status !== 'success') {
          throw new Error(data.message || `HTTP ${response.status}`)
        }
        this.settings = normalizeCameraSettings(data.data || {})
        saveToStorage(STORAGE_KEY_CAMERA, this.settings)
        return { ...this.settings }
      } catch (error) {
        this.lastSaveResult = { success: false, message: error.message }
        saveToStorage(STORAGE_KEY_CAMERA_STATE, this.lastSaveResult)
        return { ...this.settings }
      }
    },
    async saveSettings(settings) {
      // 用临时对象记录本次实际要保存的值，失败回滚为旧值
      const previousSettings = normalizeCameraSettings(this.settings)
      const nextSettings = normalizeCameraSettings(settings)
      const finalSettings = { ...nextSettings }
      const messages = []
      let exposureSuccess = true
      let gainSuccess = true
      let whiteBalanceSuccess = true
      let powerLineSuccess = true
      let resolutionSuccess = true
      let fpsSuccess = true

      try {
        if (nextSettings.exposure !== previousSettings.exposure) {
          console.log("设置曝光...")
          try {
            const response = await fetch(`${getApiUrl()}/api/stream/exposure`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                value: parseInt(nextSettings.exposure),
                target: nextSettings.target || CAMERA_DEFAULTS.target
              }),
            })
            const data = await response.json()
            if (data.status === 'success') {
              finalSettings.exposure = String(data.data?.exposure ?? nextSettings.exposure)
            } else {
              throw new Error(data.message || '曝光设置失败')
            }
          } catch (err) {
            // 接口异常或业务失败，回滚曝光值
            finalSettings.exposure = previousSettings.exposure
            exposureSuccess = false
            messages.push(`曝光设置失败: ${err.message}`)
          }
        }

        if (nextSettings.gain !== previousSettings.gain) {
          console.log("设置增益...")
          try {
            const response = await fetch(`${getApiUrl()}/api/stream/gain`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                value: parseInt(nextSettings.gain),
                target: nextSettings.target || CAMERA_DEFAULTS.target
              }),
            })
            const data = await response.json()
            if (data.status === 'success') {
              finalSettings.gain = String(data.data?.gain ?? nextSettings.gain)
            } else {
              throw new Error(data.message || '增益设置失败')
            }
          } catch (err) {
            finalSettings.gain = previousSettings.gain
            gainSuccess = false
            messages.push(`增益设置失败: ${err.message}`)
          }
        }

        if (nextSettings.whiteBalance !== previousSettings.whiteBalance) {
          console.log("设置白平衡...")
          try {
            const response = await fetch(`${getApiUrl()}/api/stream/white_balance`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                mode: nextSettings.whiteBalance || CAMERA_DEFAULTS.whiteBalance,
                target: nextSettings.target || CAMERA_DEFAULTS.target
              }),
            })
            const data = await response.json()
            if (data.status === 'success') {
              finalSettings.whiteBalance = String(data.data?.mode ?? nextSettings.whiteBalance)
            } else {
              throw new Error(data.message || '白平衡设置失败')
            }
          } catch (err) {
            finalSettings.whiteBalance = previousSettings.whiteBalance
            whiteBalanceSuccess = false
            messages.push(`白平衡设置失败: ${err.message}`)
          }
        }

        if (nextSettings.powerLineFrequency !== previousSettings.powerLineFrequency) {
          console.log("设置抗频闪...")
          try {
            const response = await fetch(`${getApiUrl()}/api/stream/power_line_frequency`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                value: parseInt(nextSettings.powerLineFrequency),
                target: nextSettings.target || CAMERA_DEFAULTS.target
              }),
            })
            const data = await response.json()
            if (data.status === 'success') {
              finalSettings.powerLineFrequency = String(
                data.data?.power_line_frequency ?? nextSettings.powerLineFrequency
              )
            } else {
              throw new Error(data.message || '抗频闪设置失败')
            }
          } catch (err) {
            finalSettings.powerLineFrequency = previousSettings.powerLineFrequency
            powerLineSuccess = false
            messages.push(`抗频闪设置失败: ${err.message}`)
          }
        }

        const setResolution = async () => {
          console.log("设置分辨率...")
          try {
            const [width, height] = nextSettings.resolution.split('x').map(Number)
            const response = await fetch(`${getApiUrl()}/api/stream/resolution`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                width,
                height,
                target: nextSettings.target
              }),
            })
            const data = await response.json()
            if (data.status === 'success') {
              if (data.data?.fps) {
                finalSettings.fps = String(data.data.fps)
              }
              if (data.data?.width && data.data?.height) {
                finalSettings.resolution = `${data.data.width}x${data.data.height}`
              }
            } else {
              throw new Error(data.message || '分辨率设置失败')
            }
          } catch (err) {
            // 回滚分辨率
            finalSettings.resolution = previousSettings.resolution
            resolutionSuccess = false
            messages.push(`分辨率设置失败: ${err.message}`)
          }
        }

        const setFps = async () => {
          console.log("设置帧率...")
          try {
            const response = await fetch(`${getApiUrl()}/api/stream/fps`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                value: parseInt(nextSettings.fps),
                target: nextSettings.target || CAMERA_DEFAULTS.target
              }),
            })
            const data = await response.json()
            if (data.status === 'success') {
              if (data.data?.fps) {
                finalSettings.fps = String(data.data.fps)
              }
            } else {
              throw new Error(data.message || '帧率设置失败')
            }
          } catch (err) {
            // 接口异常或业务失败，回滚帧率值
            finalSettings.fps = previousSettings.fps
            fpsSuccess = false
            messages.push(`帧率设置失败: ${err.message}`)
          }
        }

        // ---- 处理分辨率 / 帧率 ----
        const resolutionChanged = nextSettings.resolution !== previousSettings.resolution
        const fpsChanged = nextSettings.fps !== previousSettings.fps
        const currentFps = parseInt(previousSettings.fps)
        const nextFps = parseInt(nextSettings.fps)

        // 从高帧率切到高像素时，先降帧再切分辨率，避免临时组合超出相机能力。
        if (fpsChanged && nextFps < currentFps) {
          await setFps()
        }

        if (resolutionChanged) {
          await setResolution()
        }

        if (fpsChanged && nextFps >= currentFps) {
          await setFps()
        }

        // ---- 更新 store 和持久化 ----
        const allSuccess = exposureSuccess
          && gainSuccess
          && whiteBalanceSuccess
          && powerLineSuccess
          && resolutionSuccess
          && fpsSuccess
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
  detectionModel: 'YOLO11',
  detectionThreshold: 0.50,
  overlapRate: 0.10,
  // matchEnabled: true,
  // matchThreshold: 0.50,
  // matchFrequency: 5,
  target: 'all',
}

export const useDetectionSettingStore = defineStore('detectionSetting', {
  state: () => ({
    settings: loadFromStorage(STORAGE_KEY_DETECTION, DETECTION_DEFAULTS),
    lastSaveResult: loadFromStorage(STORAGE_KEY_DETECTION_STATE, { unset: true }),
  }),
  actions: {
    async saveSettings(settings) {
      try {
        const response = await fetch(`${getApiUrl()}/api/detection/detect`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ...settings,
            target: settings.target || DETECTION_DEFAULTS.target
          }),
        })

        const data = await response.json()
        if (!response.ok) {
          throw new Error(data.message || `HTTP ${response.status}`)
        }

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
  currentTarget: DEFAULT_ROI_RESOLUTION,
  byTarget: {
    [DEFAULT_ROI_RESOLUTION]: [],
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
        const { data } = await fetchJsonFromApiCandidates('/api/detection/fetch_regions', {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
        }, getHardwareApiUrlCandidates())
        const rois = Array.isArray(data?.rois)
          ? data.rois
          : (Array.isArray(data?.config?.rois) ? data.config.rois : [])
        const profiles = data?.rois_by_resolution && typeof data.rois_by_resolution === 'object'
          ? data.rois_by_resolution
          : {}
        const currentTarget = normalizeResolutionKey(
          data?.selected_resolution || data?.active_resolution || this.data.currentTarget
        )

        const nextData = {
          currentTarget,
          byTarget: {},
        }

        Object.entries(profiles).forEach(([key, value]) => {
          if (Array.isArray(value)) {
            nextData.byTarget[normalizeResolutionKey(key)] = cloneValue(value)
          }
        })

        if (!nextData.byTarget[currentTarget]) {
          nextData.byTarget[currentTarget] = cloneValue(rois)
        }

        this.data = nextData
        saveToStorage(STORAGE_KEY_DETECTION_REGION, this.data)
        return cloneValue(this.data.byTarget[currentTarget] || [])
      } catch (error) {
        this.lastSaveResult = { success: false, message: error.message }
        saveToStorage(STORAGE_KEY_DETECTION_REGION_STATE, this.lastSaveResult)
        return null
      }
    },
    async saveRegions(rois, options = {}) {
      const target = normalizeResolutionKey(options.target || this.data.currentTarget)
      const clear = Boolean(options.clear)

      try {
        const { data } = await fetchJsonFromApiCandidates('/api/detection/save_regions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            resolution_key: target,
            clear,
            rois: clear ? [] : cloneValue(rois),
          }),
        }, getHardwareApiUrlCandidates())

        if (data.status === 'success') {
          const savedTarget = normalizeResolutionKey(data?.data?.resolution_key || target)
          this.data.currentTarget = savedTarget
          this.data.byTarget[savedTarget] = clear ? [] : cloneValue(rois)
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
      return cloneValue(this.data.byTarget[normalizeResolutionKey(target)] || [])
    },
    getCurrentTarget() {
      return normalizeResolutionKey(this.data.currentTarget)
    },
    setCurrentTarget(target) {
      this.data.currentTarget = normalizeResolutionKey(target)
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
