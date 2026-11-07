import { createApp } from 'vue'
import App from './App.vue'
import { loadModels } from './utils/models'
import './style.css'

async function prepareAuthenticatedModelRequests() {
  if (import.meta.env.DEV || window.location.protocol === 'he:') return
  const token = localStorage.getItem('he_manager_token') || ''
  if (!token) throw new Error('请先登录 HE Manager')
  const response = await fetch(`${import.meta.env.BASE_URL}models/session`, {
    method: 'POST', headers: { Authorization: `Bearer ${token}` }, credentials: 'same-origin',
  })
  if (!response.ok) throw new Error(`模型会话创建失败: HTTP ${response.status}`)
}

prepareAuthenticatedModelRequests()
  .then(() => loadModels())
  .catch((err) => console.error('Live2D 资源访问初始化失败', err))
  .finally(() => createApp(App).mount('#app'))
