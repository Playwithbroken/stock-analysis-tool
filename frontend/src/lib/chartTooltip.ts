export interface ChartTooltipPoint {
  time: string;
  full_date?: string;
  price: number;
  _volume?: number;
  _rsi?: number | null;
  _macd?: number | null;
}

export function parseChartNumber(value: unknown): number | null {
  if (typeof value !== "number" && (typeof value !== "string" || value.trim() === "")) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function describeChartFeed(input: {
  connected: boolean;
  connectionState: "live" | "degraded" | "snapshot";
  transportMode: "ws" | "snapshot";
  streaming?: boolean;
}): string {
  if (!input.connected) return "Feed offline";
  if (input.connectionState === "degraded") return "Feed verzögert";
  if (input.transportMode === "ws" && input.connectionState === "live" && input.streaming === true) return "Live-Feed";
  return "Snapshot";
}

export function resolveChartPointIndex(value: unknown, pointCount: number): number | null {
  if (typeof value !== "number" && (typeof value !== "string" || !/^\d+$/.test(value))) return null;
  const index = Number(value);
  return Number.isInteger(index) && index >= 0 && index < pointCount ? index : null;
}

export function resolveChartTooltipPoint(payload: unknown): ChartTooltipPoint | null {
  if (!Array.isArray(payload) || !payload.length) return null;
  const entries = payload.filter((entry) => entry && typeof entry === "object") as Array<any>;
  const selected =
    entries.find((entry) => entry.dataKey === "price" && parseChartNumber(entry.payload?.price) !== null) ||
    entries.find((entry) => parseChartNumber(entry.payload?.price) !== null);
  if (!selected?.payload) return null;
  const price = parseChartNumber(selected.payload.price);
  if (price === null) return null;
  return { ...selected.payload, price } as ChartTooltipPoint;
}

export function formatChartTooltipDate(point: ChartTooltipPoint, periodId: string): string {
  const raw = point.full_date || point.time;
  const parsed = new Date(raw);
  if (!Number.isFinite(parsed.getTime())) return raw;
  const intraday = periodId === "1d" || periodId === "5d";
  return new Intl.DateTimeFormat("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    ...(intraday ? { hour: "2-digit", minute: "2-digit" } : {}),
  }).format(parsed);
}

export function formatChartAxisDate(point: ChartTooltipPoint | undefined, periodId: string): string {
  if (!point) return "";
  const raw = point.full_date || point.time;
  const parsed = new Date(raw);
  if (!Number.isFinite(parsed.getTime())) return raw;
  const options: Intl.DateTimeFormatOptions = periodId === "1d"
    ? { hour: "2-digit", minute: "2-digit" }
    : periodId === "5d"
      ? { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }
      : periodId === "1mo"
        ? { day: "2-digit", month: "2-digit" }
        : { month: "2-digit", year: "2-digit" };
  return new Intl.DateTimeFormat("de-DE", options).format(parsed);
}

export function calculateChartChangePct(fromPrice: unknown, toPrice: unknown): number | null {
  const start = parseChartNumber(fromPrice);
  const end = parseChartNumber(toPrice);
  if (start === null || end === null || start === 0) return null;
  return ((end / start) - 1) * 100;
}
