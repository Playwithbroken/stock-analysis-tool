import { useState, useEffect } from 'react'

export interface Holding {
  ticker: string
  shares: number
  buyPrice?: number
}

export interface Portfolio {
  id: string
  name: string
  holdings: Holding[]
  createdAt: string
}

export function usePortfolios() {
  const [portfolios, setPortfolios] = useState<Portfolio[]>([])
  const [loading, setLoading] = useState(true)

  const fetchPortfolios = async () => {
    try {
      const response = await fetch('/api/portfolios')
      const data = await response.json()
      if (Array.isArray(data)) {
        setPortfolios(data)
      } else {
        console.error('Expected array of portfolios, got:', data)
        setPortfolios([])
      }
    } catch (err) {
      console.error('Failed to fetch portfolios:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchPortfolios()
  }, [])

  const createPortfolio = async (name: string): Promise<Portfolio> => {
    const response = await fetch('/api/portfolios', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
    const newPortfolio = await response.json()
    setPortfolios(prev => [...prev, newPortfolio])
    return newPortfolio
  }

  const deletePortfolio = async (id: string) => {
    await fetch(`/api/portfolios/${id}`, { method: 'DELETE' })
    setPortfolios(prev => prev.filter(p => p.id !== id))
  }

  const addHolding = async (portfolioId: string, holding: Holding) => {
    await fetch(`/api/portfolios/${portfolioId}/holdings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ticker: holding.ticker,
        shares: holding.shares,
        buy_price: holding.buyPrice
      }),
    })
    await fetchPortfolios() // Refresh to get merged/updated state
  }

  const removeHolding = async (portfolioId: string, ticker: string) => {
    await fetch(`/api/portfolios/${portfolioId}/holdings/${ticker}`, {
      method: 'DELETE'
    })
    await fetchPortfolios()
  }

  return {
    portfolios,
    loading,
    createPortfolio,
    deletePortfolio,
    addHolding,
    removeHolding,
    refresh: fetchPortfolios
  }
}
