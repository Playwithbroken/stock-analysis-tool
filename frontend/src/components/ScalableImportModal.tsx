import React, { useState } from "react";
import { Upload, FileText, Check, X, ShieldCheck, Sparkles } from "lucide-react";
import useAccessibleDialog from "../hooks/useAccessibleDialog";

interface ScalableImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => Promise<void> | void;
}

const SAMPLE_DEPOT_TEXT = `SAP.DE 25 182.50
ASML.AS 8 690.00
NVDA 50 112.40
MSFT 20 415.00
AAPL 30 195.00
ALV.DE 35 275.00`;

export default function ScalableImportModal({
  isOpen,
  onClose,
  onSuccess,
}: ScalableImportModalProps) {
  const [mode, setMode] = useState<"text" | "csv">("text");
  const [inputText, setInputText] = useState("");
  const [csvFileName, setCsvFileName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dialogRef = useAccessibleDialog<HTMLDivElement>(
    isOpen,
    onClose,
    "input, textarea, select, button"
  );

  if (!isOpen) return null;

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setCsvFileName(file.name);
    setError(null);
    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result as string;
      setInputText(content);
    };
    reader.onerror = () => {
      setError("Datei konnte nicht gelesen werden.");
    };
    reader.readAsText(file);
  };

  const handleImport = async () => {
    if (!inputText.trim()) {
      setError("Bitte gib Positionen ein oder lade eine CSV-Datei hoch.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/integrations/scalable/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          csv_text: inputText,
          source_label: "manual_import_modal",
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail?.message || data.detail || "Import fehlgeschlagen.");
      }
      await onSuccess();
      onClose();
    } catch (err: any) {
      setError(err.message || "Fehler beim Importieren der Positionen.");
    } finally {
      setLoading(false);
    }
  };

  const handleLoadSample = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/integrations/scalable/load-sample", {
        method: "POST",
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail?.message || data.detail || "Musterdepot konnte nicht geladen werden.");
      }
      await onSuccess();
      onClose();
    } catch (err: any) {
      setError(err.message || "Fehler beim Laden des Musterdepots.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-md dark:bg-black/75"
      role="presentation"
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="scalable-import-title"
        tabIndex={-1}
        className="surface-panel w-full max-w-xl rounded-[2rem] border border-black/8 p-6 dark:border-white/10 dark:bg-[#1c1c1e] shadow-2xl"
      >
        <div className="flex items-center justify-between border-b border-black/6 pb-4 dark:border-white/8">
          <div className="flex items-center gap-2.5">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-black/[0.04] text-slate-800 dark:bg-white/10 dark:text-white">
              <ShieldCheck size={20} />
            </div>
            <div>
              <h3
                id="scalable-import-title"
                className="text-lg font-bold tracking-tight text-slate-900 dark:text-white"
              >
                Scalable Capital Positionen
              </h3>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Direkt importieren, synchronisieren oder als Musterdepot laden
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-full p-2 text-slate-400 transition-colors hover:bg-black/5 hover:text-slate-600 dark:hover:bg-white/10 dark:hover:text-slate-200"
          >
            <X size={18} />
          </button>
        </div>

        <div className="mt-4 flex gap-2">
          <button
            type="button"
            onClick={() => setMode("text")}
            className={`flex-1 rounded-xl py-2.5 text-xs font-extrabold uppercase tracking-[0.14em] transition-all ${
              mode === "text"
                ? "bg-[var(--accent)] text-white shadow-sm"
                : "border border-black/8 bg-black/[0.02] text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-300"
            }`}
          >
            <span className="inline-flex items-center gap-1.5">
              <FileText size={14} />
              Schnelleingabe
            </span>
          </button>
          <button
            type="button"
            onClick={() => setMode("csv")}
            className={`flex-1 rounded-xl py-2.5 text-xs font-extrabold uppercase tracking-[0.14em] transition-all ${
              mode === "csv"
                ? "bg-[var(--accent)] text-white shadow-sm"
                : "border border-black/8 bg-black/[0.02] text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-300"
            }`}
          >
            <span className="inline-flex items-center gap-1.5">
              <Upload size={14} />
              CSV Datei-Upload
            </span>
          </button>
        </div>

        {mode === "text" ? (
          <div className="mt-4 space-y-3">
            <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
              <span>Format: <code>TICKER [STÜCKE] [KAUFKURS]</code> je Zeile</span>
              <button
                type="button"
                onClick={() => setInputText(SAMPLE_DEPOT_TEXT)}
                className="text-[11px] font-bold text-[var(--accent)] hover:underline"
              >
                Vorlage einfügen
              </button>
            </div>
            <textarea
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              placeholder="Beispiel:&#10;NVDA 50 112.40&#10;SAP.DE 25 182.50&#10;MSFT 20 415.00&#10;AAPL 30 195.00"
              rows={6}
              className="w-full rounded-2xl border border-black/8 bg-white dark:border-white/10 dark:bg-[#2c2c2e] p-3 text-sm font-mono text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
            />
          </div>
        ) : (
          <div className="mt-4 space-y-3">
            <label className="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-black/10 dark:border-white/15 p-6 text-center cursor-pointer hover:border-[var(--accent)] transition-colors">
              <Upload size={28} className="text-slate-400 mb-2" />
              <div className="text-sm font-bold text-slate-700 dark:text-slate-200">
                {csvFileName ? csvFileName : "Klicke zum Auswählen der CSV-Datei"}
              </div>
              <div className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                Unterstützt Scalable Capital, Baader Bank oder Standard-CSV (ISIN, Ticker, Stücke, Kaufkurs)
              </div>
              <input
                type="file"
                accept=".csv,.txt"
                onChange={handleFileUpload}
                className="hidden"
              />
            </label>
            {inputText && (
              <div className="text-xs text-slate-500 dark:text-slate-400 truncate">
                Geladen: {inputText.split("\n").filter(Boolean).length} Zeilen
              </div>
            )}
          </div>
        )}

        {error && (
          <div className="mt-3 rounded-xl border border-red-500/20 bg-red-500/10 p-3 text-xs font-semibold text-red-700 dark:text-red-400">
            {error}
          </div>
        )}

        <div className="mt-6 flex flex-col-reverse gap-2.5 sm:flex-row sm:items-center sm:justify-between">
          <button
            type="button"
            onClick={handleLoadSample}
            disabled={loading}
            className="inline-flex items-center justify-center gap-1.5 rounded-xl border border-amber-500/20 bg-amber-500/10 px-4 py-2.5 text-xs font-extrabold uppercase tracking-[0.14em] text-amber-800 dark:text-amber-300 transition-colors hover:bg-amber-500/20 disabled:opacity-50"
          >
            <Sparkles size={14} />
            Musterdepot laden
          </button>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 rounded-xl border border-black/8 bg-white dark:border-white/10 dark:bg-white/5 px-4 py-2.5 text-xs font-extrabold uppercase tracking-[0.14em] text-slate-700 dark:text-slate-300 hover:bg-black/5 dark:hover:bg-white/10"
            >
              Abbrechen
            </button>
            <button
              type="button"
              onClick={handleImport}
              disabled={loading || !inputText.trim()}
              className="flex-1 rounded-xl bg-[var(--accent)] px-5 py-2.5 text-xs font-extrabold uppercase tracking-[0.14em] text-white hover:bg-[var(--accent-strong)] transition-colors disabled:opacity-50"
            >
              <span className="inline-flex items-center gap-1.5">
                <Check size={14} />
                {loading ? "Importiert …" : "Depot importieren"}
              </span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
