import React, { useEffect, useState } from "react";
import { Info, ShieldAlert } from "lucide-react";

interface CorrelationData {
  labels: string[];
  values: number[][];
  error?: string;
}

interface RiskMatrixProps {
  portfolioId: string;
}

export default function RiskCorrelationMatrix({ portfolioId }: RiskMatrixProps) {
  const [data, setData] = useState<CorrelationData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const res = await fetch(`/api/portfolio/${portfolioId}/correlation`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        setData(json);
      } catch {
        setData(null);
      } finally {
        setLoading(false);
      }
    };
    if (portfolioId) fetchData();
  }, [portfolioId]);

  if (loading) return null;
  if (!data || data.error || !data.labels || data.labels.length < 2) {
    return (
      <div className="surface-panel rounded-[2rem] p-6 text-center text-xs text-slate-500">
        Fuege mindestens zwei Assets hinzu, um die Korrelationsmatrix zu sehen.
      </div>
    );
  }

  const getCellClass = (val: number) => {
    if (val === 1) return "bg-black/[0.04] text-slate-600";
    if (val > 0.7) return "bg-red-500/18 text-red-700";
    if (val > 0.4) return "bg-amber-500/16 text-amber-700";
    if (val > 0) return "bg-yellow-500/12 text-yellow-700";
    return "bg-emerald-500/14 text-emerald-700";
  };

  return (
    <div className="surface-panel rounded-[2rem] p-6">
      <h3 className="mb-6 flex items-center gap-2 text-sm font-bold uppercase tracking-[0.18em] text-slate-500">
        <ShieldAlert size={16} className="text-amber-600" />
        Risk Correlation Matrix
      </h3>

      <div className="overflow-x-auto">
        <table className="w-full border-separate border-spacing-1 text-center">
          <thead>
            <tr>
              <th className="p-2" />
              {data.labels.map((label) => (
                <th
                  key={label}
                  className="p-2 text-[10px] font-bold uppercase tracking-[0.16em] text-slate-500"
                >
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.labels.map((rowLabel, rowIndex) => (
              <tr key={rowLabel}>
                <td className="p-2 text-right text-[10px] font-bold uppercase tracking-[0.16em] text-slate-500">
                  {rowLabel}
                </td>
                {data.values[rowIndex].map((val, colIndex) => (
                  <td
                    key={colIndex}
                    className={`cursor-default rounded-lg p-3 text-xs font-mono transition-all hover:scale-105 ${getCellClass(val)}`}
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

      <div className="mt-6 flex gap-3 rounded-xl border border-black/8 bg-white/72 p-4">
        <Info size={16} className="mt-0.5 shrink-0 text-sky-600" />
        <p className="text-[10px] leading-tight text-slate-600">
          <strong className="text-slate-900">Interpretation:</strong> Werte nahe{" "}
          <span className="text-red-700">1.0</span> bedeuten hohes Klumpenrisiko.
          Werte nahe <span className="text-emerald-700">0 oder negativ</span> bieten
          maximale Diversifizierung.
        </p>
      </div>
    </div>
  );
}
