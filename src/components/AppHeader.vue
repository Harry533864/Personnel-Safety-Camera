<template>
  <header>
    <nav class="navbar navbar-expand-lg navbar-dark bg-primary fixed-top">
      <div class="container-fluid">
        <RouterLink to="/" class="navbar-brand">VueJS with Flask</RouterLink>
        <button
          class="navbar-toggler"
          type="button"
          data-bs-toggle="collapse"
          data-bs-target="#navbarSupportedContent"
          aria-controls="navbarSupportedContent"
          aria-expanded="false"
          aria-label="Toggle navigation"
        >
          <span class="navbar-toggler-icon"></span>
        </button>
        <div class="collapse navbar-collapse" id="navbarSupportedContent">
          <ul class="navbar-nav me-auto">
            <li class="nav-item">
              <RouterLink to="/" class="nav-link" :class="{ active: route.path === '/' }">Home</RouterLink>
            </li>
            <li class="nav-item">
              <RouterLink to="/about" class="nav-link" :class="{ active: route.path.startsWith('/about') }">About</RouterLink>
            </li>
          </ul>
        </div>

        <div class="nav-icon-group">
          <RouterLink
            to="/"
            class="nav-icon-btn"
            :class="{ active: isCameraPage }"
            title="相机页面"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path>
              <circle cx="12" cy="13" r="4"></circle>
            </svg>
          </RouterLink>

          <RouterLink
            to="/video-page"
            class="nav-icon-btn"
            :class="{ active: isVideoPage }"
            title="视频页面"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="5" width="18" height="14" rx="2"></rect>
              <path d="M10 9.5l4 2.5-4 2.5z"></path>
            </svg>
          </RouterLink>
        </div>
      </div>
    </nav>
  </header>
</template>

<script setup>
import { computed } from "vue";
import { RouterLink, useRoute } from "vue-router";

const route = useRoute();

const isVideoPage = computed(() => route.path.startsWith("/video-page"));
const isCameraPage = computed(() => !isVideoPage.value);
</script>

<style>
.nav-icon-group {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.nav-icon-btn {
  width: 42px;
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: rgba(255, 255, 255, 0.78);
  text-decoration: none;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.08);
  transition: all 0.2s ease;
}

.nav-icon-btn:hover {
  color: #ffffff;
  background: rgba(255, 255, 255, 0.16);
}

.nav-icon-btn.active {
  color: #0d6efd;
  background: #ffffff;
  border-color: #ffffff;
}
</style>
