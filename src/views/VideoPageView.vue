<template>
  <div class="video-page">
    <div class="operation-bar">
      <div class="operation-bar-left">
        <div class="page-title-group">
          <h2 class="page-title">视频页面</h2>
        </div>
      </div>

      <div class="operation-bar-right">
        <div class="operation-actions">
          <button class="operation-btn" type="button" title="视频设置" @click="openSettingsModal">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="3"></circle>
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82L4.21 7.2a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h0A1.65 1.65 0 0 0 9.91 3.25V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h0a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
            </svg>
          </button>
        </div>
      </div>
    </div>

    <div class="video-page-intro">
      <p class="video-page-subtitle">按日期查看录像片段。当前默认单个视频保存时长为 1 分钟，可下载已勾选视频；检测目标筛选和删除功能仍需后端继续补充对应接口或字段。</p>
    </div>

    <div class="video-toolbar">
      <div class="toolbar-top">
        <div class="date-tabs">
          <button
            v-for="item in dateOptions"
            :key="item.key"
            class="date-tab"
            :class="{ active: activeDate === item.key }"
            @click="setActiveDate(item.key)"
          >
            {{ item.label }}
          </button>
        </div>

        <div class="toolbar-actions">
          <label class="checkbox-pill select-all-pill" :class="{ mixed: isPartiallyVisibleSelected }">
            <input
              :checked="areAllVisibleVideosSelected"
              :disabled="filteredVideos.length === 0"
              type="checkbox"
              @change="toggleVisibleSelection"
            />
            <span>{{ areAllVisibleVideosSelected ? "取消全选" : "全选" }}</span>
          </label>
          <label class="checkbox-pill">
            <input v-model="showAllVideos" type="checkbox" />
            <span>全部视频</span>
          </label>
          <button class="toolbar-btn" @click="exportVisibleVideos">导出</button>
          <button class="toolbar-btn danger" @click="deleteSelectedVideos">删除</button>
        </div>
      </div>

      <div class="toolbar-bottom">
        <div class="search-row">
          <div class="search-box">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="11" cy="11" r="8"></circle>
              <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
            </svg>
            <input
              v-model.trim="searchKeyword"
              type="text"
              placeholder="按日期搜索"
            />
          </div>

          <div class="calendar-picker">
            <button class="calendar-btn" type="button" @click="openDatePicker" title="选择日期">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="4" width="18" height="18" rx="2"></rect>
                <line x1="16" y1="2" x2="16" y2="6"></line>
                <line x1="8" y1="2" x2="8" y2="6"></line>
                <line x1="3" y1="10" x2="21" y2="10"></line>
              </svg>
            </button>
            <input
              ref="datePickerRef"
              v-model="selectedDate"
              class="native-date-input"
              type="date"
              @change="syncDateFromPicker"
            />
          </div>
        </div>

        <div class="toolbar-summary">
          <span>{{ recordListLoading ? "视频列表加载中..." : `当前显示 ${filteredVideos.length} 个视频` }}</span>
          <span>已选 {{ selectedIds.length }} 个</span>
        </div>
      </div>
    </div>

    <div class="video-grid" v-if="filteredVideos.length">
      <button
        v-for="video in filteredVideos"
        :key="video.id"
        class="video-card"
        @click="openVideo(video)"
      >
        <label class="card-checkbox" @click.stop>
          <input
            :checked="selectedIds.includes(video.id)"
            type="checkbox"
            @change="toggleSelection(video.id)"
          />
          <span></span>
        </label>

        <div class="video-thumb" :class="{ target: video.hasTarget === true }">
          <span class="thumb-play">
            <svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor">
              <path d="M8 5v14l11-7z"></path>
            </svg>
          </span>
          <span class="duration-badge">{{ video.duration }}</span>
          <span class="target-badge" v-if="video.hasTarget === true">检测目标</span>
        </div>

        <div class="video-meta">
          <h3>{{ video.title }}</h3>
          <p>{{ video.displayDate }} {{ video.time }}</p>
        </div>
      </button>
    </div>

    <div v-else class="empty-state">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <rect x="3" y="5" width="18" height="14" rx="2"></rect>
        <path d="M10 9.5l4 2.5-4 2.5z"></path>
      </svg>
      <p>{{ emptyStateMessage }}</p>
    </div>

    <div v-if="activeVideo" class="video-modal" @click.self="closeVideo">
      <div class="video-modal-panel">
        <button class="modal-close" @click="closeVideo">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>

        <div class="player-stage">
          <div class="player-screen" :class="{ 'player-screen-video': activeVideo?.previewUrl && !videoPlaybackError }">
            <img
              v-if="activeVideo?.previewUrl && !videoPlaybackError"
              class="player-video player-preview"
              :src="activeVideo.previewUrl"
              alt=""
              @error="handleVideoError"
            />
            <template v-else>
              <div class="player-overlay-icon">
                <svg width="36" height="36" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M8 5v14l11-7z"></path>
                </svg>
              </div>
              <div class="player-tip">
                {{ videoPlaybackError ? "低清预览暂不可用，请下载高清文件或等待当前分段结束。" : (showDetectionResult ? "检测结果显示已开启，等待后端返回结果" : "检测结果显示已关闭") }}
              </div>
            </template>
          </div>
          <button
            class="result-toggle player-result-toggle"
            :class="{ on: showDetectionResult, off: !showDetectionResult }"
            type="button"
            @click="toggleDetectionResult"
            :title="showDetectionResult ? '关闭检测结果显示' : '开启检测结果显示'"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="4" y="4" width="16" height="16" rx="2"></rect>
              <path d="M9 9h6v6H9z"></path>
            </svg>
          </button>
        </div>

        <div class="player-info">
          <div class="player-info-header">
            <h3>{{ activeVideo.title }}</h3>
            <a
              v-if="activeVideo.downloadUrl"
              class="player-download"
              :href="activeVideo.downloadUrl"
              :download="activeVideo.filename"
              @click.stop
            >
              高清下载
            </a>
          </div>
          <p>{{ activeVideo.displayDate }} {{ activeVideo.time }}</p>
          <div class="player-tags">
            <span>{{ activeVideo.duration }}</span>
            <span>{{ activeVideo.sizeText }}</span>
            <span>{{ activeVideo.hasTarget === true ? '含检测目标' : '检测信息待补充' }}</span>
          </div>
        </div>
      </div>
    </div>

    <div v-if="showSettingsModal" class="settings-modal" @click.self="closeSettingsModal">
      <div class="settings-panel">
        <div class="settings-panel-header">
          <h3>视频设置</h3>
          <button class="settings-close" type="button" @click="closeSettingsModal" :disabled="recordSettingsSaving">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>

        <div class="settings-panel-body">
          <label class="settings-field">
            <span class="settings-label">视频保存时长</span>
            <div class="settings-input-row">
              <input
                v-model.number="recordDurationMin"
                type="number"
                min="1"
                step="1"
                class="settings-input"
                @change="validateRecordDuration"
              />
              <span class="settings-unit">分钟</span>
            </div>
          </label>

          <p class="settings-tip">注意：修改后会在下一个新视频分段开始时生效，当前正在录制的视频不会立刻变化。</p>
          <p v-if="recordSettingsMessage" class="settings-message">{{ recordSettingsMessage }}</p>
        </div>

        <div class="settings-panel-footer">
          <button class="settings-btn secondary" type="button" @click="closeSettingsModal" :disabled="recordSettingsSaving">取消</button>
          <button class="settings-btn primary" type="button" @click="saveRecordSettings" :disabled="recordSettingsSaving">
            {{ recordSettingsSaving ? "保存中..." : "保存" }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { getApiUrl, syncBackendTime } from "@/stores/settingsStore";

const API_URL = getApiUrl();
const DEFAULT_RECORD_DURATION_MIN = 1;
const datePickerRef = ref(null);
const showSettingsModal = ref(false);
const recordDurationMin = ref(DEFAULT_RECORD_DURATION_MIN);
const recordSettingsSaving = ref(false);
const recordSettingsMessage = ref("");
const recordListLoading = ref(false);
const recordListError = ref("");
const currentRecordTarget = ref("cam_high");
const videoPlaybackError = ref(false);

function createDateOptions() {
  return Array.from({ length: 7 }, (_, index) => {
    const date = new Date();
    date.setDate(date.getDate() - index);
    const key = date.toISOString().slice(0, 10);
    const displayDate = `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`;
    return {
      key,
      label: displayDate,
      displayDate,
    };
  });
}

const dateOptions = ref(createDateOptions());
const activeDate = ref(dateOptions.value[0].key);
const selectedDate = ref(dateOptions.value[0].key);
const searchKeyword = ref("");
const showAllVideos = ref(true);
const selectedIds = ref([]);
const activeVideo = ref(null);
const showDetectionResult = ref(true);

function padNumber(value) {
  return String(value).padStart(2, "0");
}

function formatCompactDate(date) {
  return `${date.getFullYear()}${padNumber(date.getMonth() + 1)}${padNumber(date.getDate())}`;
}

function formatCompactTime(date) {
  return `${padNumber(date.getHours())}${padNumber(date.getMinutes())}${padNumber(date.getSeconds())}`;
}

function formatDisplayTime(date) {
  return `${padNumber(date.getHours())}:${padNumber(date.getMinutes())}:${padNumber(date.getSeconds())}`;
}

function formatDurationLabel(totalSeconds) {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${padNumber(minutes)}:${padNumber(seconds)}`;
}

function formatDateKey(date) {
  return `${date.getFullYear()}-${padNumber(date.getMonth() + 1)}-${padNumber(date.getDate())}`;
}

function buildDateOption(dateKey) {
  const date = new Date(`${dateKey}T00:00:00`);
  if (Number.isNaN(date.getTime())) {
    return {
      key: dateKey,
      label: dateKey,
      displayDate: dateKey,
    };
  }

  const displayDate = `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`;
  return {
    key: dateKey,
    label: displayDate,
    displayDate,
  };
}

function syncDateOptionsFromVideos(nextVideos) {
  const recordDateKeys = [...new Set(
    nextVideos
      .map((video) => video.dateKey)
      .filter(Boolean)
  )].sort((a, b) => b.localeCompare(a));

  if (!recordDateKeys.length) {
    dateOptions.value = createDateOptions();
    return;
  }

  dateOptions.value = recordDateKeys.map(buildDateOption);

  const activeHasRecords = nextVideos.some((video) => video.dateKey === activeDate.value);
  if (!activeHasRecords) {
    activeDate.value = recordDateKeys[0];
    selectedDate.value = recordDateKeys[0];
  }
}

function buildAbsoluteApiUrl(path) {
  if (!path) return "";
  if (/^https?:\/\//i.test(path)) return path;
  return new URL(path, API_URL).toString();
}

function parseFilenameToDate(filename) {
  const matched = String(filename || "").match(/^(\d{8})_(\d{6})/);
  if (!matched) return null;

  const [, datePart, timePart] = matched;
  const year = Number(datePart.slice(0, 4));
  const month = Number(datePart.slice(4, 6)) - 1;
  const day = Number(datePart.slice(6, 8));
  const hour = Number(timePart.slice(0, 2));
  const minute = Number(timePart.slice(2, 4));
  const second = Number(timePart.slice(4, 6));
  return new Date(year, month, day, hour, minute, second);
}

function mapRecordItem(item) {
  const startAt = item.start_at ? new Date(item.start_at) : parseFilenameToDate(item.filename);
  const hasValidDate = startAt instanceof Date && !Number.isNaN(startAt.getTime());
  return {
    id: item.filename,
    filename: item.filename,
    title: item.title || String(item.filename || "").replace(/\.[^.]+$/, ""),
    dateKey: item.date_key || (hasValidDate ? formatDateKey(startAt) : activeDate.value),
    displayDate: hasValidDate
      ? `${startAt.getFullYear()}年${startAt.getMonth() + 1}月${startAt.getDate()}日`
      : "未知日期",
    time: hasValidDate ? formatDisplayTime(startAt) : "未知时间",
    duration: Number.isFinite(Number(item.duration_sec))
      ? formatDurationLabel(Math.max(0, Math.round(Number(item.duration_sec))))
      : "--:--",
    sizeText: `${Number(item.size_mb || 0).toFixed(2)} MB`,
    hasTarget: typeof item.has_target === "boolean" ? item.has_target : null,
    downloadUrl: buildAbsoluteApiUrl(item.download_url),
    playUrl: buildAbsoluteApiUrl(item.play_url),
    previewUrl: buildAbsoluteApiUrl(item.preview_url),
  };
}

function createSliceVideo(id, option, startTimeText, hasTarget) {
  const startAt = new Date(`${option.key}T${startTimeText}`);
  return {
    id,
    title: `${formatCompactDate(startAt)}_${formatCompactTime(startAt)}`,
    dateKey: option.key,
    displayDate: option.displayDate,
    time: formatDisplayTime(startAt),
    duration: formatDurationLabel(DEFAULT_RECORD_DURATION_MIN * 60),
    sizeText: "-- MB",
    hasTarget,
    downloadUrl: "",
    playUrl: "",
    previewUrl: "",
  };
}

function createMockVideos() {
  const slicePlan = [
    [
      ["09:12:00", true],
      ["09:12:30", false],
      ["10:46:00", true],
      ["10:46:30", false],
    ],
    [
      ["08:32:00", true],
      ["08:32:30", false],
      ["15:11:00", false],
      ["15:11:30", true],
    ],
    [
      ["11:05:00", true],
      ["11:05:30", false],
      ["16:48:00", true],
      ["16:48:30", false],
    ],
    [
      ["09:57:00", false],
      ["09:57:30", true],
    ],
    [
      ["13:39:00", true],
      ["13:39:30", false],
    ],
    [
      ["17:03:00", false],
      ["17:03:30", true],
    ],
    [
      ["18:25:00", true],
      ["18:25:30", false],
    ],
  ];

  let id = 1;
  return dateOptions.value.flatMap((option, index) =>
    (slicePlan[index] || []).map(([startTimeText, hasTarget]) =>
      createSliceVideo(id++, option, startTimeText, hasTarget)
    )
  );
}

const videos = ref([]);

const filteredVideos = computed(() => {
  const keyword = normalizeDateKeyword(searchKeyword.value);
  const hasKeyword = Boolean(keyword);
  return videos.value.filter((video) => {
    const matchDate = hasKeyword ? true : video.dateKey === activeDate.value;
    const matchTarget = showAllVideos.value ? true : video.hasTarget === true;
    const matchSearch = keyword
      ? normalizeDateKeyword(`${video.title}${video.time}${video.displayDate}${video.dateKey}${video.filename || ""}`).includes(keyword)
      : true;
    return matchDate && matchTarget && matchSearch;
  });
});

const visibleVideoIds = computed(() => filteredVideos.value.map((video) => video.id));

const areAllVisibleVideosSelected = computed(() => {
  return visibleVideoIds.value.length > 0
    && visibleVideoIds.value.every((id) => selectedIds.value.includes(id));
});

const isPartiallyVisibleSelected = computed(() => {
  return !areAllVisibleVideosSelected.value
    && visibleVideoIds.value.some((id) => selectedIds.value.includes(id));
});

const emptyStateMessage = computed(() => {
  if (recordListLoading.value) return "视频列表加载中...";
  if (recordListError.value) return recordListError.value;
  if (videos.value.length) {
    const availableDates = dateOptions.value
      .slice(0, 4)
      .map((item) => item.label)
      .join("、");
    return availableDates
      ? `当前筛选条件下暂无视频。已有录像日期：${availableDates}`
      : "当前筛选条件下暂无视频";
  }
  return "当前筛选条件下暂无视频";
});

function normalizeDateKeyword(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/\s+/g, "")
    .replace(/年/g, "-")
    .replace(/月/g, "-")
    .replace(/日/g, "")
    .replace(/[/.]/g, "-");
}

const setActiveDate = (dateKey) => {
  activeDate.value = dateKey;
  selectedDate.value = dateKey;
};

const openDatePicker = () => {
  datePickerRef.value?.showPicker?.();
  datePickerRef.value?.focus();
};

const syncDateFromPicker = () => {
  if (!selectedDate.value) return;
  setActiveDate(selectedDate.value);
};

const toggleDetectionResult = () => {
  showDetectionResult.value = !showDetectionResult.value;
};

const validateRecordDuration = () => {
  const value = Number(recordDurationMin.value);
  if (!Number.isFinite(value) || value <= 0) {
    recordDurationMin.value = DEFAULT_RECORD_DURATION_MIN;
    return;
  }
  recordDurationMin.value = Math.max(1, Math.round(value));
};

const fetchRecordConfig = async () => {
  const response = await fetch(`${API_URL}/api/record/config`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  const data = await response.json();

  if (!response.ok || data.status !== "success") {
    throw new Error(data.message || `HTTP ${response.status}`);
  }

  recordDurationMin.value = Number(data.duration_min ?? DEFAULT_RECORD_DURATION_MIN);
  validateRecordDuration();
};

const openSettingsModal = async () => {
  showSettingsModal.value = true;
  recordSettingsMessage.value = "";
  try {
    await fetchRecordConfig();
  } catch (error) {
    recordSettingsMessage.value = `读取失败：${error.message}`;
  }
};

const closeSettingsModal = () => {
  if (recordSettingsSaving.value) return;
  showSettingsModal.value = false;
};

const saveRecordSettings = async () => {
  validateRecordDuration();
  recordSettingsSaving.value = true;
  recordSettingsMessage.value = "";

  try {
    const response = await fetch(`${API_URL}/api/record/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        duration_min: Number(recordDurationMin.value),
      }),
    });
    const data = await response.json();

    if (!response.ok || data.status !== "success") {
      throw new Error(data.message || `HTTP ${response.status}`);
    }

    recordSettingsMessage.value = data.message || "保存成功";
    setTimeout(() => {
      showSettingsModal.value = false;
    }, 500);
  } catch (error) {
    recordSettingsMessage.value = `保存失败：${error.message}`;
  } finally {
    recordSettingsSaving.value = false;
  }
};

const fetchRecordList = async () => {
  recordListLoading.value = true;
  recordListError.value = "";

  try {
    const params = new URLSearchParams({
      target: currentRecordTarget.value,
    });
    const response = await fetch(`${API_URL}/api/record/list?${params.toString()}`, {
      method: "GET",
      headers: { Accept: "application/json" },
    });
    const data = await response.json();

    if (!response.ok || data.status !== "success") {
      throw new Error(data.message || `HTTP ${response.status}`);
    }

    const nextVideos = Array.isArray(data.data)
      ? data.data
          .map(mapRecordItem)
          .filter((video) => Number.parseFloat(video.sizeText) > 0)
      : [];

    videos.value = nextVideos;
    syncDateOptionsFromVideos(nextVideos);
    selectedIds.value = selectedIds.value.filter((id) => videos.value.some((video) => video.id === id));
  } catch (error) {
    videos.value = createMockVideos();
    syncDateOptionsFromVideos(videos.value);
    recordListError.value = `读取后端视频列表失败，当前展示本地模拟数据：${error.message}`;
  } finally {
    recordListLoading.value = false;
  }
};

const toggleSelection = (id) => {
  if (selectedIds.value.includes(id)) {
    selectedIds.value = selectedIds.value.filter((item) => item !== id);
  } else {
    selectedIds.value = [...selectedIds.value, id];
  }
};

const toggleVisibleSelection = () => {
  const visibleIds = visibleVideoIds.value;
  if (!visibleIds.length) return;

  if (areAllVisibleVideosSelected.value) {
    const visibleIdSet = new Set(visibleIds);
    selectedIds.value = selectedIds.value.filter((id) => !visibleIdSet.has(id));
    return;
  }

  selectedIds.value = [...new Set([...selectedIds.value, ...visibleIds])];
};

const deleteSelectedVideos = () => {
  if (!selectedIds.value.length) {
    window.alert("请先勾选要删除的视频。");
    return;
  }
  const confirmed = window.confirm(`确定删除已选中的 ${selectedIds.value.length} 个视频吗？此操作会删除后端磁盘里的真实文件。`);
  if (!confirmed) return;

  deleteSelectedVideosRequest();
};

const deleteSelectedVideosRequest = async () => {
  try {
    const response = await fetch(`${API_URL}/api/record/delete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target: currentRecordTarget.value,
        filenames: selectedIds.value,
      }),
    });
    const data = await response.json();

    if (!response.ok || data.status !== "success") {
      throw new Error(data.message || `HTTP ${response.status}`);
    }

    const deletedSet = new Set(data.deleted || []);
    videos.value = videos.value.filter((video) => !deletedSet.has(video.filename));
    selectedIds.value = [];

    if (activeVideo.value && deletedSet.has(activeVideo.value.filename)) {
      activeVideo.value = null;
    }

    if (Array.isArray(data.not_found) && data.not_found.length) {
      window.alert(`部分文件未找到，可能已被删除：${data.not_found.join("、")}`);
    }
  } catch (error) {
    window.alert(`删除失败：${error.message}`);
  }
};

const exportVisibleVideos = () => {
  const exportTargets = videos.value.filter((video) => selectedIds.value.includes(video.id));

  if (!exportTargets.length) {
    window.alert("请先勾选要导出的视频。");
    return;
  }

  exportTargets.forEach((video) => {
    const anchor = document.createElement("a");
    anchor.href = video.downloadUrl || buildAbsoluteApiUrl(`/api/record/download?target=${currentRecordTarget.value}&filename=${encodeURIComponent(video.filename)}`);
    anchor.download = video.filename;
    anchor.click();
  });
};

const openVideo = (video) => {
  activeVideo.value = video;
  showDetectionResult.value = true;
  videoPlaybackError.value = false;
};

const closeVideo = () => {
  activeVideo.value = null;
};

const handleVideoError = () => {
  videoPlaybackError.value = true;
};

watch(activeDate, () => {
  selectedIds.value = selectedIds.value.filter((id) =>
    filteredVideos.value.some((video) => video.id === id)
  );
});

watch(filteredVideos, () => {
  selectedIds.value = selectedIds.value.filter((id) =>
    filteredVideos.value.some((video) => video.id === id)
  );
});

onMounted(async () => {
  await syncBackendTime(API_URL).catch(() => {});
  await Promise.allSettled([fetchRecordConfig(), fetchRecordList()]);
});
</script>

<style scoped>
.video-page {
  min-height: calc(100vh - 56px);
  background: #0d1117;
  color: #e6edf3;
  padding: 0 0 24px;
}

.operation-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 16px;
  background: #161b22;
  border-bottom: 1px solid #30363d;
  flex-shrink: 0;
  gap: 16px;
}

.operation-bar-left {
  display: flex;
  align-items: center;
  min-width: 0;
}

.operation-bar-right {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-title-group {
  display: flex;
  align-items: center;
}

.page-title {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  color: #e6edf3;
}

.operation-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.operation-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 36px;
  padding: 0;
  background: #21262d;
  border: 1px solid #30363d;
  border-radius: 6px;
  color: #8b949e;
  cursor: pointer;
  transition: all 0.2s;
}

.operation-btn:hover {
  background: #30363d;
  color: #c9d1d9;
  border-color: #8b949e;
}

.video-page-intro {
  padding: 16px 24px 0;
}

.video-page-subtitle {
  margin: 0 0 16px;
  color: #8b949e;
  font-size: 0.95rem;
  line-height: 1.6;
}

.modal-close {
  width: 42px;
  height: 42px;
  border: 1px solid #30363d;
  border-radius: 10px;
  background: #161b22;
  color: #c9d1d9;
  cursor: pointer;
}

.video-toolbar {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 16px;
  padding: 16px;
  margin: 0 24px 20px;
}

.toolbar-top,
.toolbar-bottom {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.toolbar-bottom {
  margin-top: 14px;
}

.search-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.date-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.date-tab,
.toolbar-btn {
  height: 36px;
  padding: 0 14px;
  border-radius: 10px;
  border: 1px solid #30363d;
  background: #21262d;
  color: #c9d1d9;
  cursor: pointer;
  white-space: nowrap;
}

.date-tab.active {
  background: #1f6feb;
  border-color: #1f6feb;
  color: #ffffff;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: nowrap;
  align-self: flex-start;
}

.checkbox-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 36px;
  min-width: 148px;
  padding: 0 16px;
  border-radius: 10px;
  border: 1px solid #30363d;
  background: #21262d;
  color: #c9d1d9;
  white-space: nowrap;
}

.checkbox-pill span {
  white-space: nowrap;
}

.select-all-pill {
  min-width: 116px;
}

.select-all-pill.mixed {
  border-color: rgba(47, 129, 247, 0.48);
  color: #79c0ff;
}

.checkbox-pill input:disabled + span {
  color: #6e7681;
}

.toolbar-btn {
  min-width: 84px;
  writing-mode: horizontal-tb;
  text-orientation: mixed;
}

.toolbar-btn.danger {
  background: rgba(248, 81, 73, 0.15);
  border-color: rgba(248, 81, 73, 0.35);
  color: #ffb4aa;
}

.search-box {
  width: 280px;
  max-width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 14px;
  height: 40px;
  border-radius: 10px;
  border: 1px solid #30363d;
  background: #0d1117;
  color: #8b949e;
}

.search-box input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  color: #e6edf3;
}

.calendar-picker {
  position: relative;
}

.calendar-btn {
  width: 40px;
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #30363d;
  border-radius: 10px;
  background: #21262d;
  color: #c9d1d9;
  cursor: pointer;
}

.native-date-input {
  position: absolute;
  inset: 0;
  opacity: 0;
  pointer-events: none;
}

.toolbar-summary {
  display: flex;
  gap: 18px;
  color: #8b949e;
  font-size: 0.9rem;
  justify-content: flex-end;
  text-align: right;
}

.video-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
  gap: 18px;
  padding: 0 24px;
}

.video-card {
  position: relative;
  padding: 0;
  text-align: left;
  border: 1px solid #30363d;
  border-radius: 16px;
  overflow: hidden;
  background: #161b22;
  color: inherit;
  cursor: pointer;
}

.video-thumb {
  height: 150px;
  position: relative;
  background:
    linear-gradient(180deg, rgba(13, 17, 23, 0.1), rgba(13, 17, 23, 0.7)),
    linear-gradient(135deg, #2f81f7, #1f6feb 45%, #0d1117);
}

.video-thumb.target {
  background:
    linear-gradient(180deg, rgba(13, 17, 23, 0.15), rgba(13, 17, 23, 0.72)),
    linear-gradient(135deg, #2ea043, #238636 45%, #0d1117);
}

.thumb-play {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(255, 255, 255, 0.92);
}

.duration-badge,
.target-badge {
  position: absolute;
  left: 12px;
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 0.78rem;
}

.duration-badge {
  bottom: 12px;
  background: rgba(13, 17, 23, 0.72);
}

.target-badge {
  top: 12px;
  background: rgba(255, 255, 255, 0.14);
}

.video-meta {
  padding: 14px 14px 16px;
}

.video-meta h3 {
  margin: 0 0 8px;
  font-size: 1rem;
}

.video-meta p {
  margin: 0;
  color: #8b949e;
  font-size: 0.88rem;
}

.card-checkbox {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 1;
}

.card-checkbox input {
  display: none;
}

.card-checkbox span {
  display: inline-block;
  width: 18px;
  height: 18px;
  border-radius: 5px;
  border: 1px solid rgba(255, 255, 255, 0.45);
  background: rgba(13, 17, 23, 0.35);
}

.card-checkbox input:checked + span {
  background: #1f6feb;
  border-color: #1f6feb;
}

.empty-state {
  min-height: 320px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin: 0 24px;
  border: 1px dashed #30363d;
  border-radius: 16px;
  color: #8b949e;
}

.video-modal {
  position: fixed;
  inset: 0;
  background: rgba(1, 4, 9, 0.72);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 84px 24px 24px;
  z-index: 30;
  overflow-y: auto;
}

.video-modal-panel {
  position: relative;
  width: min(920px, 100%);
  border-radius: 20px;
  border: 1px solid #30363d;
  background: #161b22;
  padding: 20px;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.35);
}

.player-stage {
  position: relative;
}

.result-toggle {
  width: 42px;
  height: 42px;
  border: 1px solid transparent;
  border-radius: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
}

.result-toggle.on {
  color: #ffffff;
  background: #238636;
  border-color: #2ea043;
}

.result-toggle.off {
  color: #ffffff;
  background: #da3633;
  border-color: #f85149;
}

.modal-close {
  position: absolute;
  top: 18px;
  right: 18px;
  z-index: 2;
}

.player-screen {
  position: relative;
  height: min(52vh, 420px);
  min-height: 300px;
  border-radius: 16px;
  background:
    linear-gradient(180deg, rgba(13, 17, 23, 0.25), rgba(13, 17, 23, 0.78)),
    linear-gradient(135deg, #2f81f7, #1f6feb 45%, #0d1117);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
}

.player-screen-video {
  padding: 0;
  overflow: hidden;
}

.player-video {
  width: 100%;
  height: 100%;
  object-fit: contain;
  border-radius: 16px;
  background: #000000;
}

.player-preview {
  display: block;
}

.player-result-toggle {
  position: absolute;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  z-index: 2;
}

.player-overlay-icon {
  width: 76px;
  height: 76px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.14);
  display: flex;
  align-items: center;
  justify-content: center;
}

.player-tip {
  color: rgba(255, 255, 255, 0.92);
  font-size: 0.95rem;
}

.player-info {
  margin-top: 18px;
}

.player-info-header {
  display: flex;
  align-items: center;
  gap: 16px;
}

.player-download {
  margin-left: auto;
  padding: 7px 12px;
  border-radius: 10px;
  border: 1px solid #30363d;
  background: #21262d;
  color: #c9d1d9;
  font-size: 0.88rem;
  font-weight: 700;
  text-decoration: none;
}

.player-download:hover {
  color: #ffffff;
  border-color: #1f6feb;
  background: #1f6feb;
}

.player-info h3 {
  margin: 0 0 8px;
  font-size: 1.2rem;
}

.player-info p {
  margin: 0;
  color: #8b949e;
}

.player-tags {
  margin-top: 12px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.player-tags span {
  padding: 5px 10px;
  border-radius: 999px;
  background: #21262d;
  color: #c9d1d9;
  font-size: 0.85rem;
}

.date-tab {
  white-space: nowrap;
}

.settings-modal {
  position: fixed;
  inset: 0;
  background: rgba(1, 4, 9, 0.72);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  z-index: 40;
}

.settings-panel {
  width: min(460px, 100%);
  border: 1px solid #30363d;
  border-radius: 18px;
  background: #161b22;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.35);
}

.settings-panel-header,
.settings-panel-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 20px;
}

.settings-panel-header {
  border-bottom: 1px solid #30363d;
}

.settings-panel-header h3 {
  margin: 0;
  font-size: 1.05rem;
}

.settings-close {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  border: 1px solid #30363d;
  background: #21262d;
  color: #c9d1d9;
  cursor: pointer;
}

.settings-panel-body {
  padding: 20px;
}

.settings-field {
  display: block;
}

.settings-label {
  display: block;
  margin-bottom: 10px;
  color: #c9d1d9;
  font-size: 0.95rem;
}

.settings-input-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.settings-input {
  flex: 1;
  height: 42px;
  padding: 0 14px;
  border-radius: 10px;
  border: 1px solid #30363d;
  background: #0d1117;
  color: #e6edf3;
  outline: none;
}

.settings-unit {
  color: #8b949e;
  white-space: nowrap;
}

.settings-tip,
.settings-message {
  margin: 14px 0 0;
  color: #8b949e;
  font-size: 0.9rem;
  line-height: 1.6;
}

.settings-panel-footer {
  justify-content: flex-end;
  gap: 10px;
  border-top: 1px solid #30363d;
}

.settings-btn {
  min-width: 84px;
  height: 38px;
  padding: 0 14px;
  border-radius: 10px;
  border: 1px solid #30363d;
  cursor: pointer;
}

.settings-btn.secondary {
  background: #21262d;
  color: #c9d1d9;
}

.settings-btn.primary {
  background: #1f6feb;
  border-color: #1f6feb;
  color: #ffffff;
}

@media (max-width: 900px) {
  .toolbar-top,
  .toolbar-bottom {
    flex-direction: column;
    align-items: stretch;
  }

  .toolbar-actions,
  .toolbar-summary {
    justify-content: space-between;
  }

  .toolbar-actions {
    flex-wrap: wrap;
  }

  .search-row {
    width: 100%;
  }

  .search-box {
    width: 100%;
  }

  .player-screen {
    height: 300px;
    min-height: 260px;
  }
}

@media (max-width: 640px) {
  .video-page {
    padding-bottom: 16px;
  }

  .video-page-intro,
  .video-grid {
    padding-left: 16px;
    padding-right: 16px;
  }

  .video-toolbar,
  .empty-state {
    margin-left: 16px;
    margin-right: 16px;
  }

  .video-grid {
    grid-template-columns: 1fr;
  }

  .toolbar-actions {
    flex-wrap: wrap;
  }

  .search-row {
    flex-wrap: wrap;
  }

  .video-modal {
    padding: 72px 12px 12px;
  }

  .video-modal-panel {
    padding: 16px;
  }
}
</style>

<style scoped>
.video-page {
  min-height: calc(100vh - var(--topbar-height));
  padding: 16px 16px 24px;
  color: var(--industrial-text);
  background: transparent;
}

.operation-bar,
.video-toolbar,
.video-card,
.empty-state,
.video-modal-panel,
.settings-panel {
  background: var(--industrial-surface);
  border: 1px solid var(--industrial-border);
  border-radius: var(--industrial-radius);
  box-shadow: var(--industrial-shadow);
}

.operation-bar {
  position: relative;
  min-height: 58px;
  padding: 10px 14px 10px 18px;
  margin-bottom: 14px;
}

.operation-bar::before,
.video-toolbar::before,
.settings-panel-header::before {
  content: "";
  position: absolute;
  left: 0;
  top: 12px;
  bottom: 12px;
  width: 3px;
  border-radius: 0 999px 999px 0;
  background: var(--industrial-red);
}

.page-title {
  color: var(--industrial-text);
  font-size: 18px;
  font-weight: 800;
}

.page-title::after {
  content: "录像检索与回放";
  display: block;
  margin-top: 2px;
  color: var(--industrial-faint);
  font-size: 12px;
  font-weight: 600;
}

.video-page-intro {
  padding: 0;
}

.video-page-subtitle {
  margin: 0 0 14px;
  color: var(--industrial-muted);
  font-size: 13px;
}

.operation-btn,
.date-tab,
.toolbar-btn,
.calendar-btn,
.modal-close,
.settings-close,
.settings-btn,
.result-toggle {
  color: var(--industrial-muted);
  background: var(--industrial-surface-subtle);
  border: 1px solid var(--industrial-border);
  border-radius: var(--industrial-radius-sm);
  box-shadow: var(--industrial-shadow);
}

.operation-btn:hover,
.date-tab:hover,
.toolbar-btn:hover,
.calendar-btn:hover,
.modal-close:hover,
.settings-close:hover,
.settings-btn.secondary:hover,
.result-toggle:hover {
  color: var(--industrial-red-dark);
  background: var(--industrial-red-soft);
  border-color: rgba(185, 28, 28, 0.24);
  box-shadow: var(--industrial-shadow-hover);
}

.date-tab.active,
.settings-btn.primary,
.result-toggle.on {
  color: #ffffff;
  background: var(--industrial-red);
  border-color: var(--industrial-red);
}

.toolbar-btn.danger {
  color: var(--industrial-danger);
  background: var(--industrial-danger-soft);
  border-color: rgba(197, 48, 48, 0.26);
}

.video-toolbar {
  position: relative;
  margin: 0 0 18px;
  padding: 16px;
}

.search-box,
.settings-input {
  height: 36px;
  color: var(--industrial-text);
  background: var(--industrial-surface);
  border: 1px solid var(--industrial-border);
  border-radius: var(--industrial-radius-sm);
}

.search-box input,
.settings-input {
  color: var(--industrial-text);
}

.search-box input::placeholder {
  color: var(--industrial-faint);
}

.checkbox-pill {
  height: 36px;
  color: var(--industrial-muted);
  background: var(--industrial-surface-subtle);
  border: 1px solid var(--industrial-border);
  border-radius: var(--industrial-radius-sm);
}

.toolbar-summary {
  color: var(--industrial-muted);
  font-size: 12px;
}

.video-grid {
  padding: 0;
  gap: 14px;
}

.video-card {
  overflow: hidden;
  color: var(--industrial-text);
  transition:
    border-color var(--motion-normal),
    box-shadow var(--motion-normal),
    transform var(--motion-fast);
}

.video-card:hover {
  border-color: rgba(185, 28, 28, 0.24);
  box-shadow: var(--industrial-shadow-hover);
  transform: translateY(-1px);
}

.video-thumb,
.video-thumb.target,
.player-screen {
  background:
    linear-gradient(180deg, rgba(15, 23, 42, 0.08), rgba(15, 23, 42, 0.72)),
    linear-gradient(135deg, #4b5563 0%, #111827 56%, #2f1115 100%);
}

.video-thumb {
  height: 142px;
}

.duration-badge,
.target-badge,
.player-tags span {
  color: #ffffff;
  background: rgba(15, 23, 42, 0.72);
  border: 1px solid rgba(255, 255, 255, 0.12);
}

.video-meta h3,
.player-info h3,
.settings-panel-header h3 {
  color: var(--industrial-text);
  font-weight: 800;
}

.video-meta p,
.player-info p,
.settings-label,
.settings-tip,
.settings-message {
  color: var(--industrial-muted);
}

.card-checkbox span {
  border-color: rgba(255, 255, 255, 0.65);
  background: rgba(15, 23, 42, 0.48);
}

.card-checkbox input:checked + span {
  background: var(--industrial-red);
  border-color: var(--industrial-red);
}

.empty-state {
  min-height: 280px;
  margin: 0;
  color: var(--industrial-muted);
  border-style: dashed;
  background: rgba(255, 255, 255, 0.72);
}

.video-modal,
.settings-modal {
  background: rgba(31, 41, 51, 0.62);
}

.video-modal-panel,
.settings-panel {
  border-radius: 10px;
}

.player-screen {
  border: 1px solid #273244;
  border-radius: var(--industrial-radius);
}

.player-screen-video {
  background: #0b1018;
}

.player-video {
  border-radius: var(--industrial-radius);
}

.player-download {
  color: var(--industrial-muted);
  background: var(--industrial-surface-subtle);
  border-color: var(--industrial-border);
}

.player-download:hover {
  color: #ffffff;
  background: var(--industrial-red);
  border-color: var(--industrial-red);
}

.result-toggle.off {
  color: var(--industrial-danger);
  background: var(--industrial-danger-soft);
  border-color: rgba(197, 48, 48, 0.26);
}

.settings-panel-header,
.settings-panel-footer {
  border-color: var(--industrial-border);
}

.settings-panel-header {
  position: relative;
}

.settings-panel-body {
  background: var(--industrial-surface);
}

@media (max-width: 900px) {
  .video-page {
    padding: 12px;
  }
}
</style>
