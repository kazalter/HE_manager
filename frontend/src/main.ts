import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import router from './router'
import { initTheme } from './theme'
import { initDensity } from './density'
import { initAuth } from './auth'
import { initDesktop } from './desktop'

initTheme()
initDensity()
initDesktop().then(initAuth).finally(() => {
  const app = createApp(App)
  app.use(router)
  app.mount('#app')
})
