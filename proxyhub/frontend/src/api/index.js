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
  batchRename: (node_ids = null) => api.post('/nodes/batch/rename', { node_ids }),
  batchTag: (node_ids = null) => api.post('/nodes/batch/tag', { node_ids }),
  batchUnquarantine: (node_ids = null) => api.post('/nodes/batch/unquarantine', { node_ids }),
}

// ─── Networks ────────────────────────────────────────
export const networkApi = {
  list: () => api.get('/networks/'),
  create: (data) => api.post('/networks/', data),
  update: (id, data) => api.put(`/networks/${id}`, data),
  remove: (id) => api.delete(`/networks/${id}`),
  resetToken: (id) => api.post(`/networks/${id}/reset-token`),
  getNodes: (id) => api.get(`/networks/${id}/nodes`),
  addNodes: (id, nodeIds) => api.post(`/networks/${id}/nodes`, { node_ids: nodeIds }),
  removeNode: (networkId, nodeId) => api.delete(`/networks/${networkId}/nodes/${nodeId}`),
  smartSelect: (id, data = { max_total: 50, max_per_country: 5, prefer_clean: true }) =>
    api.post(`/networks/${id}/smart-select`, data),
}

// ─── Testing ─────────────────────────────────────────
export const testApi = {
  tcpPing: (data) => api.post('/test/tcp-ping', data),
  latency: (data) => api.post('/test/latency', data),
  proxySpeed: (data) => api.post('/test/proxy-speed', data),
  bandwidth: (data) => api.post('/test/bandwidth', data),
  purity: (data) => api.post('/test/purity', data),
  full: (data) => api.post('/test/full', data),
  getProgress: () => api.get('/test/progress'),
  results: (params) => api.get('/test/results', { params }),
}

// ─── Backup & Restore ─────────────────────────────────
export const backupApi = {
  exportUrl: '/api/backup/export',
  importBackup: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return api.post('/backup/import', fd)
  },
}

// ─── Traffic ─────────────────────────────────────────
export const trafficApi = {
  usage: () => api.get('/traffic/usage'),
  config: () => api.get('/traffic/config'),
  updateConfig: (data) => api.put('/traffic/config', data),
}

// ─── Rules ───────────────────────────────────────────
export const rulesApi = {
  list: () => api.get('/rules/'),
  create: (data) => api.post('/rules/', data),
  update: (id, data) => api.put(`/rules/${id}`, data),
  remove: (id) => api.delete(`/rules/${id}`),
  batchDelete: (ids) => api.delete('/rules/batch/delete', { data: ids }),
  parseText: (text) => api.post('/rules/parse-text', { text }),
}
