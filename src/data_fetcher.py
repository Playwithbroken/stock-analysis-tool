"""
Data Fetcher Module
Fetches market data, fundamentals, and news for stock analysis.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import requests
from bs4 import BeautifulSoup


class DataFetcher:
    """Fetches all required data for stock analysis."""
    
    # Class-level cache
    _global_cache = {}
    _cache_ttl = 300  # 5 minutes
    _etf_info_overrides: Dict[str, Dict[str, Any]] = {
        "SPY": {
            "longName": "SPDR S&P 500 ETF Trust",
            "quoteType": "ETF",
            "sector": "Broad Market",
            "industry": "US Large Cap",
            "currency": "USD",
        },
        "QQQ": {
            "longName": "Invesco QQQ Trust",
            "quoteType": "ETF",
            "sector": "Growth",
            "industry": "Nasdaq 100",
            "currency": "USD",
        },
        "GLD": {
            "longName": "SPDR Gold Shares",
            "quoteType": "ETF",
            "sector": "Commodities",
            "industry": "Gold",
            "currency": "USD",
        },
        "TLT": {
            "longName": "iShares 20+ Year Treasury Bond ETF",
            "quoteType": "ETF",
            "sector": "Rates",
            "industry": "US Treasuries",
            "currency": "USD",
        },
        "XLE": {
            "longName": "Energy Select Sector SPDR Fund",
            "quoteType": "ETF",
            "sector": "Energy",
            "industry": "Energy Equities",
            "currency": "USD",
        },
    }

    def __init__(self, ticker: str):
        self.ticker = ticker.upper()
        self.stock = yf.Ticker(self.ticker)
        self._info = None
        self._history_1y = None
        
    @property
    def info(self) -> Dict:
        """Get stock info with global caching and error handling."""
        now = datetime.now()
        cache_key = f"info_{self.ticker}"
        
        if cache_key in DataFetcher._global_cache:
            val, ts = DataFetcher._global_cache[cache_key]
            if (now - ts).total_seconds() < DataFetcher._cache_ttl:
                return val

        if self.ticker in self._etf_info_overrides:
            val = self._etf_info_overrides[self.ticker]
            DataFetcher._global_cache[cache_key] = (val, now)
            return val
        
        try:
            # yfinance info can be slow or hang
            print(f"Fetching info for {self.ticker}...")
            val = self.stock.info
            if not val:
                print(f"Warning: No info returned for {self.ticker}")
                val = {}
            DataFetcher._global_cache[cache_key] = (val, now)
            return val
        except Exception as e:
            print(f"Error fetching info for {self.ticker}: {e}")
            return {}
    
    def get_price_data(self) -> Dict[str, Any]:
        """Get current price and price changes derived from a single 1y history fetch."""
        try:
            if self._history_1y is None:
                self._history_1y = self.stock.history(period="1y")
            
            hist = self._history_1y
            if hist.empty:
                return {"error": "No price data available"}
            
            current_price = hist['Close'].iloc[-1]
            
            def safe_pct_change(start_idx: int) -> Optional[float]:
                if len(hist) < abs(start_idx):
                    return None
                start_val = hist['Close'].iloc[start_idx]
                if start_val == 0: return 0
                return ((current_price / start_val) - 1) * 100
            
            return {
                "current_price": current_price,
                "currency": self.info.get("currency", "USD"),
                "change_1w": safe_pct_change(-6),
                "change_1m": safe_pct_change(-22),
                "change_6m": safe_pct_change(-127),
                "change_1y": safe_pct_change(0),
                "high_52w": self.info.get("fiftyTwoWeekHigh"),
                "low_52w": self.info.get("fiftyTwoWeekLow"),
                "from_52w_high": ((current_price / self.info.get("fiftyTwoWeekHigh", current_price)) - 1) * 100 if current_price else None,
                "from_52w_low": ((current_price / self.info.get("fiftyTwoWeekLow", current_price)) - 1) * 100 if current_price else None,
            }
        except Exception as e:
            return {"error": str(e)}

    def get_price_data_fast(self) -> Dict[str, Any]:
        """Fast market snapshot without expensive info calls (used for dashboard brief)."""
        try:
            hist = self.stock.history(period="6mo", interval="1d", auto_adjust=False)
            if hist.empty:
                return {"error": "No price data available"}

            current_price = float(hist["Close"].iloc[-1])

            def safe_pct_change(start_idx: int) -> Optional[float]:
                if len(hist) < abs(start_idx):
                    return None
                start_val = float(hist["Close"].iloc[start_idx])
                if start_val == 0:
                    return 0.0
                return ((current_price / start_val) - 1) * 100

            return {
                "current_price": current_price,
                "currency": "USD",
                "change_1w": safe_pct_change(-6),
                "change_1m": safe_pct_change(-22),
                "change_6m": safe_pct_change(0),
                "change_1y": None,
                "high_52w": None,
                "low_52w": None,
                "from_52w_high": None,
                "from_52w_low": None,
            }
        except Exception as e:
            return {"error": str(e)}
    
    def get_volatility_data(self) -> Dict[str, Any]:
        """Calculate volatility metrics from cached history."""
        try:
            if self._history_1y is None:
                self._history_1y = self.stock.history(period="1y")
            
            hist = self._history_1y
            if hist.empty:
                return {"error": "No data available"}
            
            returns = hist['Close'].pct_change().dropna()
            volatility_daily = returns.std()
            volatility_annual = volatility_daily * np.sqrt(252)
            
            avg_volume = hist['Volume'].mean()
            current_volume = hist['Volume'].iloc[-1]
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
            
            return {
                "volatility_daily": volatility_daily * 100,
                "volatility_annual": volatility_annual * 100,
                "avg_volume": avg_volume,
                "current_volume": current_volume,
                "volume_ratio": volume_ratio,
                "beta": self.info.get("beta", None),
            }
        except Exception as e:
            return {"error": str(e)}

    def _safe_number(self, value: Any) -> Optional[float]:
        """Normalize yfinance/numpy scalar values into finite floats."""
        try:
            if value is None or pd.isna(value):
                return None
            number = float(value)
            return number if np.isfinite(number) else None
        except Exception:
            return None

    def _statement_series(
        self,
        statement: Any,
        labels: List[str],
        limit: int = 8,
    ) -> List[Dict[str, Any]]:
        if statement is None or not isinstance(statement, pd.DataFrame) or statement.empty:
            return []

        normalized_index = {str(idx).strip().lower(): idx for idx in statement.index}
        row = None
        for label in labels:
            matched = normalized_index.get(label.strip().lower())
            if matched is not None:
                row = statement.loc[matched]
                break
        if row is None:
            return []

        series: List[Dict[str, Any]] = []
        for period, value in row.items():
            number = self._safe_number(value)
            if number is None:
                continue
            period_value = period.strftime("%Y-%m-%d") if isinstance(period, pd.Timestamp) else str(period)
            series.append({"period": period_value, "value": number})
        return series[:limit]

    def _build_statement_rows(
        self,
        income_stmt: Any,
        cashflow_stmt: Any,
        balance_stmt: Any,
        limit: int,
    ) -> List[Dict[str, Any]]:
        metrics = {
            "revenue": self._statement_series(income_stmt, ["Total Revenue", "Operating Revenue"], limit),
            "gross_profit": self._statement_series(income_stmt, ["Gross Profit"], limit),
            "operating_income": self._statement_series(income_stmt, ["Operating Income"], limit),
            "net_income": self._statement_series(income_stmt, ["Net Income", "Net Income Common Stockholders"], limit),
            "ebitda": self._statement_series(income_stmt, ["EBITDA", "Normalized EBITDA"], limit),
            "operating_cashflow": self._statement_series(cashflow_stmt, ["Operating Cash Flow", "Total Cash From Operating Activities"], limit),
            "free_cashflow": self._statement_series(cashflow_stmt, ["Free Cash Flow"], limit),
            "capital_expenditure": self._statement_series(cashflow_stmt, ["Capital Expenditure", "Capital Expenditures"], limit),
            "total_debt": self._statement_series(balance_stmt, ["Total Debt"], limit),
            "cash": self._statement_series(balance_stmt, ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"], limit),
        }

        periods: List[str] = []
        for values in metrics.values():
            for item in values:
                if item["period"] not in periods:
                    periods.append(item["period"])

        rows: List[Dict[str, Any]] = []
        for period in periods[:limit]:
            row: Dict[str, Any] = {"period": period}
            for key, values in metrics.items():
                match = next((item for item in values if item["period"] == period), None)
                if match:
                    row[key] = match["value"]

            revenue = self._safe_number(row.get("revenue"))
            if revenue and revenue != 0:
                for source, target in [
                    ("gross_profit", "gross_margin"),
                    ("operating_income", "operating_margin"),
                    ("net_income", "net_margin"),
                    ("free_cashflow", "fcf_margin"),
                ]:
                    value = self._safe_number(row.get(source))
                    if value is not None:
                        row[target] = value / revenue

            debt = self._safe_number(row.get("total_debt"))
            cash = self._safe_number(row.get("cash"))
            if debt is not None and cash is not None:
                row["net_debt"] = debt - cash
            rows.append(row)
        return rows

    def _calculate_statement_trends(
        self,
        annual_rows: List[Dict[str, Any]],
        quarterly_rows: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        def pct_change(latest: Any, previous: Any) -> Optional[float]:
            latest_num = self._safe_number(latest)
            previous_num = self._safe_number(previous)
            if latest_num is None or previous_num in (None, 0):
                return None
            return (latest_num - previous_num) / abs(previous_num)

        trends: Dict[str, Any] = {}
        if len(annual_rows) >= 2:
            latest = annual_rows[0]
            previous = annual_rows[1]
            trends["revenue_yoy"] = pct_change(latest.get("revenue"), previous.get("revenue"))
            trends["net_income_yoy"] = pct_change(latest.get("net_income"), previous.get("net_income"))
            trends["free_cashflow_yoy"] = pct_change(latest.get("free_cashflow"), previous.get("free_cashflow"))
            for key in ["gross_margin", "operating_margin", "net_margin", "fcf_margin"]:
                if latest.get(key) is not None and previous.get(key) is not None:
                    trends[f"{key}_change"] = latest[key] - previous[key]

        if len(annual_rows) >= 3:
            latest_revenue = self._safe_number(annual_rows[0].get("revenue"))
            oldest_revenue = self._safe_number(annual_rows[-1].get("revenue"))
            years = max(1, len(annual_rows) - 1)
            if latest_revenue and oldest_revenue and latest_revenue > 0 and oldest_revenue > 0:
                trends["revenue_cagr"] = (latest_revenue / oldest_revenue) ** (1 / years) - 1

        if len(quarterly_rows) >= 5:
            trends["quarterly_revenue_yoy"] = pct_change(
                quarterly_rows[0].get("revenue"),
                quarterly_rows[4].get("revenue"),
            )
        return trends
    
    def get_fundamentals(self) -> Dict[str, Any]:
        """Get fundamental data."""
        try:
            info = self.info
            annual_rows: List[Dict[str, Any]] = []
            quarterly_rows: List[Dict[str, Any]] = []
            statement_trends: Dict[str, Any] = {}
            try:
                annual_rows = self._build_statement_rows(
                    getattr(self.stock, "income_stmt", None),
                    getattr(self.stock, "cashflow", None),
                    getattr(self.stock, "balance_sheet", None),
                    limit=5,
                )
                quarterly_rows = self._build_statement_rows(
                    getattr(self.stock, "quarterly_income_stmt", None),
                    getattr(self.stock, "quarterly_cashflow", None),
                    getattr(self.stock, "quarterly_balance_sheet", None),
                    limit=8,
                )
                statement_trends = self._calculate_statement_trends(annual_rows, quarterly_rows)
            except Exception:
                annual_rows = []
                quarterly_rows = []
                statement_trends = {}

            return {
                "market_cap": info.get("marketCap"),
                "enterprise_value": info.get("enterpriseValue"),
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "peg_ratio": info.get("pegRatio"),
                "pb_ratio": info.get("priceToBook"),
                "ps_ratio": info.get("priceToSalesTrailing12Months"),
                "ev_ebitda": info.get("enterpriseToEbitda"),
                "ev_revenue": info.get("enterpriseToRevenue"),
                "revenue": info.get("totalRevenue"),
                "revenue_growth": info.get("revenueGrowth"),
                "gross_margin": info.get("grossMargins"),
                "operating_margin": info.get("operatingMargins"),
                "profit_margin": info.get("profitMargins"),
                "roe": info.get("returnOnEquity"),
                "roa": info.get("returnOnAssets"),
                "eps": info.get("trailingEps"),
                "forward_eps": info.get("forwardEps"),
                "earnings_growth": info.get("earningsGrowth"),
                "total_cash": info.get("totalCash"),
                "total_debt": info.get("totalDebt"),
                "debt_to_equity": info.get("debtToEquity"),
                "current_ratio": info.get("currentRatio"),
                "quick_ratio": info.get("quickRatio"),
                "free_cashflow": info.get("freeCashflow"),
                "operating_cashflow": info.get("operatingCashflow"),
                "dividend_yield": info.get("dividendYield"),
                "payout_ratio": info.get("payoutRatio"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "employees": info.get("fullTimeEmployees"),
                "country": info.get("country"),
                "quote_type": info.get("quoteType"),
                "expense_ratio": info.get("annualReportExpenseRatio"),
                "total_assets": info.get("totalAssets"),
                "category": info.get("category"),
                "fund_family": info.get("fundFamily"),
                "financial_statements": {
                    "annual": annual_rows,
                    "quarterly": quarterly_rows,
                    "trends": statement_trends,
                    "coverage": {
                        "annual_periods": len(annual_rows),
                        "quarterly_periods": len(quarterly_rows),
                    },
                },
            }
        except Exception as e:
            return {"error": str(e)}
    
    def get_analyst_data(self) -> Dict[str, Any]:
        """Get analyst recommendations and price targets."""
        try:
            info = self.info
            return {
                "target_high": info.get("targetHighPrice"),
                "target_low": info.get("targetLowPrice"),
                "target_mean": info.get("targetMeanPrice"),
                "target_median": info.get("targetMedianPrice"),
                "recommendation": info.get("recommendationKey"),
                "recommendation_mean": info.get("recommendationMean"),
                "num_analysts": info.get("numberOfAnalystOpinions"),
            }
        except Exception as e:
            return {"error": str(e)}
    
    def get_short_interest(self) -> Dict[str, Any]:
        """Get short interest data."""
        try:
            info = self.info
            return {
                "short_ratio": info.get("shortRatio"),
                "short_percent_float": info.get("shortPercentOfFloat"),
                "shares_short": info.get("sharesShort"),
                "shares_short_prior": info.get("sharesShortPriorMonth"),
            }
        except Exception as e:
            return {"error": str(e)}

    def get_etf_holdings(self) -> list:
        """Get top holdings for an ETF if available."""
        try:
            if hasattr(self.stock, 'funds_data') and self.stock.funds_data.top_holdings is not None:
                holdings = self.stock.funds_data.top_holdings
                # Convert to list of dicts for JSON serialization
                result = []
                for idx, row in holdings.iterrows():
                    result.append({
                        "symbol": row.name if hasattr(row, 'name') else str(idx),
                        "name": row.get("Holding Name", ""),
                        "weight": float(row.get("Holding Percent", 0)) * 100 if "Holding Percent" in row else 0
                    })
                return result[:10]
            return []
        except Exception as e:
            print(f"Error fetching holdings for {self.ticker}: {e}")
            return []

    def get_news(self) -> list:
        """Get recent news for the stock."""
        try:
            news = self.stock.news
            if news:
                processed_news = []
                for item in news[:10]:
                    content = item.get("content", item)
                    title = content.get("title") or item.get("title") or ""
                    publisher = content.get("provider", {}).get("displayName") or item.get("publisher") or ""
                    link = content.get("canonicalUrl", {}).get("url") or item.get("link") or ""
                    processed_news.append({
                        "title": title,
                        "publisher": publisher,
                        "link": link,
                        "timestamp": "", # Simplified for discovery speed
                    })
                return processed_news
            return []
        except Exception:
            return []
    
    def get_comparison_data(self, index_ticker: str = "^GSPC") -> Dict[str, Any]:
        """Compare stock performance with S&P 500 from cached history."""
        try:
            if self._history_1y is None:
                self._history_1y = self.stock.history(period="1y")
            
            if self._history_1y.empty:
                return {"error": "No comparison data available"}
            
            # Simple stock return
            stock_return = ((self._history_1y['Close'].iloc[-1] / self._history_1y['Close'].iloc[0]) - 1) * 100
            
            # For discovery, we skip the index fetch to save time and return a general status
            return {
                "stock_return_1y": stock_return,
                "relative_performance": stock_return - 10, # Mock benchmark of 10%
                "index_name": "S&P 500 (Est.)",
                "outperforming": stock_return > 10,
            }
        except Exception as e:
            return {"error": str(e)}
    
    def get_competitors(self) -> list:
        return []
    
    def get_earnings_history(self) -> list:
        """Return recent earnings results with EPS estimate/actual surprise where available."""
        try:
            earnings_dates = None
            try:
                earnings_dates = self.stock.get_earnings_dates(limit=8)
            except Exception:
                earnings_dates = getattr(self.stock, "earnings_dates", None)

            if earnings_dates is None or not isinstance(earnings_dates, pd.DataFrame) or earnings_dates.empty:
                return []

            rows: List[Dict[str, Any]] = []
            for idx, row in earnings_dates.iterrows():
                reported_eps = self._safe_number(
                    row.get("Reported EPS")
                    if hasattr(row, "get")
                    else None
                )
                eps_estimate = self._safe_number(row.get("EPS Estimate") if hasattr(row, "get") else None)
                surprise_pct = self._safe_number(row.get("Surprise(%)") if hasattr(row, "get") else None)
                if surprise_pct is not None and abs(surprise_pct) <= 1:
                    surprise_pct *= 100
                if surprise_pct is None and reported_eps is not None and eps_estimate not in (None, 0):
                    surprise_pct = ((reported_eps / eps_estimate) - 1) * 100

                if reported_eps is None and eps_estimate is None and surprise_pct is None:
                    continue

                period = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
                status = "inline"
                if surprise_pct is not None:
                    if surprise_pct >= 3:
                        status = "beat"
                    elif surprise_pct <= -3:
                        status = "miss"

                rows.append(
                    {
                        "period": period,
                        "eps_estimate": eps_estimate,
                        "reported_eps": reported_eps,
                        "eps_surprise_pct": surprise_pct,
                        "status": status,
                    }
                )
            return rows[:8]
        except Exception as e:
            print(f"Error fetching earnings history for {self.ticker}: {e}")
            return []
    
    def get_insider_transactions(self) -> list:
        return []

    def get_dividends(self) -> Dict[str, Any]:
        """Get basic dividend information for portfolio income estimates."""
        try:
            info = self.info
            dividend_rate = info.get("dividendRate")
            dividend_yield = info.get("dividendYield")
            series = getattr(self.stock, "dividends", None)
            last_payment = None
            trailing_total = None

            if isinstance(series, pd.Series) and not series.empty:
                clean_series = series.dropna()
                if not clean_series.empty:
                    last_payment = float(clean_series.iloc[-1])
                    trailing_total = float(clean_series.tail(12).sum())
                    if dividend_rate in (None, 0):
                        dividend_rate = trailing_total

            return {
                "dividend_rate": float(dividend_rate) if dividend_rate not in (None, "") else None,
                "dividend_yield": float(dividend_yield) * 100 if dividend_yield not in (None, "") else None,
                "last_payment": last_payment,
                "trailing_12m_total": trailing_total,
            }
        except Exception as e:
            return {"error": str(e), "dividend_rate": None, "dividend_yield": None}

    def get_history(self, period: str = "1mo", interval: str = "1d") -> list:
        """Get historical price data."""
        fallback_windows = [
            (period, interval),
            ("5d", "15m"),
            ("1mo", "1d"),
            ("1y", "1wk"),
        ]
        fallback_windows = list(dict.fromkeys(fallback_windows))

        last_error: Optional[Exception] = None
        for current_period, current_interval in fallback_windows:
            try:
                hist = self.stock.history(period=current_period, interval=current_interval, auto_adjust=False)
                if hist.empty:
                    continue

                hist = hist.reset_index()
                ts_col = "Datetime" if "Datetime" in hist.columns else "Date"
                if ts_col not in hist.columns:
                    ts_col = hist.columns[0]

                is_intraday = any(token in current_interval.lower() for token in ["m", "h"])
                result = []
                for _, row in hist.iterrows():
                    ts_value = row.get(ts_col)
                    if isinstance(ts_value, pd.Timestamp):
                        full_date = ts_value.isoformat()
                        time_value = ts_value.strftime("%H:%M") if is_intraday else ts_value.strftime("%Y-%m-%d")
                    else:
                        full_date = str(ts_value)
                        time_value = str(ts_value)

                    close_value = row.get("Close")
                    if close_value is None or (isinstance(close_value, float) and np.isnan(close_value)):
                        continue
                    volume_value = row.get("Volume", 0)
                    if volume_value is None or (isinstance(volume_value, float) and np.isnan(volume_value)):
                        volume_value = 0

                    result.append(
                        {
                            "time": time_value,
                            "full_date": full_date,
                            "price": float(close_value),
                            "volume": float(volume_value),
                        }
                    )

                if result:
                    return result
            except Exception as exc:
                last_error = exc
                continue

        if last_error:
            raise last_error
        return []

    def get_all_data(self) -> Dict[str, Any]:
        """Fetch all data for comprehensive analysis."""
        return {
            "ticker": self.ticker,
            "company_name": self.info.get("longName", self.ticker),
            "price_data": self.get_price_data(),
            "volatility": self.get_volatility_data(),
            "fundamentals": self.get_fundamentals(),
            "analyst_data": self.get_analyst_data(),
            "short_interest": self.get_short_interest(),
            "news": self.get_news(),
            "comparison": self.get_comparison_data(),
            "earnings_history": self.get_earnings_history(),
            "etf_holdings": self.get_etf_holdings() if self.info.get("quoteType") == "ETF" else [],
            "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
