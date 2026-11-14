import React, { useEffect, useState } from "react";
import { Upload, FileText, Check, X, ShieldCheck, Sparkles, KeyRound, ExternalLink, RefreshCw } from "lucide-react";
import useAccessibleDialog from "../hooks/useAccessibleDialog";

interface ScalableImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => Promise<void> | void;
}

interface UploadedSessionFile {
  filename: string;
  content: string;
  encoding: "utf-8" | "base64";
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
  const [mode, setMode] = useState<"text" | "csv" | "session">("text");
  const [inputText, setInputText] = useState("");
  const [csvFileName, setCsvFileName] = useState("");
  const [sessionFiles, setSessionFiles] = useState<UploadedSessionFile[]>([]);
  const [sessionJsonText, setSessionJsonText] = useState("");
  const [oauthState, setOauthState] = useState<{
    status: "idle" | "pending" | "connected" | "error";
    verification_url?: string | null;
    user_code?: string | null;
    output?: string;
    error?: string | null;
  }>({ status: "idle" });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen || mode !== "session" || oauthState.status !== "pending") return;
    const timer = window.setInterval(async () => {
      try {
        const res = await fetch("/api/integrations/scalable/login/status", { credentials: "same-origin" });
        if (!res.ok) return;
        const data = await res.json();
        setOauthState(data);
        if (data.status === "connected") {
          window.clearInterval(timer);
          await onSuccess();
          onClose();
        } else if (data.status === "error") {
          window.clearInterval(timer);
          setError(data.error || "Scalable OAuth-Login fehlgeschlagen.");
        }
      } catch {
        // Keep polling while server completes OAuth handshake
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [isOpen, mode, oauthState.status, onClose, onSuccess]);

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

  const handleStartOAuthLogin = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/integrations/scalable/login/start", {
        method: "POST",
        credentials: "same-origin",
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail?.message || data.detail || "OAuth-Login konnte nicht gestartet werden.");
      }
      setOauthState(data);
      if (data.status === "connected") {
        await onSuccess();
        onClose();
      } else if (data.status === "error") {
        setError(data.error || "Scalable OAuth-Login fehlgeschlagen.");
      }
    } catch (err: any) {
      setError(err?.message || "Fehler beim Starten des Scalable OAuth-Logins.");
    } finally {
      setLoading(false);
    }
  };

  const handleSessionFilesUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = Array.from(e.target.files || []);
    if (!fileList.length) return;
    setError(null);
    try {
      const loaded: UploadedSessionFile[] = await Promise.all(
        fileList.map(
          (file) =>
            new Promise<UploadedSessionFile>((resolve, reject) => {
              const reader = new FileReader();
              const isText = /\.(json|toml|pem|key)$/i.test(file.name);
              reader.onload = () => {
                if (isText) {
                  resolve({
                    filename: file.name,
                    content: String(reader.result || ""),
                    encoding: "utf-8",
                  });
                } else {
                  const buf = reader.result as ArrayBuffer;
                  const bytes = new Uint8Array(buf);
                  let binary = "";
                  for (let i = 0; i < bytes.byteLength; i += 1) {
                    binary += String.fromCharCode(bytes[i]);
                  }
                  resolve({
                    filename: file.name,
                    content: btoa(binary),
                    encoding: "base64",
                  });
                }
              };
              reader.onerror = () => reject(new Error(`Datei ${file.name} konnte nicht gelesen werden.`));
              if (isText) {
                reader.readAsText(file);
              } else {
                reader.readAsArrayBuffer(file);
              }
            })
        )
      );
      setSessionFiles(loaded);
    } catch (err: any) {
      setError(err?.message || "Session-Dateien konnten nicht gelesen werden.");
    }
  };

  const handleSessionSubmit = async () => {
    if (!sessionFiles.length && !sessionJsonText.trim()) {
      setError("Bitte wähle deine session.json (und ggf. Key-Datei) aus oder füge den JSON-Inhalt ein.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/integrations/scalable/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          files: sessionFiles,
          session_json: sessionJsonText.trim() || undefined,
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail?.message || data.detail || "CLI-Session konnte nicht aktiviert werden.");
      }
      await onSuccess();
      onClose();
    } catch (err: any) {
      setError(err.message || "Fehler beim Aktivieren der CLI-Session.");
    } finally {
      setLoading(false);
    }
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
          <button
            type="button"
            onClick={() => setMode("session")}
            className={`flex-1 rounded-xl py-2.5 text-xs font-extrabold uppercase tracking-[0.14em] transition-all ${
              mode === "session"
                ? "bg-[var(--accent)] text-white shadow-sm"
                : "border border-black/8 bg-black/[0.02] text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-300"
            }`}
          >
            <span className="inline-flex items-center gap-1.5">
              <KeyRound size={14} />
              CLI Session
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
        ) : mode === "csv" ? (
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
        ) : (
          <div className="mt-4 space-y-3">
            <div className="rounded-2xl border border-[#0071e3]/20 bg-[#0071e3]/6 p-4 dark:border-[#0071e3]/30 dark:bg-[#0071e3]/10">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="text-xs font-extrabold uppercase tracking-[0.14em] text-[#0071e3] dark:text-[#66b0ff]">
                    Direkt auf dem Server verbinden (OAuth Device-Code)
                  </div>
                  <p className="mt-1 text-xs leading-5 text-slate-600 dark:text-slate-300">
                    Startet <code>sc login --local-read-only</code> auf Railway. Du bestätigst nur kurz im Browser mit 2FA.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={handleStartOAuthLogin}
                  disabled={loading || oauthState.status === "pending"}
                  className="inline-flex shrink-0 items-center justify-center gap-2 rounded-full bg-[#0071e3] px-4 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-white shadow-xs transition-colors hover:bg-[#0077ed] disabled:opacity-50"
                >
                  <RefreshCw size={13} className={oauthState.status === "pending" ? "animate-spin" : ""} />
                  {oauthState.status === "pending" ? "Warte auf 2FA …" : "OAuth-Login starten"}
                </button>
              </div>
              {oauthState.status === "pending" && (
                <div className="mt-3 space-y-2 rounded-xl border border-black/8 bg-white/80 p-3 text-xs dark:border-white/10 dark:bg-[#1c1c1e]/80">
                  {oauthState.verification_url ? (
                    <a
                      href={oauthState.verification_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 font-bold text-[#0071e3] underline break-all"
                    >
                      <ExternalLink size={13} />
                      {oauthState.verification_url}
                    </a>
                  ) : (
                    <div className="text-slate-500 dark:text-slate-400">Generiere Scalable-Anmeldelink …</div>
                  )}
                  {oauthState.user_code && (
                    <div className="font-mono text-sm font-extrabold tracking-widest text-slate-900 dark:text-white">
                      Code: {oauthState.user_code}
                    </div>
                  )}
                  {!oauthState.verification_url && oauthState.output && (
                    <pre className="max-h-24 overflow-auto whitespace-pre-wrap text-[11px] text-slate-500 dark:text-slate-400">
                      {oauthState.output}
                    </pre>
                  )}
                </div>
              )}
            </div>

            <div className="rounded-2xl border border-black/8 bg-black/[0.02] p-3.5 text-xs leading-5 text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-300">
              <div className="font-bold text-slate-900 dark:text-white">
                Alternative: Lokale session.json hochladen
              </div>
              <p className="mt-1">
                Falls du dich auf macOS/Linux mit <code>sc login --local-read-only</code> (<code>session_backend = "file"</code>) angemeldet hast, kannst du hier die <code>session.json</code> hochladen:
              </p>
            </div>
            <label className="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-black/10 dark:border-white/15 p-4 text-center cursor-pointer hover:border-[var(--accent)] transition-colors">
              <KeyRound size={24} className="text-slate-400 mb-1.5" />
              <div className="text-xs font-bold text-slate-700 dark:text-slate-200">
                {sessionFiles.length > 0
                  ? `${sessionFiles.length} Datei(en) ausgewählt: ${sessionFiles.map((f) => f.filename).join(", ")}`
                  : "session.json (und ggf. Signing-Key) auswählen"}
              </div>
              <input
                type="file"
                multiple
                accept=".json,.toml,.pem,.key,.der,.p8"
                onChange={handleSessionFilesUpload}
                className="hidden"
              />
            </label>
            <textarea
              value={sessionJsonText}
              onChange={(e) => setSessionJsonText(e.target.value)}
              placeholder='Optional: Inhalt der session.json direkt hier einfügen ({"access_token": ...})'
              rows={2}
              className="w-full rounded-2xl border border-black/8 bg-white dark:border-white/10 dark:bg-[#2c2c2e] p-3 text-xs font-mono text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
            />
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
              onClick={mode === "session" ? handleSessionSubmit : handleImport}
              disabled={
                loading ||
                (mode === "session" ? !sessionFiles.length && !sessionJsonText.trim() : !inputText.trim())
              }
              className="flex-1 rounded-xl bg-[var(--accent)] px-5 py-2.5 text-xs font-extrabold uppercase tracking-[0.14em] text-white hover:bg-[var(--accent-strong)] transition-colors disabled:opacity-50"
            >
              <span className="inline-flex items-center gap-1.5">
                <Check size={14} />
                {loading
                  ? mode === "session"
                    ? "Aktiviere …"
                    : "Importiert …"
                  : mode === "session"
                    ? "Session aktivieren"
                    : "Depot importieren"}
              </span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
