import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../store/auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    component: () => import('../views/Layout.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('../views/Dashboard.vue'),
      },
      {
        path: 'subscriptions',
        name: 'Subscriptions',
        component: () => import('../views/Subscriptions.vue'),
      },
      {
        path: 'nodes',
        name: 'Nodes',
        component: () => import('../views/Nodes.vue'),
      },
      {
        path: 'networks',
        name: 'Networks',
        component: () => import('../views/Networks.vue'),
      },
      {
        path: 'testing',
        name: 'Testing',
        component: () => import('../views/Testing.vue'),
      },
      {
        path: 'rules',
        name: 'Rules',
        component: () => import('../views/Rules.vue'),
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// Navigation guard
router.beforeEach((to) => {
  const auth = useAuthStore()
  if (!to.meta.public && !auth.isLoggedIn) {
    return { name: 'Login' }
  }
  if (to.name === 'Login' && auth.isLoggedIn) {
    return { name: 'Dashboard' }
  }
})

export default router
