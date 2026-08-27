import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// Attach JWT token automatically
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Handle 401 → redirect to login
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default api

// ─── Auth ───────────────────────────────────────────
export const authApi = {
  login: (username, password) => {
    const form = new FormData()
    form.append('username', username)
    form.append('password', password)
    return api.post('/auth/token', form)
  },
}

// ─── Subscriptions ───────────────────────────────────
export const subApi = {
  list: () => api.get('/subscriptions/'),
  create: (data) => api.post('/subscriptions/', data),
  update: (id, data) => api.put(`/subscriptions/${id}`, data),
  remove: (id) => api.delete(`/subscriptions/${id}`),
  refresh: (id) => api.post(`/subscriptions/${id}/refresh`),
}

// ─── Nodes ───────────────────────────────────────────
export const nodeApi = {
  list: (params) => api.get('/nodes/', { params }),
  create: (data) => api.post('/nodes/', data),
  remove: (id) => api.delete(`/nodes/${id}`),
  batchDelete: (ids) => api.delete('/nodes/batch/delete', { data: ids }),
}

// ─── Networks ────────────────────────────────────────
export const networkApi = {
  list: () => api.get('/networks/'),
  create: (data) => api.post('/networks/', data),
  update: (id, data) => api.put(`/networks/${id}`, data),
  remove: (id) => api.delete(`/networks/${id}`),
  getNodes: (id) => api.get(`/networks/${id}/nodes`),
  addNodes: (id, nodeIds) => api.post(`/networks/${id}/nodes`, { node_ids: nodeIds }),
  removeNode: (networkId, nodeId) => api.delete(`/networks/${networkId}/nodes/${nodeId}`),
}

// ─── Testing ─────────────────────────────────────────
export const testApi = {
  tcpPing: (data) => api.post('/test/tcp-ping', data),
  proxySpeed: (data) => api.post('/test/proxy-speed', data),
  purity: (data) => api.post('/test/purity', data),
  full: (data) => api.post('/test/full', data),
  results: (params) => api.get('/test/results', { params }),
}
