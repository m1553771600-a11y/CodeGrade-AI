import axios from 'axios'

const TOKEN_KEY = 'ce_token'

const http = axios.create({
  baseURL: '/api/v1',
  timeout: 180000, // 评审含 LLM 调用，超时放宽到 3 分钟
})

http.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response && err.response.status === 401) {
      localStorage.removeItem(TOKEN_KEY)
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(err)
  }
)

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}
export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

export async function register(username, password) {
  const { data } = await http.post('/auth/register', { username, password })
  return data
}
export async function login(username, password) {
  const { data } = await http.post('/auth/login', { username, password })
  return data
}

export async function submitReview(file, session_id, git_url = '') {
  const fd = new FormData()
  if (file) fd.append('file', file)
  if (git_url) fd.append('git_url', git_url)
  if (session_id) fd.append('session_id', session_id)
  const { data } = await http.post('/review/', fd)
  return data
}
export async function getReview(submissionId) {
  const { data } = await http.get(`/review/${submissionId}`)
  return data
}
export async function listReviews(limit = 20) {
  const { data } = await http.get('/review/', { params: { limit } })
  return data
}
export async function getProfile() {
  const { data } = await http.get('/profile/me')
  return data
}
