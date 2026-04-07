import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

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

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
