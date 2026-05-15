import { useState, useEffect, useRef } from 'react'

export interface Holding {
  ticker: string
  shares: number
  buyPrice?: number
  purchaseDate?: string
}

export interface Portfolio {
  id: string
  name: string
  holdings: Holding[]
  createdAt: string
}

export type PortfolioDataSource = 'server' | 'local-cache' | 'empty' | 'disabled'

const CACHE_KEY = 'portfolios_local_cache'
const CACHE_VERSION = 2

function saveToCache(portfolios: Portfolio[]) {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify({ v: CACHE_VERSION, data: portfolios, ts: Date.now() }))
  } catch {
    // localStorage might be full or unavailable
  }
}

function loadFromCache(): Portfolio[] {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (parsed?.v === CACHE_VERSION && Array.isArray(parsed.data)) return parsed.data
  } catch { /* ignore */ }
  return []
}

function clearCache() {
  try { localStorage.removeItem(CACHE_KEY) } catch { /* ignore */ }
}

async function readApiError(response: Response, fallback: string): Promise<string> {
  try {
    const payload = await response.json()
    if (payload?.detail) return String(payload.detail)
  } catch {
    // ignore malformed error payload
  }
  return fallback
}

export function usePortfolios(enabled: boolean = true) {
  // Seed from cache immediately so UI doesn't flash empty on load
  const [portfolios, setPortfolios] = useState<Portfolio[]>(() => loadFromCache())
  const [loading, setLoading] = useState(true)
  const [needsRestore, setNeedsRestore] = useState(false)
  const [dataSource, setDataSource] = useState<PortfolioDataSource>('local-cache')
  const [dataSourceMessage, setDataSourceMessage] = useState('')
  const pendingRestoreRef = useRef<Portfolio[]>([])

  const syncCache = (data: Portfolio[]) => {
    setPortfolios(data)
    saveToCache(data)
  }

  const applyServerPortfolios = (data: Portfolio[]) => {
    setPortfolios(data)
    saveToCache(data)
    setNeedsRestore(false)
    setDataSource(data.length ? 'server' : 'empty')
    setDataSourceMessage('')
  }

  const fetchPortfolios = async () => {
    if (!enabled) {
      setPortfolios([])
      setDataSource('disabled')
      setDataSourceMessage('')
      setLoading(false)
      return
    }
    try {
      const response = await fetch('/api/portfolios')
      if (!response.ok) throw new Error(`Portfolio-Liste konnte nicht geladen werden (${response.status})`)
      const data = await response.json()
      if (Array.isArray(data)) {
        if (data.length === 0) {
          // Backend is empty — check if we have cached portfolios to restore
          const cached = loadFromCache()
          if (cached.length > 0) {
            pendingRestoreRef.current = cached
            setNeedsRestore(true)
            setDataSource('server')
            setDataSourceMessage('Server ist leer. Lokale Sicherung kann wiederhergestellt werden.')
          } else {
            syncCache([])
            setDataSource('empty')
            setDataSourceMessage('')
          }
        } else {
          applyServerPortfolios(data)
        }
      } else {
        // Fallback to cache on bad response
        const cached = loadFromCache()
        if (cached.length > 0) {
          setPortfolios(cached)
          setDataSource('local-cache')
          setDataSourceMessage('Portfolio-Daten kommen aus der lokalen Browser-Sicherung, weil die Serverantwort ungueltig war.')
        }
      }
    } catch {
      // Network error — use cache silently
      const cached = loadFromCache()
      if (cached.length > 0) {
        setPortfolios(cached)
        setDataSource('local-cache')
        setDataSourceMessage('Portfolio-Daten kommen aus der lokalen Browser-Sicherung, weil der Server nicht erreichbar war.')
      }
    } finally {
      setLoading(false)
    }
  }

  /** Re-create all portfolios from local cache on the backend */
  const restoreFromCache = async () => {
    const toRestore = pendingRestoreRef.current
    if (!toRestore.length) return
    setNeedsRestore(false)
    const restored: Portfolio[] = []
    for (const cached of toRestore) {
      try {
        const res = await fetch('/api/portfolios', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: cached.name }),
        })
        const newP: Portfolio = await res.json()
        // Re-add all holdings
        for (const h of cached.holdings) {
          await fetch(`/api/portfolios/${newP.id}/holdings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ticker: h.ticker, shares: h.shares, buy_price: h.buyPrice, purchase_date: h.purchaseDate }),
          })
        }
        restored.push({ ...newP, holdings: cached.holdings })
      } catch {
        // Keep cached version if restore fails
        restored.push(cached)
      }
    }
    syncCache(restored)
    setDataSource('server')
    setDataSourceMessage('Lokale Sicherung wurde an den Server uebertragen.')
  }

  const discardRestore = () => {
    pendingRestoreRef.current = []
    setNeedsRestore(false)
    clearCache()
    syncCache([])
    setDataSource('empty')
    setDataSourceMessage('')
  }

  useEffect(() => {
    fetchPortfolios()
  }, [enabled])

  const createPortfolio = async (name: string): Promise<Portfolio> => {
    const response = await fetch('/api/portfolios', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
    if (!response.ok) {
      throw new Error(await readApiError(response, `Portfolio konnte nicht gespeichert werden (${response.status})`))
    }
    const newPortfolio = await response.json()
    setPortfolios((current) => {
      const withoutDuplicate = current.filter((portfolio) => portfolio.id !== newPortfolio.id)
      const updated = [...withoutDuplicate, newPortfolio]
      saveToCache(updated)
      return updated
    })
    setNeedsRestore(false)
    setDataSource('server')
    setDataSourceMessage('')
    await fetchPortfolios()
    return newPortfolio
  }

  const deletePortfolio = async (id: string) => {
    const response = await fetch(`/api/portfolios/${id}`, { method: 'DELETE' })
    if (!response.ok) {
      throw new Error(await readApiError(response, `Portfolio konnte nicht geloescht werden (${response.status})`))
    }
    setPortfolios((current) => {
      const updated = current.filter(p => p.id !== id)
      saveToCache(updated)
      return updated
    })
    await fetchPortfolios()
  }

  const addHolding = async (portfolioId: string, holding: Holding) => {
    const response = await fetch(`/api/portfolios/${portfolioId}/holdings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ticker: holding.ticker,
        shares: holding.shares,
        buyPrice: holding.buyPrice,
        purchaseDate: holding.purchaseDate
      }),
    })
    if (!response.ok) {
      throw new Error(await readApiError(response, `Position konnte nicht gespeichert werden (${response.status})`))
    }
    await fetchPortfolios()
  }

  const removeHolding = async (portfolioId: string, ticker: string) => {
    const response = await fetch(`/api/portfolios/${portfolioId}/holdings/${ticker}`, {
      method: 'DELETE'
    })
    if (!response.ok) {
      throw new Error(await readApiError(response, `Position konnte nicht geloescht werden (${response.status})`))
    }
    await fetchPortfolios()
  }

  const updateHolding = async (portfolioId: string, ticker: string, patch: Partial<Holding>) => {
    const response = await fetch(`/api/portfolios/${portfolioId}/holdings/${ticker}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        shares: patch.shares,
        buyPrice: patch.buyPrice,
        purchaseDate: patch.purchaseDate,
      }),
    })
    if (!response.ok) {
      throw new Error(await readApiError(response, `Position konnte nicht aktualisiert werden (${response.status})`))
    }
    await fetchPortfolios()
  }

  return {
    portfolios,
    loading,
    dataSource,
    dataSourceMessage,
    needsRestore,
    cachedPortfolios: pendingRestoreRef.current,
    createPortfolio,
    deletePortfolio,
    addHolding,
    updateHolding,
    removeHolding,
    restoreFromCache,
    discardRestore,
    refresh: fetchPortfolios,
  }
}
