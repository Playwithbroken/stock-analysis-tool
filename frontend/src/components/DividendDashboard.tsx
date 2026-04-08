import React, { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Calendar, DollarSign } from "lucide-react";
import { useCurrency } from "../context/CurrencyContext";

interface DividendData {
  monthly: number[];
  yearly_total: number;
  yield_on_cost: number;
  error?: string;
}

interface DividendDashboardProps {
  portfolioId: string;
}

const MONTHS = ["Jan", "Feb", "Mae", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];

export default function DividendDashboard({ portfolioId }: DividendDashboardProps) {
  const { formatPrice } = useCurrency();
  const [data, setData] = useState<DividendData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const res = await fetch(`/api/portfolio/${portfolioId}/dividends`);
        const json = await res.json();
        setData(json);
      } catch (e) {
        console.error("Failed to fetch dividend data", e);
      } finally {
        setLoading(false);
      }
    };
    if (portfolioId) fetchData();
  }, [portfolioId]);

  if (loading) {
    return (
      <div className="surface-panel flex h-[300px] items-center justify-center rounded-[2rem] p-6">
        <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">
          Calculating Cashflow
        </div>
      </div>
    );
  }

  if (data?.error) {
    return (
      <div className="surface-panel flex h-[300px] items-center justify-center rounded-[2rem] p-6">
        <div className="text-center text-xs font-bold text-red-700">
          {typeof data.error === "string" ? data.error : "Unable to load dividend data."}
        </div>
      </div>
    );
  }

  const chartData =
    data?.monthly?.map((val, i) => ({
      month: MONTHS[i],
      value: val,
    })) || [];

  return (
    <div className="surface-panel rounded-[2rem] p-6">
      <div className="mb-8 flex flex-col justify-between gap-4 md:flex-row md:items-center">
        <div>
          <div className="mb-1 flex items-center gap-2 text-slate-500">
            <DollarSign size={16} className="text-emerald-600" />
            <span className="text-sm font-medium uppercase tracking-[0.18em]">
              Dividend Dashboard
            </span>
          </div>
          <div className="flex items-baseline gap-3">
            <div className="text-2xl font-bold text-slate-900">
              {formatPrice(data?.yearly_total || 0)}
            </div>
            <div className="rounded bg-emerald-500/10 px-2 py-0.5 text-sm font-bold text-emerald-700">
              {data?.yield_on_cost.toFixed(2)}% Yield
            </div>
          </div>
        </div>

        <div className="flex items-center gap-4 text-xs font-bold uppercase tracking-[0.16em] text-slate-500">
          <div className="flex items-center gap-1">
            <Calendar size={14} /> Monthly Projection
          </div>
        </div>
      </div>

      <div className="h-[200px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData}>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="rgba(22,28,36,0.08)"
              vertical={false}
            />
            <XAxis
              dataKey="month"
              axisLine={false}
              tickLine={false}
              tick={{ fill: "#7c848f", fontSize: 10 }}
            />
            <YAxis hide />
            <Tooltip
              cursor={{ fill: "rgba(15,118,110,0.05)" }}
              content={({ active, payload }) => {
                if (active && payload && payload.length) {
                  return (
                    <div className="rounded-lg border border-black/8 bg-white p-2 shadow-[0_18px_36px_rgba(17,24,39,0.1)]">
                      <p className="font-bold text-slate-900">
                        {formatPrice(payload[0].value as number)}
                      </p>
                    </div>
                  );
                }
                return null;
              }}
            />
            <Bar dataKey="value" radius={[4, 4, 0, 0]}>
              {chartData.map((entry, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={entry.value > 0 ? "#0f766e" : "#cbd5e1"}
                  fillOpacity={0.82}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4 border-t border-black/8 pt-4">
        <div>
          <div className="mb-1 text-[10px] font-bold uppercase tracking-[0.16em] text-slate-500">
            Average Monthly
          </div>
          <div className="font-medium text-slate-900">
            {formatPrice((data?.yearly_total || 0) / 12)}
          </div>
        </div>
        <div>
          <div className="mb-1 text-[10px] font-bold uppercase tracking-[0.16em] text-slate-500">
            Status
          </div>
          <div className="font-medium text-[var(--accent)]">Auto-Harvesting Active</div>
        </div>
      </div>
    </div>
  );
}
