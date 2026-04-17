import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

const rootEl = document.getElementById('root')
if (rootEl) {
  rootEl.removeAttribute('data-boot-pending')
}

// Auto-reload when Vite lazy chunks fail to load after a new deploy (stale browser cache)
window.addEventListener('vite:preloadError', () => {
  window.location.reload()
})

const nativeFetch = window.fetch.bind(window)
window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  const response = await nativeFetch(input, {
    credentials: 'same-origin',
    ...init,
  })
  if (response.status === 401) {
    window.dispatchEvent(new CustomEvent('app:unauthorized'))
  }
  return response
}

ReactDOM.createRoot(rootEl!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
