import { createRouter, createWebHistory } from 'vue-router'

import LogsView from '../views/LogsView.vue'
import MonitorView from '../views/MonitorView.vue'
import PoseView from '../views/PoseView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'monitor', component: MonitorView },
    { path: '/pose', name: 'pose', component: PoseView },
    { path: '/logs', name: 'logs', component: LogsView },
  ],
})
