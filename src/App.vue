<script setup>
import { onMounted } from "vue";
import { RouterView } from "vue-router";
import AppHeader from "@/components/AppHeader.vue";
import { syncBackendTime } from "@/stores/settingsStore";

onMounted(() => {
  syncBackendTime().catch(() => {});
});
</script>

<template>
  <div class="app-shell">
    <AppHeader />

    <main class="main-content">
      <RouterView />
    </main>
  </div>
</template>

<style>
.app-shell {
  min-height: 100vh;
  background: var(--industrial-bg);
}

.main-content {
  position: relative;
  z-index: 1;
  width: auto;
  max-width: none;
  min-height: 100vh;
  min-width: 0;
  margin-left: var(--sidebar-width, 216px);
  padding: calc(var(--topbar-height, 56px) + 16px) 16px 32px;
  overflow-x: hidden;
}

@media (max-width: 900px) {
  .main-content {
    margin-left: 72px;
  }
}

@media (max-width: 640px) {
  .main-content {
    margin-left: 0;
    padding: 120px 10px 24px;
  }
}
</style>
