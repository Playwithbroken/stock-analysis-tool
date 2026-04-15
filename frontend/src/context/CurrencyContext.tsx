import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  ReactNode,
} from "react";
import { fetchJsonWithRetry } from "../lib/api";

type Currency = "USD" | "EUR";

interface CurrencyContextType {
  currency: Currency;
  setCurrency: (c: Currency) => void;
  exchangeRate: number; // 1 USD = X EUR
  convert: (amount: number, from?: "USD" | "EUR") => number;
  formatPrice: (amount: number, forceCurrency?: Currency) => string;
}

const CurrencyContext = createContext<CurrencyContextType | undefined>(
  undefined,
);

export const CurrencyProvider: React.FC<{ children: ReactNode }> = ({
  children,
}) => {
  const [currency, setCurrency] = useState<Currency>(() => {
    return (localStorage.getItem("preferred_currency") as Currency) || "USD";
  });
  const [exchangeRate, setExchangeRate] = useState<number>(0.92);

  useEffect(() => {
    localStorage.setItem("preferred_currency", currency);
  }, [currency]);

  useEffect(() => {
    const fetchRate = async () => {
      try {
        const data = await fetchJsonWithRetry<{ rate?: number }>(
          "/api/market/exchange-rate",
          undefined,
          { retries: 1, retryDelayMs: 1000 },
        );
        if (data.rate) {
          setExchangeRate(data.rate);
        }
      } catch {
        // Silently fall back to default rate (0.92) — not critical
      }
    };
    fetchRate();
    // Refresh every hour
    const interval = setInterval(fetchRate, 3600000);
    return () => clearInterval(interval);
  }, []);

  const convert = (amount: number, from: "USD" | "EUR" = "USD"): number => {
    if (!amount) return 0;
    if (currency === from) return amount;

    if (from === "USD" && currency === "EUR") {
      return amount * exchangeRate;
    } else if (from === "EUR" && currency === "USD") {
      return amount / exchangeRate;
    }
    return amount;
  };

  const formatPrice = (amount: number, forceCurrency?: Currency): string => {
    const activeCurrency = forceCurrency || currency;
    const value = convert(amount, "USD"); // Assuming input is always USD/Base

    return new Intl.NumberFormat("de-DE", {
      style: "currency",
      currency: activeCurrency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  };

  return (
    <CurrencyContext.Provider
      value={{ currency, setCurrency, exchangeRate, convert, formatPrice }}
    >
      {children}
    </CurrencyContext.Provider>
  );
};

export const useCurrency = () => {
  const context = useContext(CurrencyContext);
  if (!context) {
    throw new Error("useCurrency must be used within a CurrencyProvider");
  }
  return context;
};
