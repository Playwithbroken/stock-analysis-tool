import React from "react";
import { ResponsiveContainer, Treemap } from "recharts";
import { useCurrency } from "../context/CurrencyContext";

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
  "#6b21a8", // purple-800
  "#7e22ce", // purple-700
  "#9333ea", // purple-600
  "#a855f7", // purple-500
  "#c084fc", // purple-400
  "#4c1d95", // violet-900
  "#5b21b6", // violet-800
];

const CustomizedContent = (props: any) => {
  const { x, y, width, height, index, ticker, position_value, formatPrice } =
    props;

  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        style={{
          fill: COLORS[index % COLORS.length],
          stroke: "#000",
          strokeWidth: 2 / (props.depth + 1),
          strokeOpacity: 1 / (props.depth + 1),
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
          className="uppercase pointer-events-none"
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
          fillOpacity={0.6}
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
    <div className="bg-[#050507] rounded-2xl p-6 border border-white/5 shadow-inner">
      <h3 className="text-sm font-bold text-gray-400 uppercase tracking-widest mb-6 flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-purple-500 animate-pulse"></span>
        Capital Allocation Heatmap
      </h3>

      <div className="h-[250px] w-full bg-black/5 rounded-xl border border-white/5 relative overflow-hidden">
        <ResponsiveContainer width="99%" height="99%">
          <Treemap
            data={data}
            dataKey="size"
            aspectRatio={4 / 3}
            stroke="#000"
            fill="#8884d8"
            content={<CustomizedContent formatPrice={formatPrice} />}
          />
        </ResponsiveContainer>
      </div>

      <div className="mt-4 flex justify-between items-center text-[10px] text-gray-600 font-bold uppercase tracking-tighter">
        <span>Allocation distribution</span>
        <span>{data.length} Assets</span>
      </div>
    </div>
  );
}
