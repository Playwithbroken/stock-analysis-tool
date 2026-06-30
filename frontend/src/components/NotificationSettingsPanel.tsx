import React, { useEffect, useState } from "react";
import { useTheme } from "../context/ThemeContext";

interface NotificationSettingsPanelProps {
  onSaved?: () => void;
}

interface WorkspaceProfile {
  display_name: string;
  timezone: string;
  browser_notifications: boolean;
  theme: string;
  advisory_enabled: boolean;
  advisory_profile_complete?: boolean;
  investment_objective: string;
  time_horizon: string;
  risk_tolerance: string;
  experience_level: string;
  loss_capacity: string;
  liquidity_need: string;
  preferred_strategy: string;
  max_single_position_pct: number;
  max_portfolio_drawdown_pct: number;
  suitability_notes: string;
}

interface NotificationStatus {
  alerts_enabled: boolean;
  email?: { configured: boolean; from?: string; to?: string };
  telegram?: { enabled: boolean; configured: boolean };
  macro_alerts?: {
    enabled: boolean;
    channel: string;
    min_score: number;
    cooldown_hours: number;
    max_items: number;
  };
  schedule?: { timezone: string; europe_open: string; us_open: string };
}

const initialProfile: WorkspaceProfile = {
  display_name: "",
  timezone: "Europe/Berlin",
  browser_notifications: false,
  theme: "premium-light",
  advisory_enabled: true,
  advisory_profile_complete: false,
  investment_objective: "mixed",
  time_horizon: "medium",
  risk_tolerance: "medium",
  experience_level: "intermediate",
  loss_capacity: "medium",
  liquidity_need: "medium",
  preferred_strategy: "mixed",
  max_single_position_pct: 12.5,
  max_portfolio_drawdown_pct: 20,
  suitability_notes: "",
};

const advisoryOptions = {
  investment_objective: [
    ["mixed", "Balanced"],
    ["growth", "Growth"],
    ["income", "Income"],
    ["capital_preservation", "Capital protection"],
    ["speculation", "Speculation"],
  ],
  time_horizon: [
    ["medium", "Medium"],
    ["short", "Short"],
    ["long", "Long"],
  ],
  risk_tolerance: [
    ["medium", "Medium"],
    ["low", "Low"],
    ["high", "High"],
    ["speculative", "Speculative"],
  ],
  experience_level: [
    ["intermediate", "Intermediate"],
    ["beginner", "Beginner"],
    ["advanced", "Advanced"],
    ["professional", "Professional"],
  ],
  loss_capacity: [
    ["medium", "Medium"],
    ["low", "Low"],
    ["high", "High"],
  ],
  liquidity_need: [
    ["medium", "Medium"],
    ["low", "Low"],
    ["high", "High"],
  ],
  preferred_strategy: [
    ["mixed", "Mixed"],
    ["long_term", "Long term"],
    ["dividend", "Dividend"],
    ["swing_trading", "Swing"],
    ["day_trading", "Daytrading"],
  ],
};

export default function NotificationSettingsPanel({
  onSaved,
}: NotificationSettingsPanelProps) {
  const { theme, setTheme } = useTheme();
  const [profile, setProfile] = useState<WorkspaceProfile>(initialProfile);
  const [notificationStatus, setNotificationStatus] = useState<NotificationStatus | null>(null);
  const [saving, setSaving] = useState(false);
  const [statusText, setStatusText] = useState("");

  useEffect(() => {
    const load = async () => {
      const [profileRes, notificationRes] = await Promise.all([
        fetch("/api/settings/profile").then((r) => r.json()),
        fetch("/api/notifications/status").then((r) => r.json()),
      ]);
      setProfile({ ...initialProfile, ...profileRes });
      setNotificationStatus(notificationRes);
    };
    load().catch(() => {
      setStatusText("Settings konnten nicht geladen werden.");
    });
  }, []);

  const saveProfile = async (patch?: Partial<WorkspaceProfile>) => {
    setSaving(true);
    try {
      const nextProfile = { ...profile, ...(patch || {}) };
      const res = await fetch("/api/settings/profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(nextProfile),
      });
      const payload = await res.json();
      setProfile(payload);
      setStatusText("Settings gespeichert.");
      onSaved?.();
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="surface-panel rounded-[2rem] p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
            Notification Settings
          </div>
          <h2 className="mt-2 text-3xl text-slate-900">Workspace profile and delivery</h2>
          <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-600">
            Lokales Profil, Telegram-Status und Open-Brief-Zeiten. Email und Browser-Push bleiben
            fuer diese private Beta bewusst aus, damit keine doppelten oder nervigen Meldungen entstehen.
          </p>
        </div>
        {statusText ? (
          <div className="text-xs font-semibold text-slate-500">{statusText}</div>
        ) : null}
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-[1.4rem] border border-black/8 bg-white/75 p-4">
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
              Display name
            </div>
            <input
              value={profile.display_name}
              onChange={(e) => setProfile((prev) => ({ ...prev, display_name: e.target.value }))}
              className="mt-3 w-full rounded-xl border border-black/8 bg-white px-3 py-2 text-sm font-semibold text-slate-800"
            />
          </div>
          <div className="rounded-[1.4rem] border border-black/8 bg-white/75 p-4">
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
              Timezone
            </div>
            <input
              value={profile.timezone}
              onChange={(e) => setProfile((prev) => ({ ...prev, timezone: e.target.value }))}
              className="mt-3 w-full rounded-xl border border-black/8 bg-white px-3 py-2 text-sm font-semibold text-slate-800"
            />
          </div>
          <div className="rounded-[1.4rem] border border-black/8 bg-white/75 p-4">
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
              Theme
            </div>
            <select
              value={theme}
              onChange={(e) => {
                const t = e.target.value as "premium-light" | "dark";
                setTheme(t);
                setProfile((prev) => ({ ...prev, theme: t }));
              }}
              className="mt-3 w-full rounded-xl border border-black/8 bg-white px-3 py-2 text-sm font-semibold text-slate-800"
            >
              <option value="premium-light">Premium Light</option>
              <option value="dark">Dark Mode</option>
            </select>
          </div>

          <div className="md:col-span-2 flex flex-wrap gap-3">
            <button
              onClick={() => saveProfile()}
              disabled={saving}
              className="rounded-xl bg-[var(--accent)] px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-white transition-colors hover:bg-[var(--accent-strong)] disabled:opacity-50"
            >
              Save settings
            </button>
          </div>
        </div>

        <AdvisoryProfilePanel
          profile={profile}
          setProfile={setProfile}
          onSave={() => saveProfile()}
          saving={saving}
        />

        <div className="space-y-3">
          <div className="rounded-[1.4rem] border border-black/8 bg-white/75 p-4">
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
              Telegram delivery
            </div>
            <div className="mt-2 text-sm font-black text-slate-900">
              {notificationStatus?.telegram?.configured
                ? notificationStatus?.telegram?.enabled
                  ? "Live"
                  : "Configured"
                : "Missing"}
            </div>
            <div className="mt-1 text-xs text-slate-500">
              {notificationStatus?.telegram?.configured
                ? "Bot und Chat sind verbunden."
                : "TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID und TELEGRAM_ALERTS_ENABLED=true setzen."}
            </div>
          </div>
          <div className="rounded-[1.4rem] border border-black/8 bg-white/75 p-4">
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
              Email / Browser Push
            </div>
            <div className="mt-2 text-sm font-black text-slate-900">
              Aus
            </div>
            <div className="mt-1 text-xs text-slate-500">
              Private Beta nutzt Telegram-only, damit Briefings und Alerts nicht doppelt ankommen.
            </div>
          </div>
          <div className="rounded-[1.4rem] border border-black/8 bg-white/75 p-4">
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
              Macro alerts
            </div>
            <div className="mt-2 text-sm font-black text-slate-900">
              {notificationStatus?.macro_alerts?.enabled ? "Live" : "Disabled"}
            </div>
            <div className="mt-1 text-xs leading-5 text-slate-500">
              Telegram-only / Min score {notificationStatus?.macro_alerts?.min_score ?? 82} /
              Cooldown {notificationStatus?.macro_alerts?.cooldown_hours ?? 3}h / max{" "}
              {notificationStatus?.macro_alerts?.max_items ?? 5}
            </div>
          </div>
          <div className="rounded-[1.4rem] border border-black/8 bg-white/75 p-4">
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
              Scheduled briefs
            </div>
            <div className="mt-2 text-sm font-black text-slate-900">
              {notificationStatus?.schedule?.timezone || "Europe/Berlin"}
            </div>
            <div className="mt-1 text-xs text-slate-500">
              Europe {notificationStatus?.schedule?.europe_open || "--:--"} / US {notificationStatus?.schedule?.us_open || "--:--"}
            </div>
          </div>
        </div>

        <ManualTelegramTrigger />
        <ManualPaperAccountStatusTrigger />
        <ManualMacroAlertTrigger />
      </div>
    </section>
  );
}

function AdvisoryProfilePanel({
  profile,
  setProfile,
  onSave,
  saving,
}: {
  profile: WorkspaceProfile;
  setProfile: React.Dispatch<React.SetStateAction<WorkspaceProfile>>;
  onSave: () => void;
  saving: boolean;
}) {
  const setField = (field: keyof WorkspaceProfile, value: string | number | boolean) => {
    setProfile((prev) => ({ ...prev, [field]: value }));
  };

  const strictLimit =
    Number(profile.max_single_position_pct || 0) <= 8 ||
    Number(profile.max_portfolio_drawdown_pct || 0) <= 12 ||
    profile.risk_tolerance === "low" ||
    profile.loss_capacity === "low";

  return (
    <div className="rounded-[1.4rem] border border-black/8 bg-white/75 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
            Advisory profile
          </div>
          <div className="mt-2 text-xl font-black text-slate-950">Suitability rules</div>
          <p className="mt-2 max-w-2xl text-xs leading-5 text-slate-600">
            Jeder Setup-Impuls wird gegen Ziel, Erfahrung, Verlusttragfaehigkeit und
            Positionsgroesse geprueft. Das verhindert blinde Trades.
          </p>
        </div>
        <div
          className={`rounded-full px-3 py-1 text-[10px] font-black uppercase tracking-[0.16em] ${
            profile.advisory_profile_complete
              ? "bg-emerald-100 text-emerald-800"
              : "bg-amber-100 text-amber-800"
          }`}
        >
          {profile.advisory_profile_complete ? "Active" : "Needs review"}
        </div>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <AdvisorySelect
          label="Objective"
          value={profile.investment_objective}
          options={advisoryOptions.investment_objective}
          onChange={(value) => setField("investment_objective", value)}
        />
        <AdvisorySelect
          label="Strategy"
          value={profile.preferred_strategy}
          options={advisoryOptions.preferred_strategy}
          onChange={(value) => setField("preferred_strategy", value)}
        />
        <AdvisorySelect
          label="Risk"
          value={profile.risk_tolerance}
          options={advisoryOptions.risk_tolerance}
          onChange={(value) => setField("risk_tolerance", value)}
        />
        <AdvisorySelect
          label="Experience"
          value={profile.experience_level}
          options={advisoryOptions.experience_level}
          onChange={(value) => setField("experience_level", value)}
        />
        <AdvisorySelect
          label="Loss capacity"
          value={profile.loss_capacity}
          options={advisoryOptions.loss_capacity}
          onChange={(value) => setField("loss_capacity", value)}
        />
        <AdvisorySelect
          label="Liquidity"
          value={profile.liquidity_need}
          options={advisoryOptions.liquidity_need}
          onChange={(value) => setField("liquidity_need", value)}
        />
        <AdvisorySelect
          label="Horizon"
          value={profile.time_horizon}
          options={advisoryOptions.time_horizon}
          onChange={(value) => setField("time_horizon", value)}
        />
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <AdvisoryNumber
          label="Max single position"
          suffix="%"
          value={profile.max_single_position_pct}
          onChange={(value) => setField("max_single_position_pct", value)}
        />
        <AdvisoryNumber
          label="Max drawdown"
          suffix="%"
          value={profile.max_portfolio_drawdown_pct}
          onChange={(value) => setField("max_portfolio_drawdown_pct", value)}
        />
      </div>

      <textarea
        value={profile.suitability_notes}
        onChange={(e) => setField("suitability_notes", e.target.value)}
        placeholder="Eigene Regeln: z.B. keine Earnings-Gambles, kein Hebel, nur bestaetigte Trigger."
        className="mt-3 min-h-[86px] w-full rounded-xl border border-black/8 bg-white px-3 py-2 text-sm font-semibold leading-6 text-slate-800 outline-none transition focus:border-teal-400"
      />

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <div className={`text-xs font-semibold ${strictLimit ? "text-amber-700" : "text-emerald-700"}`}>
          {strictLimit
            ? "Konservativer Rahmen: riskante Setups werden schneller blockiert."
            : "Aktiver Rahmen: passende Setups duerfen nach Trigger-Pruefung weiterlaufen."}
        </div>
        <button
          type="button"
          onClick={onSave}
          disabled={saving}
          className="rounded-xl bg-slate-950 px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-white transition hover:bg-slate-800 disabled:opacity-50"
        >
          {saving ? "Saving..." : "Save advisory"}
        </button>
      </div>
    </div>
  );
}

function AdvisorySelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[][];
  onChange: (value: string) => void;
}) {
  return (
    <label className="block rounded-2xl border border-black/8 bg-white/70 p-3">
      <span className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
        {label}
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-2 w-full rounded-xl border border-black/8 bg-white px-3 py-2 text-sm font-black text-slate-900"
      >
        {options.map(([optionValue, optionLabel]) => (
          <option key={optionValue} value={optionValue}>
            {optionLabel}
          </option>
        ))}
      </select>
    </label>
  );
}

function AdvisoryNumber({
  label,
  value,
  suffix,
  onChange,
}: {
  label: string;
  value: number;
  suffix: string;
  onChange: (value: number) => void;
}) {
  return (
    <label className="block rounded-2xl border border-black/8 bg-white/70 p-3">
      <span className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
        {label}
      </span>
      <div className="mt-2 flex items-center gap-2 rounded-xl border border-black/8 bg-white px-3 py-2">
        <input
          type="number"
          min={1}
          max={100}
          step={0.5}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="w-full bg-transparent text-sm font-black text-slate-900 outline-none"
        />
        <span className="text-xs font-black text-slate-500">{suffix}</span>
      </div>
    </label>
  );
}

function ManualMacroAlertTrigger() {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string>("");

  const check = async () => {
    setBusy(true);
    setMsg("");
    try {
      const res = await fetch("/api/signals/alerts/critical-market", { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setMsg(`Fehler: ${data.detail || "Macro check failed"}`);
      } else if (Number(data.sent || 0) > 0) {
        setMsg(`Gesendet: ${data.sent} Macro Alert${Number(data.sent) === 1 ? "" : "s"}.`);
      } else {
        setMsg(data.message || "Keine neuen Macro Alerts.");
      }
    } catch (e) {
      setMsg(`Fehler: ${(e as Error).message}`);
    } finally {
      setBusy(false);
      window.setTimeout(() => setMsg(""), 6000);
    }
  };

  return (
    <div className="rounded-[1.4rem] border border-amber-500/20 bg-amber-50/50 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-amber-700">
            Check macro alerts
          </div>
          <div className="mt-1 text-xs leading-5 text-slate-600">
            Prueft Krieg, Wahlen, Zentralbanken, Oel und Policy-News gegen das
            Qualitaetsgate und sendet nur neue High-Impact-Treffer an Telegram.
          </div>
        </div>
        <button
          onClick={check}
          disabled={busy}
          className="rounded-xl bg-slate-950 px-4 py-2 text-sm font-bold text-white shadow-sm transition hover:bg-slate-800 disabled:opacity-50"
        >
          {busy ? "Checking..." : "Check now"}
        </button>
      </div>
      {msg ? (
        <div
          className={`mt-3 text-xs font-semibold ${
            msg.startsWith("Fehler") ? "text-rose-700" : "text-emerald-700"
          }`}
        >
          {msg}
        </div>
      ) : null}
    </div>
  );
}

function ManualTelegramTrigger() {
  const [session, setSession] = useState<string>("global");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string>("");

  const sessions: Array<{ value: string; label: string }> = [
    { value: "global", label: "Morning Brief (full)" },
    { value: "europe", label: "Europe Open" },
    { value: "midday", label: "Midday Pulse" },
    { value: "usa", label: "US Open" },
    { value: "europe_close", label: "Europe Close" },
    { value: "usa_close", label: "US Close" },
    { value: "close", label: "Daily Recap" },
  ];

  const send = async () => {
    setBusy(true);
    setMsg("");
    try {
      const res = await fetch(
        `/api/admin/send-telegram-brief?session=${encodeURIComponent(session)}`,
        { method: "POST" }
      );
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setMsg(`Fehler: ${data.detail || "Send failed"}`);
      } else {
        setMsg(`Gesendet: ${data.message || "Sent."}`);
      }
    } catch (e) {
      setMsg(`Fehler: ${(e as Error).message}`);
    } finally {
      setBusy(false);
      window.setTimeout(() => setMsg(""), 6000);
    }
  };

  return (
    <div className="mt-4 rounded-[1.4rem] border border-teal-500/20 bg-teal-50/40 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-teal-700">
            Send Telegram brief now
          </div>
          <div className="mt-1 text-xs text-slate-600">
            Manually trigger any session brief - useful before market open or
            to verify the bot link.
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={session}
            onChange={(e) => setSession(e.target.value)}
            className="rounded-xl border border-black/10 bg-white/80 px-3 py-2 text-sm font-semibold text-slate-800"
            disabled={busy}
          >
            {sessions.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
          <button
            onClick={send}
            disabled={busy}
            className="rounded-xl bg-teal-600 px-4 py-2 text-sm font-bold text-white shadow-sm transition hover:bg-teal-700 disabled:opacity-50"
          >
            {busy ? "Sending..." : "Send to Telegram"}
          </button>
        </div>
      </div>
      {msg ? (
        <div
          className={`mt-3 text-xs font-semibold ${
            msg.startsWith("Gesendet") ? "text-emerald-700" : "text-rose-700"
          }`}
        >
          {msg}
        </div>
      ) : null}
    </div>
  );
}

function ManualPaperAccountStatusTrigger() {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string>("");

  const send = async () => {
    setBusy(true);
    setMsg("");
    try {
      const res = await fetch("/api/admin/send-paper-account-status", { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setMsg(`Fehler: ${data.detail || "Send failed"}`);
      } else {
        const account = data.demo_account || {};
        const status = account.day_status || data.status || "sent";
        const pnl =
          account.net_pnl_value != null
            ? ` / P&L ${Number(account.net_pnl_value).toFixed(2)} (${Number(account.net_pnl_pct || 0).toFixed(2)}%)`
            : "";
        setMsg(`Gesendet: ${status}${pnl}`);
      }
    } catch (e) {
      setMsg(`Fehler: ${(e as Error).message}`);
    } finally {
      setBusy(false);
      window.setTimeout(() => setMsg(""), 7000);
    }
  };

  return (
    <div className="mt-4 rounded-[1.4rem] border border-emerald-500/20 bg-emerald-50/45 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-emerald-700">
            Paper account to Telegram
          </div>
          <div className="mt-1 text-xs leading-5 text-slate-600">
            Sendet den aktuellen 500k-Demo-Status mit Equity, offenem Risiko,
            P&L und den wichtigsten Trade-Checks.
          </div>
        </div>
        <button
          onClick={send}
          disabled={busy}
          className="rounded-xl bg-emerald-700 px-4 py-2 text-sm font-bold text-white shadow-sm transition hover:bg-emerald-800 disabled:opacity-50"
        >
          {busy ? "Sending..." : "Send paper status"}
        </button>
      </div>
      {msg ? (
        <div
          className={`mt-3 text-xs font-semibold ${
            msg.startsWith("Gesendet") ? "text-emerald-700" : "text-rose-700"
          }`}
        >
          {msg}
        </div>
      ) : null}
    </div>
  );
}
