import React, { useState, useEffect } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { DollarSign, Calendar, TrendingUp } from "lucide-react";
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

const MONTHS = [
  "Jan",
  "Feb",
  "Mär",
  "Apr",
  "Mai",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Okt",
  "Nov",
  "Dez",
];

export default function DividendDashboard({
  portfolioId,
}: DividendDashboardProps) {
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

  if (loading)
    return (
      <div className="bg-[#050507] rounded-2xl p-6 border border-white/5 animate-pulse h-[300px] flex items-center justify-center">
        <div className="text-gray-600 uppercase text-[10px] tracking-widest font-bold">
          Calculating Cashflow...
        </div>
      </div>
    );

  if (data?.error) {
    return (
      <div className="bg-[#050507] rounded-2xl p-6 border border-white/5 h-[300px] flex items-center justify-center">
        <div className="text-red-500 text-xs font-bold text-center">
          {typeof data.error === "string"
            ? data.error
            : "Unable to load dividend data."}
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
    <div className="bg-[#050507] rounded-2xl p-6 border border-white/5 shadow-inner">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
        <div>
          <div className="flex items-center gap-2 text-gray-400 mb-1">
            <DollarSign size={16} className="text-green-500" />
            <span className="text-sm font-medium uppercase tracking-wider">
              Dividend Dashboard
            </span>
          </div>
          <div className="flex items-baseline gap-3">
            <div className="text-2xl font-bold text-white">
              {formatPrice(data?.yearly_total || 0)}
            </div>
            <div className="text-green-400 text-sm font-bold bg-green-500/10 px-2 py-0.5 rounded">
              {data?.yield_on_cost.toFixed(2)}% Yield
            </div>
          </div>
        </div>

        <div className="flex items-center gap-4 text-xs font-bold text-gray-500 uppercase">
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
              stroke="#222"
              vertical={false}
              strokeOpacity={0.1}
            />
            <XAxis
              dataKey="month"
              axisLine={false}
              tickLine={false}
              tick={{ fill: "#444", fontSize: 10 }}
            />
            <YAxis hide />
            <Tooltip
              cursor={{ fill: "rgba(255,255,255,0.03)" }}
              content={({ active, payload }) => {
                if (active && payload && payload.length) {
                  return (
                    <div className="bg-[#0a0a0c] border border-white/10 p-2 rounded-lg shadow-xl">
                      <p className="text-white font-bold">
                        {formatPrice(payload[0].value)}
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
                  fill={entry.value > 0 ? "#10b981" : "#1f2937"}
                  fillOpacity={0.8}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-4 pt-4 border-t border-white/5 grid grid-cols-2 gap-4">
        <div>
          <div className="text-[10px] text-gray-600 uppercase font-bold mb-1">
            Average Monthly
          </div>
          <div className="text-white font-medium">
            {formatPrice((data?.yearly_total || 0) / 12)}
          </div>
        </div>
        <div>
          <div className="text-[10px] text-gray-600 uppercase font-bold mb-1">
            Status
          </div>
          <div className="text-purple-400 font-medium">
            Auto-Harvesting Active
          </div>
        </div>
      </div>
    </div>
  );
}
