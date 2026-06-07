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

interface FetchPortfolioOptions {
  preserveLocalOnEmpty?: boolean
}

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

async function delay(ms: number) {
  await new Promise((resolve) => window.setTimeout(resolve, ms))
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

  const fetchPortfolios = async (options: FetchPortfolioOptions = {}): Promise<Portfolio[] | null> => {
    if (!enabled) {
      setPortfolios([])
      setDataSource('disabled')
      setDataSourceMessage('')
      setLoading(false)
      return []
    }
    try {
      const response = await fetch('/api/portfolios', { credentials: 'same-origin' })
      if (!response.ok) throw new Error(`Portfolio-Liste konnte nicht geladen werden (${response.status})`)
      const data = await response.json()
      if (Array.isArray(data)) {
        if (data.length === 0) {
          // Backend is empty — check if we have cached portfolios to restore
          const cached = loadFromCache()
          if (options.preserveLocalOnEmpty && cached.length > 0) {
            setPortfolios(cached)
            setDataSource('server')
            setDataSourceMessage('Server hat die Aenderung bestaetigt; Listen-Sync laeuft noch.')
            return cached
          }
          if (cached.length > 0) {
            pendingRestoreRef.current = cached
            setNeedsRestore(true)
            setDataSource('server')
            setDataSourceMessage('Server ist leer. Lokale Sicherung kann wiederhergestellt werden.')
            return cached
          } else {
            syncCache([])
            setDataSource('empty')
            setDataSourceMessage('')
            return []
          }
        } else {
          applyServerPortfolios(data)
          return data
        }
      } else {
        // Fallback to cache on bad response
        const cached = loadFromCache()
        if (cached.length > 0) {
          setPortfolios(cached)
          setDataSource('local-cache')
          setDataSourceMessage('Portfolio-Daten kommen aus der lokalen Browser-Sicherung, weil die Serverantwort ungueltig war.')
          return cached
        }
      }
    } catch {
      // Network error — use cache silently
      const cached = loadFromCache()
      if (cached.length > 0) {
        setPortfolios(cached)
        setDataSource('local-cache')
        setDataSourceMessage('Portfolio-Daten kommen aus der lokalen Browser-Sicherung, weil der Server nicht erreichbar war.')
        return cached
      }
    } finally {
      setLoading(false)
    }
    return null
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
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: cached.name }),
        })
        const newP: Portfolio = await res.json()
        // Re-add all holdings
        for (const h of cached.holdings) {
          await fetch(`/api/portfolios/${newP.id}/holdings`, {
            method: 'POST',
            credentials: 'same-origin',
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
    const cleanName = name.trim()
    if (!cleanName) {
      throw new Error('Portfolio-Name ist erforderlich.')
    }
    const response = await fetch('/api/portfolios', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: cleanName }),
    })
    if (!response.ok) {
      throw new Error(await readApiError(response, `Portfolio konnte nicht gespeichert werden (${response.status})`))
    }
    const newPortfolio = await response.json()
    if (!newPortfolio?.id) {
      throw new Error('Portfolio wurde vom Server nicht bestaetigt.')
    }
    const confirmedPortfolio: Portfolio = {
      id: String(newPortfolio.id),
      name: String(newPortfolio.name || cleanName),
      holdings: Array.isArray(newPortfolio.holdings) ? newPortfolio.holdings : [],
      createdAt: String(newPortfolio.createdAt || new Date().toISOString()),
    }
    setPortfolios((current) => {
      const withoutDuplicate = current.filter((portfolio) => portfolio.id !== confirmedPortfolio.id)
      const updated = [confirmedPortfolio, ...withoutDuplicate]
      saveToCache(updated)
      return updated
    })
    setNeedsRestore(false)
    setDataSource('server')
    setDataSourceMessage('Portfolio wurde angelegt. Server-Bestaetigung laeuft.')
    let refreshed: Portfolio[] | null = null
    for (let attempt = 0; attempt < 3; attempt += 1) {
      if (attempt > 0) await delay(350 * attempt)
      refreshed = await fetchPortfolios({ preserveLocalOnEmpty: true })
      if (refreshed?.some((portfolio) => portfolio.id === confirmedPortfolio.id)) {
        setDataSource('server')
        setDataSourceMessage('Portfolio wurde serverseitig gespeichert und verifiziert.')
        return confirmedPortfolio
      }
    }
    if (refreshed && !refreshed.some((portfolio) => portfolio.id === confirmedPortfolio.id)) {
      setPortfolios((current) => {
        const updated = [confirmedPortfolio, ...current.filter((portfolio) => portfolio.id !== confirmedPortfolio.id)]
        saveToCache(updated)
        return updated
      })
      setDataSource('server')
      setDataSourceMessage('Portfolio ist angelegt, aber die Serverliste hat es noch nicht zurueckgemeldet. Bitte einmal Refresh pruefen.')
    }
    return confirmedPortfolio
  }

  const deletePortfolio = async (id: string) => {
    const response = await fetch(`/api/portfolios/${id}`, { method: 'DELETE', credentials: 'same-origin' })
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
    const normalizedHolding: Holding = {
      ticker: String(holding.ticker || '').trim().toUpperCase().replace(/\s+/g, ''),
      shares: Number(holding.shares),
      buyPrice: holding.buyPrice,
      purchaseDate: holding.purchaseDate,
    }
    const response = await fetch(`/api/portfolios/${portfolioId}/holdings`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ticker: normalizedHolding.ticker,
        shares: normalizedHolding.shares,
        buyPrice: normalizedHolding.buyPrice,
        buy_price: normalizedHolding.buyPrice,
        purchaseDate: normalizedHolding.purchaseDate,
        purchase_date: normalizedHolding.purchaseDate,
      }),
    })
    if (!response.ok) {
      throw new Error(await readApiError(response, `Position konnte nicht gespeichert werden (${response.status})`))
    }
    setPortfolios((current) => {
      const updated = current.map((portfolio) => {
        if (portfolio.id !== portfolioId) return portfolio
        const existing = portfolio.holdings.find((item) => item.ticker === normalizedHolding.ticker)
        const holdings = existing
          ? portfolio.holdings.map((item) =>
              item.ticker === normalizedHolding.ticker
                ? {
                    ...item,
                    shares: Number(item.shares || 0) + normalizedHolding.shares,
                    buyPrice: normalizedHolding.buyPrice ?? item.buyPrice,
                    purchaseDate: normalizedHolding.purchaseDate ?? item.purchaseDate,
                  }
                : item,
            )
          : [...portfolio.holdings, normalizedHolding]
        return { ...portfolio, holdings }
      })
      saveToCache(updated)
      return updated
    })
    setDataSource('server')
    setDataSourceMessage('Position wurde gespeichert. Serverliste wird abgeglichen.')
    await fetchPortfolios({ preserveLocalOnEmpty: true })
  }

  const removeHolding = async (portfolioId: string, ticker: string) => {
    const response = await fetch(`/api/portfolios/${portfolioId}/holdings/${ticker}`, {
      method: 'DELETE',
      credentials: 'same-origin',
    })
    if (!response.ok) {
      throw new Error(await readApiError(response, `Position konnte nicht geloescht werden (${response.status})`))
    }
    await fetchPortfolios()
  }

  const updateHolding = async (portfolioId: string, ticker: string, patch: Partial<Holding>) => {
    const response = await fetch(`/api/portfolios/${portfolioId}/holdings/${ticker}`, {
      method: 'PATCH',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        shares: patch.shares,
        buyPrice: patch.buyPrice,
        buy_price: patch.buyPrice,
        purchaseDate: patch.purchaseDate,
        purchase_date: patch.purchaseDate,
      }),
    })
    if (!response.ok) {
      throw new Error(await readApiError(response, `Position konnte nicht aktualisiert werden (${response.status})`))
    }
    const updatedHolding = await response.json().catch(() => null)
    setPortfolios((current) => {
      const updated = current.map((portfolio) => {
        if (portfolio.id !== portfolioId) return portfolio
        return {
          ...portfolio,
          holdings: portfolio.holdings.map((holding) =>
            holding.ticker === ticker
              ? {
                  ...holding,
                  ...(updatedHolding || {}),
                  shares: patch.shares ?? updatedHolding?.shares ?? holding.shares,
                  buyPrice: patch.buyPrice ?? updatedHolding?.buyPrice ?? holding.buyPrice,
                  purchaseDate: patch.purchaseDate ?? updatedHolding?.purchaseDate ?? holding.purchaseDate,
                }
              : holding,
          ),
        }
      })
      saveToCache(updated)
      return updated
    })
    setDataSource('server')
    setDataSourceMessage('Position wurde aktualisiert. Serverliste wird abgeglichen.')
    await fetchPortfolios({ preserveLocalOnEmpty: true })
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
