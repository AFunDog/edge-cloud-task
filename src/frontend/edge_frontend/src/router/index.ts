import { createRouter, createWebHistory } from 'vue-router'

import MonitorView from '../views/MonitorView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'monitor', component: MonitorView },
  ],
})
