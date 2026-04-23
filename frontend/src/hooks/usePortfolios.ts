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

export function usePortfolios(enabled: boolean = true) {
  // Seed from cache immediately so UI doesn't flash empty on load
  const [portfolios, setPortfolios] = useState<Portfolio[]>(() => loadFromCache())
  const [loading, setLoading] = useState(true)
  const [needsRestore, setNeedsRestore] = useState(false)
  const pendingRestoreRef = useRef<Portfolio[]>([])

  const syncCache = (data: Portfolio[]) => {
    setPortfolios(data)
    saveToCache(data)
  }

  const fetchPortfolios = async () => {
    if (!enabled) {
      setPortfolios([])
      setLoading(false)
      return
    }
    try {
      const response = await fetch('/api/portfolios')
      const data = await response.json()
      if (Array.isArray(data)) {
        if (data.length === 0) {
          // Backend is empty — check if we have cached portfolios to restore
          const cached = loadFromCache()
          if (cached.length > 0) {
            pendingRestoreRef.current = cached
            setNeedsRestore(true)
          } else {
            syncCache([])
          }
        } else {
          syncCache(data)
          setNeedsRestore(false)
        }
      } else {
        // Fallback to cache on bad response
        const cached = loadFromCache()
        if (cached.length > 0) setPortfolios(cached)
      }
    } catch {
      // Network error — use cache silently
      const cached = loadFromCache()
      if (cached.length > 0) setPortfolios(cached)
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
  }

  const discardRestore = () => {
    pendingRestoreRef.current = []
    setNeedsRestore(false)
    clearCache()
    syncCache([])
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
    const newPortfolio = await response.json()
    const updated = [...portfolios, newPortfolio]
    syncCache(updated)
    return newPortfolio
  }

  const deletePortfolio = async (id: string) => {
    await fetch(`/api/portfolios/${id}`, { method: 'DELETE' })
    const updated = portfolios.filter(p => p.id !== id)
    syncCache(updated)
  }

  const addHolding = async (portfolioId: string, holding: Holding) => {
    await fetch(`/api/portfolios/${portfolioId}/holdings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ticker: holding.ticker,
        shares: holding.shares,
        buy_price: holding.buyPrice,
        purchase_date: holding.purchaseDate
      }),
    })
    await fetchPortfolios()
  }

  const removeHolding = async (portfolioId: string, ticker: string) => {
    await fetch(`/api/portfolios/${portfolioId}/holdings/${ticker}`, {
      method: 'DELETE'
    })
    await fetchPortfolios()
  }

  const updateHolding = async (portfolioId: string, ticker: string, patch: Partial<Holding>) => {
    await fetch(`/api/portfolios/${portfolioId}/holdings/${ticker}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        shares: patch.shares,
        buy_price: patch.buyPrice,
        purchase_date: patch.purchaseDate,
      }),
    })
    await fetchPortfolios()
  }

  return {
    portfolios,
    loading,
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
