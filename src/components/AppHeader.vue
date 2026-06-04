<template>
  <aside class="app-sidebar">
    <RouterLink to="/" class="brand-block" aria-label="AI 人员安全相机平台首页">
      <img class="brand-logo" :src="asvLogoUrl" alt="ASV 艾视维" />
      <span class="brand-copy">
        <strong>AI 人员安全相机平台</strong>
      </span>
    </RouterLink>

    <nav class="side-nav" aria-label="主导航">
      <RouterLink
        v-for="item in navItems"
        :key="item.to"
        :to="item.to"
        class="side-nav-link"
        :class="{ active: item.active(route.path) }"
        :title="item.label"
      >
        <span class="side-nav-icon" v-html="item.icon"></span>
        <span class="side-nav-label">{{ item.label }}</span>
      </RouterLink>
    </nav>

    <div class="sidebar-footer">
      <span class="status-pill" :class="runtimeStatusStore.statusClass">
        {{ runtimeStatusStore.statusText }}
      </span>
      <small>{{ runtimeStatusStore.backendHost }}</small>
    </div>
  </aside>

  <header class="app-topbar">
    <div class="topbar-left">
      <span class="module-eyebrow">AI Vision / HMI</span>
      <h1>{{ currentTitle }}</h1>
    </div>

    <div class="topbar-right">
      <span class="topbar-chip" :class="runtimeStatusStore.statusClass">
        <span class="chip-dot"></span>
        {{ runtimeStatusStore.statusText }}
      </span>
      <span class="topbar-time">{{ currentTime }}</span>
    </div>
  </header>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";
import asvLogoUrl from "@/assets/asv-logo.png";
import { useRuntimeStatusStore } from "@/stores/settingsStore";

const route = useRoute();
const runtimeStatusStore = useRuntimeStatusStore();
const currentTime = ref("");
let timer = null;
let statusTimer = null;

const icon = {
  monitor: '<svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="13" rx="2"></rect><path d="M8 21h8"></path><path d="M12 17v4"></path></svg>',
  video: '<svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2"></rect><path d="m10 9 5 3-5 3z"></path></svg>',
  camera: '<svg viewBox="0 0 24 24"><path d="M3 7h4l2-3h6l2 3h4v12H3z"></path><circle cx="12" cy="13" r="4"></circle></svg>',
  detect: '<svg viewBox="0 0 24 24"><path d="M4 4h6v6H4z"></path><path d="M14 4h6v6h-6z"></path><path d="M14 14h6v6h-6z"></path><path d="M4 14h6v6H4z"></path></svg>',
  region: '<svg viewBox="0 0 24 24"><path d="M4 9V4h5"></path><path d="M15 4h5v5"></path><path d="M20 15v5h-5"></path><path d="M9 20H4v-5"></path><path d="M12 8v8"></path><path d="M8 12h8"></path></svg>',
  model: '<svg viewBox="0 0 24 24"><path d="M12 4v12"></path><path d="m7 9 5-5 5 5"></path><path d="M4 20h16"></path></svg>',
  alarm: '<svg viewBox="0 0 24 24"><path d="M12 3 2 20h20L12 3z"></path><path d="M12 9v4"></path><path d="M12 17h.01"></path></svg>',
};

const navItems = [
  { to: "/", label: "实时监控", icon: icon.monitor, active: (path) => path === "/" },
  { to: "/video-page", label: "视频回放", icon: icon.video, active: (path) => path.startsWith("/video-page") },
  { to: "/camera-settings", label: "相机设置", icon: icon.camera, active: (path) => path.startsWith("/camera-settings") },
  { to: "/detection-settings", label: "检测设置", icon: icon.detect, active: (path) => path.startsWith("/detection-settings") },
  { to: "/detection-region", label: "检测区域", icon: icon.region, active: (path) => path.startsWith("/detection-region") },
  { to: "/model-management", label: "模型管理", icon: icon.model, active: (path) => path.startsWith("/model-management") },
  { to: "/exception-output", label: "异常输出", icon: icon.alarm, active: (path) => path.startsWith("/exception-output") },
];

const currentTitle = computed(() => {
  return navItems.find((item) => item.active(route.path))?.label || "AI 人员安全相机平台";
});

const updateTime = () => {
  currentTime.value = new Date().toLocaleString("zh-CN", {
    hour12: false,
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
};

onMounted(() => {
  updateTime();
  timer = setInterval(updateTime, 1000);
  runtimeStatusStore.fetchStatus();
  statusTimer = setInterval(() => runtimeStatusStore.fetchStatus(), 5000);
});

onUnmounted(() => {
  if (timer) clearInterval(timer);
  if (statusTimer) clearInterval(statusTimer);
});
</script>

<style>
.app-sidebar {
  position: fixed;
  inset: 0 auto 0 0;
  z-index: 30;
  width: var(--sidebar-width, 216px);
  display: flex;
  flex-direction: column;
  background: #ffffff;
  border-right: 1px solid var(--industrial-border);
  box-shadow: 4px 0 18px rgba(31, 41, 51, 0.08);
}

.brand-block {
  min-height: 110px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 12px 14px 10px;
  color: var(--industrial-text);
  text-decoration: none;
  background: #ffffff;
  border-bottom: 1px solid rgba(143, 17, 23, 0.14);
  box-shadow: 0 2px 10px rgba(31, 41, 51, 0.08);
}

.brand-logo {
  width: 154px;
  height: auto;
  flex: 0 0 auto;
  display: block;
}

.brand-copy {
  display: grid;
  gap: 2px;
  justify-items: center;
  min-width: 0;
}

.brand-copy strong {
  color: var(--industrial-red-dark);
  font-size: 15px;
  font-weight: 800;
}

.side-nav {
  flex: 1;
  display: grid;
  align-content: start;
  gap: 4px;
  padding: 14px 10px;
  overflow-y: auto;
}

.side-nav-link {
  position: relative;
  min-height: 40px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 12px;
  color: var(--industrial-text);
  text-decoration: none;
  border: 1px solid transparent;
  border-radius: var(--industrial-radius-sm);
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0;
  transition:
    background-color var(--motion-normal),
    border-color var(--motion-normal),
    color var(--motion-normal),
    box-shadow var(--motion-normal),
    opacity var(--motion-normal),
    transform var(--motion-fast);
}

.side-nav-link::before {
  content: "";
  position: absolute;
  left: 0;
  width: 3px;
  height: 18px;
  border-radius: 0 999px 999px 0;
  background: transparent;
  opacity: 0;
  transition:
    background-color var(--motion-normal),
    opacity var(--motion-normal),
    height var(--motion-normal);
}

.side-nav-link:hover {
  color: var(--industrial-red-dark);
  background: var(--industrial-red-soft);
  border-color: var(--industrial-red-line);
  box-shadow: 0 3px 9px rgba(143, 17, 23, 0.06);
  transform: translateY(-1px);
}

.side-nav-link.active {
  color: var(--industrial-red-dark);
  border-color: var(--industrial-red-line);
  background: var(--industrial-red-soft);
  font-weight: 800;
  box-shadow: 0 4px 12px rgba(143, 17, 23, 0.08);
  animation: nav-active-settle 180ms ease-out;
}

.side-nav-link.active::before {
  background: var(--industrial-red);
  opacity: 1;
  height: 22px;
}

.side-nav-icon {
  width: 18px;
  height: 18px;
  flex: 0 0 auto;
  display: inline-flex;
}

.side-nav-icon svg {
  width: 18px;
  height: 18px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.side-nav-label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: inherit;
}

.side-nav-link:active {
  background: #f8dfe2;
  border-color: rgba(193, 18, 31, 0.34);
  box-shadow: 0 2px 7px rgba(143, 17, 23, 0.1) inset;
  transform: translateY(0) scale(0.99);
}

@keyframes nav-active-settle {
  0% {
    background-color: #f8dfe2;
    border-color: rgba(193, 18, 31, 0.34);
    box-shadow: 0 2px 7px rgba(143, 17, 23, 0.1) inset;
  }

  100% {
    background-color: var(--industrial-red-soft);
    border-color: var(--industrial-red-line);
    box-shadow: 0 4px 12px rgba(143, 17, 23, 0.08);
  }
}

.sidebar-footer {
  display: grid;
  gap: 6px;
  padding: 14px 14px 16px;
  border-top: 1px solid var(--industrial-border);
  color: var(--industrial-muted);
}

.sidebar-footer small {
  font-family: "Roboto Mono", Consolas, monospace;
  color: var(--industrial-faint);
}

.app-topbar {
  position: fixed;
  top: 0;
  right: 0;
  left: var(--sidebar-width, 216px);
  z-index: 25;
  height: var(--topbar-height);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 20px;
  background: rgba(255, 255, 255, 0.96);
  border-bottom: 1px solid var(--industrial-border);
}

.app-topbar::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: var(--industrial-red);
}

.topbar-left {
  min-width: 0;
}

.module-eyebrow {
  display: block;
  margin-bottom: 1px;
  color: var(--industrial-faint);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.topbar-left h1 {
  margin: 0;
  color: var(--industrial-text);
  font-size: 17px;
  font-weight: 800;
  line-height: 1.2;
}

.topbar-right {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  min-width: 0;
}

.topbar-chip,
.topbar-time {
  min-height: 34px;
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--industrial-border);
  border-radius: var(--industrial-radius-sm);
  background: var(--industrial-surface);
  box-shadow: var(--industrial-shadow);
}

.topbar-chip {
  gap: 7px;
  padding: 0 10px;
  color: var(--industrial-muted);
  font-size: 12px;
  font-weight: 700;
}

.topbar-chip.success {
  color: var(--industrial-success);
}

.topbar-chip.warning {
  color: var(--industrial-warning);
}

.topbar-chip.danger {
  color: var(--industrial-danger);
}

.chip-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
}

.topbar-time {
  padding: 0 10px;
  color: var(--industrial-muted);
  font-family: "Roboto Mono", Consolas, monospace;
  font-size: 12px;
}

@media (max-width: 900px) {
  .app-sidebar {
    width: 72px;
  }

  .brand-block {
    justify-content: center;
    padding: 14px 8px;
  }

  .brand-copy,
  .side-nav-label,
  .sidebar-footer {
    display: none;
  }

  .brand-logo {
    width: 48px;
  }

  .side-nav {
    padding: 12px 8px;
  }

  .side-nav-link {
    justify-content: center;
    padding: 0;
  }

  .app-topbar {
    left: 72px;
  }
}

@media (max-width: 640px) {
  .app-sidebar {
    top: 56px;
    right: 0;
    bottom: auto;
    width: 100%;
    height: 48px;
    flex-direction: row;
    border-right: 0;
    border-bottom: 1px solid var(--industrial-border);
  }

  .brand-block,
  .sidebar-footer {
    display: none;
  }

  .side-nav {
    display: flex;
    flex: 1;
    gap: 4px;
    padding: 6px 8px;
    overflow-x: auto;
  }

  .side-nav-link {
    flex: 0 0 44px;
  }

  .app-topbar {
    left: 0;
    padding: 0 12px;
  }

  .topbar-time {
    display: none;
  }
}
</style>
