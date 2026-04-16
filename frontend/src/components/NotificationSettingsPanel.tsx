import React, { useEffect, useState } from "react";
import { useTheme } from "../context/ThemeContext";

interface NotificationSettingsPanelProps {
  onSaved?: () => void;
}

interface WorkspaceProfile {
  display_name: string;
  email: string;
  timezone: string;
  browser_notifications: boolean;
  theme: string;
}

interface NotificationStatus {
  alerts_enabled: boolean;
  email?: { configured: boolean; from?: string; to?: string };
  telegram?: { enabled: boolean; configured: boolean };
  schedule?: { timezone: string; europe_open: string; us_open: string };
}

const initialProfile: WorkspaceProfile = {
  display_name: "",
  email: "",
  timezone: "Europe/Berlin",
  browser_notifications: false,
  theme: "premium-light",
};

export default function NotificationSettingsPanel({
  onSaved,
}: NotificationSettingsPanelProps) {
  const { theme, setTheme } = useTheme();
  const [profile, setProfile] = useState<WorkspaceProfile>(initialProfile);
  const [notificationStatus, setNotificationStatus] = useState<NotificationStatus | null>(null);
  const [permission, setPermission] = useState<string>(
    typeof Notification !== "undefined" ? Notification.permission : "unsupported",
  );
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

  const requestBrowserPermission = async () => {
    if (typeof Notification === "undefined") {
      setStatusText("Browser Notifications werden hier nicht unterstuetzt.");
      return;
    }
    const next = await Notification.requestPermission();
    setPermission(next);
    if (next === "granted") {
      await saveProfile({ browser_notifications: true });
      new Notification("Browser Alerts aktiv", {
        body: "Die App kann dir jetzt direkt im Browser Signale anzeigen.",
      });
    } else {
      await saveProfile({ browser_notifications: false });
      setStatusText("Browser-Notifications wurden nicht erlaubt.");
    }
  };

  const sendBrowserTest = () => {
    if (typeof Notification === "undefined" || Notification.permission !== "granted") {
      setStatusText("Erst Browser-Notifications aktivieren.");
      return;
    }
    new Notification("Market Alert Test", {
      body: "Broker Freund meldet: Browser-Notifications funktionieren.",
    });
    setStatusText("Browser-Test wurde gesendet.");
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
            Lokales Profil fuer deinen Workspace, Browser-Alerts fuer Web und ein klarer Status
            fuer Mail, Telegram und Open-Brief-Zeiten.
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
              Email
            </div>
            <input
              value={profile.email}
              onChange={(e) => setProfile((prev) => ({ ...prev, email: e.target.value }))}
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
            <button
              onClick={requestBrowserPermission}
              className="rounded-xl border border-black/8 bg-white px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-700"
            >
              Enable browser alerts
            </button>
            <button
              onClick={sendBrowserTest}
              className="rounded-xl border border-black/8 bg-white px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-700"
            >
              Test browser alert
            </button>
          </div>
        </div>

        <div className="space-y-3">
          <div className="rounded-[1.4rem] border border-black/8 bg-white/75 p-4">
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
              Browser
            </div>
            <div className="mt-2 text-sm font-black text-slate-900">
              {permission === "granted"
                ? "Granted"
                : permission === "denied"
                  ? "Blocked"
                  : permission === "unsupported"
                    ? "Unsupported"
                    : "Not yet allowed"}
            </div>
            <div className="mt-1 text-xs text-slate-500">
              {profile.browser_notifications ? "Stored as active in workspace profile." : "Not active in profile."}
            </div>
          </div>
          <div className="rounded-[1.4rem] border border-black/8 bg-white/75 p-4">
            <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
              Email delivery
            </div>
            <div className="mt-2 text-sm font-black text-slate-900">
              {notificationStatus?.email?.configured ? "Configured" : "Missing"}
            </div>
            <div className="mt-1 text-xs text-slate-500">
              {notificationStatus?.email?.to || "No recipient configured"}
            </div>
          </div>
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
                ? "Bot and chat linked."
                : "Telegram token and chat id required."}
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
              Europe {notificationStatus?.schedule?.europe_open || "--:--"} • US {notificationStatus?.schedule?.us_open || "--:--"}
            </div>
          </div>
        </div>

        <ManualTelegramTrigger />
      </div>
    </section>
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
        setMsg(`✕ ${data.detail || "Send failed"}`);
      } else {
        setMsg(`✓ ${data.message || "Sent."}`);
      }
    } catch (e) {
      setMsg(`✕ Network error: ${(e as Error).message}`);
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
            Manually trigger any session brief — useful before market open or
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
            {busy ? "Sending…" : "Send to Telegram"}
          </button>
        </div>
      </div>
      {msg ? (
        <div
          className={`mt-3 text-xs font-semibold ${
            msg.startsWith("✓") ? "text-emerald-700" : "text-rose-700"
          }`}
        >
          {msg}
        </div>
      ) : null}
    </div>
  );
}
