import React from "react";
import { ResponsiveContainer, Treemap } from "recharts";
import { useCurrency } from "../context/CurrencyContext";
import MeasuredChartFrame from "./MeasuredChartFrame";

interface Holding {
  ticker: string;
  name: string;
  shares: number;
  current_price: number;
  position_value: number;
}

interface PortfolioHeatmapProps {
  holdings: Holding[];
}

const COLORS = [
  "#0f766e",
  "#0d9488",
  "#14b8a6",
  "#5eead4",
  "#1d4ed8",
  "#3b82f6",
  "#93c5fd",
];

const CustomizedContent = (props: any) => {
  const { x, y, width, height, index, ticker, position_value, formatPrice } = props;

  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        style={{
          fill: COLORS[index % COLORS.length],
          stroke: "rgba(255,255,255,0.85)",
          strokeWidth: 1.4 / (props.depth + 1),
        }}
      />
      {width > 30 && height > 20 && (
        <text
          x={x + width / 2}
          y={y + height / 2 - 5}
          textAnchor="middle"
          fill="#fff"
          fontSize={Math.min(width / 6, 12)}
          fontWeight="bold"
          className="pointer-events-none uppercase"
        >
          {ticker}
        </text>
      )}
      {width > 50 && height > 40 && (
        <text
          x={x + width / 2}
          y={y + height / 2 + 10}
          textAnchor="middle"
          fill="#fff"
          fillOpacity={0.72}
          fontSize={Math.min(width / 10, 10)}
          className="pointer-events-none"
        >
          {typeof formatPrice === "function"
            ? formatPrice(position_value)
            : `$${position_value?.toFixed(0)}`}
        </text>
      )}
    </g>
  );
};

export default function PortfolioHeatmap({ holdings }: PortfolioHeatmapProps) {
  const { formatPrice } = useCurrency();
  const data = holdings
    .filter((h) => h.position_value > 0)
    .map((h) => ({
      name: h.name,
      ticker: h.ticker,
      size: h.position_value,
      position_value: h.position_value,
    }))
    .sort((a, b) => b.size - a.size);

  if (data.length === 0) return null;

  return (
    <div className="surface-panel rounded-[2rem] p-6">
      <h3 className="mb-6 flex items-center gap-2 text-sm font-bold uppercase tracking-[0.18em] text-slate-500">
        <span className="h-2 w-2 rounded-full bg-[var(--accent)] animate-pulse" />
        Capital Allocation Heatmap
      </h3>

      <MeasuredChartFrame
        className="relative h-[250px] w-full overflow-hidden rounded-xl border border-black/8 bg-white/72"
        minHeight={250}
      >
        <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={220}>
          <Treemap
            data={data}
            dataKey="size"
            aspectRatio={4 / 3}
            stroke="#ffffff"
            fill="#0f766e"
            content={<CustomizedContent formatPrice={formatPrice} />}
          />
        </ResponsiveContainer>
      </MeasuredChartFrame>

      <div className="mt-4 flex items-center justify-between text-[10px] font-bold uppercase tracking-[0.16em] text-slate-500">
        <span>Allocation distribution</span>
        <span>{data.length} Assets</span>
      </div>
    </div>
  );
}
