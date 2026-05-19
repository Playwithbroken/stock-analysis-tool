import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

const SW_RELOAD_GUARD_KEY = 'brokerfreund:sw-reload-once'

const rootEl = document.getElementById('root')
if (rootEl) {
  rootEl.removeAttribute('data-boot-pending')
}

const syncMobileViewportChrome = () => {
  const viewport = window.visualViewport
  const obstruction = viewport
    ? Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop)
    : 0
  document.documentElement.style.setProperty('--mobile-browser-bottom', `${Math.round(obstruction)}px`)
}

syncMobileViewportChrome()
window.visualViewport?.addEventListener('resize', syncMobileViewportChrome)
window.visualViewport?.addEventListener('scroll', syncMobileViewportChrome)
window.addEventListener('orientationchange', () => window.setTimeout(syncMobileViewportChrome, 250))

// Auto-reload when Vite lazy chunks fail to load after a new deploy (stale browser cache)
window.addEventListener('vite:preloadError', () => {
  window.location.reload()
})

if ('serviceWorker' in navigator) {
  const reloadOnce = () => {
    try {
      if (sessionStorage.getItem(SW_RELOAD_GUARD_KEY) === '1') return
      sessionStorage.setItem(SW_RELOAD_GUARD_KEY, '1')
    } catch {
      // Ignore sessionStorage restrictions; fallback to direct reload.
    }
    window.location.reload()
  }

  navigator.serviceWorker.addEventListener('controllerchange', reloadOnce)

  window.addEventListener('load', () => {
    navigator.serviceWorker
      .getRegistrations()
      .then((registrations) => {
        for (const reg of registrations) {
          reg.update().catch(() => {})

          if (reg.waiting) {
            reg.waiting.postMessage({ type: 'SKIP_WAITING' })
          }

          reg.addEventListener('updatefound', () => {
            const installing = reg.installing
            if (!installing) return
            installing.addEventListener('statechange', () => {
              if (installing.state === 'installed' && navigator.serviceWorker.controller) {
                reg.waiting?.postMessage({ type: 'SKIP_WAITING' })
              }
            })
          })
        }
      })
      .catch(() => {})
  })
}

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
