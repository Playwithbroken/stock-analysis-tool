import React, { useState, useEffect } from "react";
import { ShieldAlert, Info } from "lucide-react";

interface CorrelationData {
  labels: string[];
  values: number[][];
  error?: string;
}

interface RiskMatrixProps {
  portfolioId: string;
}

export default function RiskCorrelationMatrix({
  portfolioId,
}: RiskMatrixProps) {
  const [data, setData] = useState<CorrelationData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const res = await fetch(`/api/portfolio/${portfolioId}/correlation`);
        const json = await res.json();
        setData(json);
      } catch (e) {
        console.error("Failed to fetch correlation", e);
      } finally {
        setLoading(false);
      }
    };
    if (portfolioId) fetchData();
  }, [portfolioId]);

  if (loading) return null;
  if (!data || data.error || !data.labels || data.labels.length < 2) {
    return (
      <div className="bg-[#050507] rounded-2xl p-6 border border-white/5 text-gray-500 text-center text-xs">
        Füge mindestens zwei Assets hinzu, um die Korrelationsmatrix zu sehen.
      </div>
    );
  }

  const getBgColor = (val: number) => {
    if (val === 1) return "bg-white/5";
    if (val > 0.7) return "bg-red-500/40 text-red-200";
    if (val > 0.4) return "bg-orange-500/20 text-orange-200";
    if (val > 0) return "bg-yellow-500/10 text-yellow-100";
    return "bg-green-500/20 text-green-200";
  };

  return (
    <div className="bg-[#050507] rounded-2xl p-6 border border-white/5 shadow-inner">
      <h3 className="text-sm font-bold text-gray-400 uppercase tracking-widest mb-6 flex items-center gap-2">
        <ShieldAlert size={16} className="text-orange-500" />
        Risk Correlation Matrix
      </h3>

      <div className="overflow-x-auto">
        <table className="w-full text-center border-separate border-spacing-1">
          <thead>
            <tr>
              <th className="p-2"></th>
              {data.labels.map((label) => (
                <th
                  key={label}
                  className="p-2 text-[10px] text-gray-500 font-bold uppercase"
                >
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.labels.map((rowLabel, rowIndex) => (
              <tr key={rowLabel}>
                <td className="p-2 text-[10px] text-gray-500 font-bold uppercase text-right">
                  {rowLabel}
                </td>
                {data.values[rowIndex].map((val, colIndex) => (
                  <td
                    key={colIndex}
                    className={`p-3 rounded-lg text-xs font-mono transition-all hover:scale-105 cursor-default ${getBgColor(val)}`}
                    title={`Correlation: ${val.toFixed(2)}`}
                  >
                    {val.toFixed(2)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-6 p-4 bg-white/5 rounded-xl border border-white/5 flex gap-3">
        <Info size={16} className="text-blue-400 shrink-0 mt-0.5" />
        <p className="text-[10px] text-gray-400 leading-tight">
          <strong className="text-white">Interpretation:</strong> Werte nahe{" "}
          <span className="text-red-400">1.0</span> bedeuten hohes Klumpenrisiko
          (Aktien bewegen sich identisch). Werte nahe{" "}
          <span className="text-green-400">0 oder negativ</span> bieten maximale
          Diversifizierung.
        </p>
      </div>
    </div>
  );
}
