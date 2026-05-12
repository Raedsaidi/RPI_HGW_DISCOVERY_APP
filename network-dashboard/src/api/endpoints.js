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

  logout: (refreshToken) => authClient.post('logout', { refresh_token: refreshToken }),

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
  getMacs: (id, params) => discoveryClient.get(`/switches/${id}/macs`, { params }),
  reconnect: (id) => discoveryClient.post(`/switches/${id}/reconnect`),

  terminalOpen: (id) => discoveryClient.post(`/switches/${id}/terminal/open`),
  terminalList: (id) => discoveryClient.get(`/switches/${id}/terminal/sessions`),
  terminalClose: (sessionId) => discoveryClient.post(`/switches/terminal/${sessionId}/close`),
}

export const rpisApi = {
  list: (params) => discoveryClient.get('/rpis', { params }),
  get: (ip) => discoveryClient.get(`/rpis/${ip}`),
  getFacts: (ip, params) => discoveryClient.get(`/rpis/${ip}/facts`, { params }),
  submitCredentials: (data) => discoveryClient.post('/rpis/credentials', data),
  deleteCredentials: (ip) => discoveryClient.delete(`/rpis/${ip}/credentials`),
  reconnect: (ip) => discoveryClient.post(`/rpis/${ip}/reconnect`),

  terminalOpen: (ip) => discoveryClient.post(`/rpis/${ip}/terminal/open`),
  terminalList: (ip) => discoveryClient.get(`/rpis/${ip}/terminal/sessions`),
  terminalClose: (sessionId) => discoveryClient.post(`/rpis/terminal/${sessionId}/close`),

  // ✅ NEW: all RPi terminal sessions for current user
  terminalSessionsAll: () => discoveryClient.get('/rpis/terminal/sessions'),

  reboot: (ip) => discoveryClient.post(`/rpis/${ip}/reboot`),
}

export const hgwsApi = {
  list: (params) => discoveryClient.get('/hgws', { params }),
  get: (ip) => discoveryClient.get(`/hgws/${ip}`),
  getHistory: (ip, params) => discoveryClient.get(`/hgws/${ip}/history`, { params }),
  reconnect: (ip, params) => discoveryClient.post(`/hgws/${ip}/reconnect`, null, { params }),

  // ✅ FIX: HGW terminal by unique ID (prevents collisions when IP duplicates)
  terminalOpenById: (hgwId, params) => discoveryClient.post(`/hgws/${hgwId}/terminal/open`, null, { params }),
  terminalListById: (hgwId) => discoveryClient.get(`/hgws/${hgwId}/terminal/sessions`),
  terminalClose: (sessionId) => discoveryClient.post(`/hgws/terminal/${sessionId}/close`),
}

export const discoveryApi = {
  trigger: () => discoveryClient.post('/discovery/run'),
  listRuns: (params) => discoveryClient.get('/discovery/runs', { params }),
  getRun: (id) => discoveryClient.get(`/discovery/runs/${id}`),
  deleteRun: (id) => discoveryClient.delete(`/discovery/runs/${id}`),
  getRunErrors: (id, params) => discoveryClient.get(`/discovery/runs/${id}/errors`, { params }),
  getStatus: () => discoveryClient.get('/discovery/status'),
  miniHgwUpdate: (runId, data) => discoveryClient.post(`/discovery/runs/${runId}/mini/hgw`, data),
}

export const topologyApi = {
  getLatest: () => discoveryClient.get('/topology'),
  getForRun: (runId) => discoveryClient.get(`/topology/${runId}`),
  getForSwitch: (runId, switchIp) =>
    discoveryClient.get(`/topology/${runId}/switch/${encodeURIComponent(switchIp)}`),
  getForHgw: (runId, hgwIdentifier) =>
    discoveryClient.get(`/topology/${runId}/hgw/${encodeURIComponent(hgwIdentifier)}`),
  getMyHgws: (runId) => discoveryClient.get(`/topology/${runId}/my-hgws`),
}

export const syncApi = {
  getStatus: () => discoveryClient.get('/sync/status'),
  trigger: () => discoveryClient.post('/sync/trigger'),
}