import authClient from './authClient'
import discoveryClient from './discoveryClient'
import axios from 'axios'

export const authApi = {
  login: (username, password) => {
    const form = new URLSearchParams()
    form.append('username', username)
    form.append('password', password)

    return axios.post('/api/v1/auth/login', form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
  },

  logout: (refreshToken) =>
    authClient.post('logout', { refresh_token: refreshToken }),

  me: () => authClient.get('me'),

  refresh: (refreshToken) =>
    axios.post('/api/v1/auth/refresh', {
      refresh_token: refreshToken,
    }),
}

export const usersApi = {
  list: (params) => authClient.get('users', { params }),
  create: (data) => authClient.post('users', data),
  update: (id, data) => authClient.patch(`users/${id}`, data),
  delete: (id) => authClient.delete(`users/${id}`),
}

export const switchesApi = {
  list: (params) => discoveryClient.get('/switches', { params }),
  get: (id) => discoveryClient.get(`/switches/${id}`),
  create: (data) => discoveryClient.post('/switches', data),
  update: (id, data) => discoveryClient.put(`/switches/${id}`, data),
  delete: (id) => discoveryClient.delete(`/switches/${id}`),
  getRpis: (id) => discoveryClient.get(`/switches/${id}/rpis`),
  getMacs: (id, params) =>
    discoveryClient.get(`/switches/${id}/macs`, { params }),
  reconnect: (id) => discoveryClient.post(`/switches/${id}/reconnect`),
  terminalOpen: (id) => discoveryClient.post(`/switches/${id}/terminal/open`),
  terminalList: (id) => discoveryClient.get(`/switches/${id}/terminal/sessions`),
  terminalClose: (sessionId) => discoveryClient.post(`/switches/terminal/${sessionId}/close`),
}

export const rpisApi = {
  list: (params) => discoveryClient.get('/rpis', { params }),
  get: (ip) => discoveryClient.get(`/rpis/${ip}`),
  getFacts: (ip, params) =>
    discoveryClient.get(`/rpis/${ip}/facts`, { params }),
  submitCredentials: (data) =>
    discoveryClient.post('/rpis/credentials', data),
  deleteCredentials: (ip) =>
    discoveryClient.delete(`/rpis/${ip}/credentials`),
  reconnect: (ip) => discoveryClient.post(`/rpis/${ip}/reconnect`),
  terminalOpen: (ip) => discoveryClient.post(`/rpis/${ip}/terminal/open`),
  terminalList: (ip) => discoveryClient.get(`/rpis/${ip}/terminal/sessions`),
  terminalClose: (sessionId) => discoveryClient.post(`/rpis/terminal/${sessionId}/close`),
  reboot: (ip) => discoveryClient.post(`/rpis/${ip}/reboot`),
}

export const hgwsApi = {
  list: (params) => discoveryClient.get('/hgws', { params }),
  get: (ip) => discoveryClient.get(`/hgws/${ip}`),
  getHistory: (ip, params) =>
    discoveryClient.get(`/hgws/${ip}/history`, { params }),
  reconnect: (ip, params) =>
    discoveryClient.post(`/hgws/${ip}/reconnect`, null, { params }),
  terminalOpen: (ip, params) => discoveryClient.post(`/hgws/${ip}/terminal/open`, null, { params }),
  terminalList: (ip) => discoveryClient.get(`/hgws/${ip}/terminal/sessions`),
  terminalClose: (sessionId) => discoveryClient.post(`/hgws/terminal/${sessionId}/close`),
}

export const discoveryApi = {
  trigger: () => discoveryClient.post('/discovery/run'),
  listRuns: (params) =>
    discoveryClient.get('/discovery/runs', { params }),
  getRun: (id) =>
    discoveryClient.get(`/discovery/runs/${id}`),
  deleteRun: (id) =>
    discoveryClient.delete(`/discovery/runs/${id}`),
  getRunErrors: (id, params) =>
    discoveryClient.get(`/discovery/runs/${id}/errors`, { params }),
  getStatus: () =>
    discoveryClient.get('/discovery/status'),
}

export const topologyApi = {
  // ── Existing ──────────────────────────────────────────────────────────
  getLatest: () =>
    discoveryClient.get('/topology'),

  getForRun: (runId) =>
    discoveryClient.get(`/topology/${runId}`),

  // ── Filter by switch (ADMIN / SUPER_ADMIN only) ───────────────────────
  getForSwitch: (runId, switchIp) =>
    discoveryClient.get(`/topology/${runId}/switch/${encodeURIComponent(switchIp)}`),

  // ── Filter by HGW identifier (serial_number or IP) ────────────────────
  getForHgw: (runId, hgwIdentifier) =>
    discoveryClient.get(`/topology/${runId}/hgw/${encodeURIComponent(hgwIdentifier)}`),

  // ── HGWs visible to the current user for a given run ─────────────────
  getMyHgws: (runId) =>
    discoveryClient.get(`/topology/${runId}/my-hgws`),
}

export const syncApi = {
  getStatus: () => discoveryClient.get('/sync/status'),
  trigger: () => discoveryClient.post('/sync/trigger'),
}