import { createRouter, createWebHistory } from 'vue-router'

import AgentView from '../views/AgentView.vue'
import EventsView from '../views/EventsView.vue'
import KnowledgeView from '../views/KnowledgeView.vue'
import LogsView from '../views/LogsView.vue'
import MonitorView from '../views/MonitorView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'monitor', component: MonitorView },
    { path: '/events', name: 'events', component: EventsView },
    { path: '/agent', name: 'agent', component: AgentView },
    { path: '/logs', name: 'logs', component: LogsView },
    { path: '/knowledge', name: 'knowledge', component: KnowledgeView },
  ],
})
