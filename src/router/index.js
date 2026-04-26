import { createRouter, createWebHistory } from 'vue-router'

// 导入各个模块的路由
import homeRoutes from './home'
import cameraRoutes from './cameraSetting'
import detectionRoutes from './detectionSetting'
import detectionRegionRoutes from './detectionRegion'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    ...homeRoutes,
    ...cameraRoutes,
    ...detectionRoutes,
    ...detectionRegionRoutes
  ]
})

export default router
