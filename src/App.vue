<script setup>
import { RouterView } from 'vue-router'
import AppHeader from "@/components/AppHeader.vue";
import AppFooter from "@/components/AppFooter.vue";
</script>

<template>
  <div class="app-wrapper">
    <AppHeader />

    <main class="main-content">
      <RouterView />
    </main>
    
    <!-- <AppFooter /> -->
  </div>
</template>

<style>
.app-wrapper {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.main-content {
  flex: 1;
  padding-top: 56px; /* Height of navbar */
}

/* Override footer margin for monitor page */
:deep(footer) {
  margin-top: 0 !important;
}
</style>