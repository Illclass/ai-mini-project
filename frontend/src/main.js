import { createApp } from 'vue'
import App from './App.vue'
import { createAppRouter } from './router.js'
import { checkSession } from './api/index.js'
import './style.css'
import './clean-theme.css'
const router = createAppRouter({ checkSession })
const app = createApp(App).use(router)
router.isReady().then(() => app.mount('#app'))
