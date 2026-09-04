import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import worldMapSvgUrl from "../assets/world-map-wikimedia.svg?url";
import { localizeMarketRegime, normalizeGermanDisplayText } from "../lib/displayText";
import { Bell, Layers3, ListFilter, MapPinned } from "lucide-react";

// Lazy-load world map SVG — keeps initial bundle ~280KB smaller
type CountryTone = "red" | "amber" | "blue" | "green" | "slate";
type MapViewState = { zoom: number; x: number; y: number };

const MAP_MIN_ZOOM = 1;
const MAP_MAX_ZOOM = 2.8;

function clampNumber(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function clampMapView(view: MapViewState): MapViewState {
  const zoom = clampNumber(Number.isFinite(view.zoom) ? view.zoom : 1, MAP_MIN_ZOOM, MAP_MAX_ZOOM);
  if (zoom <= 1.01) return { zoom: 1, x: 0, y: 0 };
  const maxX = 190 * zoom;
  const maxY = 120 * zoom;
  return {
    zoom,
    x: clampNumber(view.x, -maxX, maxX),
    y: clampNumber(view.y, -maxY, maxY),
  };
}

interface RegionAsset {
  ticker: string;
  label: string;
  change_1d?: number | null;
}

interface RegionSummary {
  label: string;
  tone: string;
  avg_change_1d: number;
  assets?: RegionAsset[];
}

interface MapNewsItem {
  title: string;
  region?: string;
  impact?: string;
  publisher?: string;
  link?: string;
  ticker?: string;
  event_type?: string;
  event_intelligence?: {
    impact_score?: number;
    confidence_score?: number;
    decay?: string;
    affected_sectors?: string[];
    affected_assets?: string[];
    action?: string;
    leverage?: string;
    why_now?: string;
    trigger?: string;
    invalidation?: string;
    execution_window?: string;
    decision_quality?: string;
    size_guidance?: string;
    execution_bias?: string;
  };
  portfolio_exposure?: {
    status?: string;
    note?: string;
    action?: string;
    exposure_strength?: string;
    matched_holdings?: string[];
    matched_sectors?: string[];
    hedge_candidates?: Array<{
      ticker?: string;
      label?: string;
    }>;
  };
  geo?: {
    lat: number;
    lon: number;
    place?: string;
    country?: string;
    confidence?: "high" | "medium" | "low";
    source?: "provider" | "resolver" | "fallback";
  };
  map_priority?: number;
}

interface WatchlistImpactItem {
  ticker?: string;
  type?: string;
  summary?: string;
}

interface ContrarianSignalItem {
  ticker?: string;
  title?: string;
  publisher?: string;
  region?: string;
  media_bias?: string;
  contrarian_bias?: string;
  score?: number;
  rsi_14?: number;
  volume_ratio?: number;
  reason?: string;
  link?: string;
}

interface EventPingItem {
  id?: string;
  type?: string;
  severity?: string;
  region?: string;
  symbols?: string[];
  started_at?: string;
  confidence?: number;
  title?: string;
  trade_impact?: {
    action?: string;
    baseline_scenario?: string;
    symbols?: string[];
    trigger?: string;
    invalidation?: string;
    window?: string;
    hedge_idea?: string;
  };
}

interface WorldMarketMapProps {
  regions: RegionSummary[];
  selectedRegion: string;
  onSelectRegion: (regionLabel: string) => void;
  dataCurrent?: boolean;
  news?: MapNewsItem[];
  eventLayer?: MapNewsItem[];
  eventPings?: EventPingItem[];
  watchlistImpact?: WatchlistImpactItem[];
  contrarianSignals?: ContrarianSignalItem[];
  openingTimeline?: Array<{
    stage: string;
    label: string;
    tone: string;
    move: number;
    driver: string;
    catalysts?: string[];
    earnings?: string[];
  }>;
  onAnalyze: (ticker: string) => void;
  focusTicker?: string;
}

interface GeoEvent extends MapNewsItem {
  geoKey?: string;
  markerLabel: string;
  markerTone: CountryTone;
  markerIcon: string;
  pulse: boolean;
  regionKey: "USA" | "Europe" | "Asia" | "Global";
  geoZone?: string;
  geoPlace?: string;
  markerPosition: { left: string; top: string };
}

interface MapAnchor {
  left: string;
  top: string;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function anchorFromGeo(geo?: MapNewsItem["geo"]): MapAnchor | null {
  if (!geo) return null;
  if (!Number.isFinite(geo.lat) || !Number.isFinite(geo.lon)) return null;
  // Calibrated bounds for the drawable part of the SVG map (avoids margin drift).
  const xMin = 4;
  const xMax = 96;
  const yMin = 10;
  const yMax = 88;
  const left = xMin + ((geo.lon + 180) / 360) * (xMax - xMin);
  const top = yMin + ((90 - geo.lat) / 180) * (yMax - yMin);
  return {
    left: `${clamp(left, xMin, xMax).toFixed(2)}%`,
    top: `${clamp(top, yMin, yMax).toFixed(2)}%`,
  };
}

type EventFilter = "all" | "WAR" | "CB" | "OIL" | "VOTE" | "NAT" | "POL";
type EventSort = "impact" | "region" | "latest";
type TimeLens = "live" | "24h" | "7d";

const positions: Record<
  string,
  {
    x: number;
    y: number;
    align: "left" | "right";
    cardWidth: number;
    lineLength: number;
    cardOffsetX: number;
    cardOffsetY: number;
  }
> = {
  // x/y are percentage of the SVG viewport (0-100)
  // USA ~75°W → x≈22%, central US lat ~38°N → y≈42%
  USA: { x: 22, y: 42, align: "left", cardWidth: 150, lineLength: 38, cardOffsetX: 52, cardOffsetY: -10 },
  // Europe center ~15°E → x≈51%, ~50°N → y≈36%
  Europe: { x: 48, y: 36, align: "right", cardWidth: 148, lineLength: 34, cardOffsetX: 44, cardOffsetY: -42 },
  // Asia center ~105°E → x≈74%, ~35°N → y≈40%
  Asia: { x: 74, y: 40, align: "right", cardWidth: 148, lineLength: 34, cardOffsetX: 44, cardOffsetY: -8 },
};

const regionKeywords: Record<string, string[]> = {
  USA: ["usa", "u.s.", "us ", "federal reserve", "fed", "washington", "wall street"],
  Europe: ["europe", "eu", "ecb", "france", "germany", "uk", "britain", "italy"],
  Asia: ["asia", "china", "japan", "hong kong", "taiwan", "korea", "india"],
};

const markerLayout = {
  USA:    { left: "22%",   top: "40%" },
  Europe: { left: "49%",   top: "35%" },
  Asia:   { left: "75%",   top: "39%" },
  Global: { left: "55%",   top: "52%" },
};

// Geo anchors use % of map container (left=longitude-based, top=latitude-based)
// Wikimedia SVG: ~180°W→0% to ~180°E→100%, ~90°N→0% to ~90°S→100%
// lon_pct = (lon + 180) / 360 * 100
// lat_pct = (90 - lat) / 180 * 100
const geoAnchors: Array<{ terms: string[]; anchor: MapAnchor }> = [
  { terms: ["hungary", "budapest"],              anchor: { left: "52%",   top: "33%" } },
  { terms: ["ukraine", "kyiv", "odesa"],         anchor: { left: "53.5%", top: "30%" } },
  { terms: ["poland", "warsaw"],                 anchor: { left: "50%",   top: "29%" } },
  { terms: ["germany", "berlin"],                anchor: { left: "47.5%", top: "28%" } },
  { terms: ["france", "paris"],                  anchor: { left: "45%",   top: "31%" } },
  { terms: ["uk ", "britain", "london", "england"], anchor: { left: "43%", top: "27%" } },
  { terms: ["spain", "madrid"],                  anchor: { left: "43%",   top: "36%" } },
  { terms: ["italy", "rome"],                    anchor: { left: "48.5%", top: "36%" } },
  { terms: ["turkey", "ankara"],                 anchor: { left: "53%",   top: "36%" } },
  { terms: ["russia", "moscow"],                 anchor: { left: "57%",   top: "24%" } },
  { terms: ["lebanon", "beirut"],                anchor: { left: "53.2%", top: "39%" } },
  { terms: ["iran", "tehran"],                   anchor: { left: "57%",   top: "38%" } },
  { terms: ["israel", "gaza", "jerusalem"],      anchor: { left: "53%",   top: "40%" } },
  { terms: ["saudi", "riyadh"],                  anchor: { left: "55.5%", top: "44%" } },
  { terms: ["opec", "oil", "crude", "middle east", "gulf", "red sea", "brent"], anchor: { left: "56%", top: "43%" } },
  { terms: ["egypt", "cairo"],                   anchor: { left: "52%",   top: "41%" } },
  { terms: ["india", "mumbai", "delhi"],         anchor: { left: "65%",   top: "44%" } },
  { terms: ["china", "beijing", "shanghai"],     anchor: { left: "72%",   top: "36%" } },
  { terms: ["taiwan", "taipei"],                 anchor: { left: "77%",   top: "42%" } },
  { terms: ["japan", "tokyo"],                   anchor: { left: "80%",   top: "35%" } },
  { terms: ["hong kong"],                        anchor: { left: "75.5%", top: "43%" } },
  { terms: ["korea", "seoul"],                   anchor: { left: "78%",   top: "35%" } },
  { terms: ["australia", "sydney"],              anchor: { left: "81%",   top: "70%" } },
  { terms: ["brazil", "são paulo", "rio"],       anchor: { left: "32%",   top: "62%" } },
  { terms: ["mexico", "mexico city"],            anchor: { left: "18%",   top: "47%" } },
  { terms: ["canada"],                           anchor: { left: "21%",   top: "24%" } },
  { terms: ["usa", "u.s.", "washington", "wall street", "new york", "federal reserve", "fed"], anchor: { left: "22%", top: "38%" } },
  { terms: ["california", "silicon valley", "san francisco"], anchor: { left: "16%", top: "40%" } },
  { terms: ["south africa", "johannesburg"],     anchor: { left: "51%",   top: "68%" } },
  { terms: ["nigeria", "lagos"],                 anchor: { left: "47%",   top: "52%" } },
];

const markerOffsets: Record<
  GeoEvent["regionKey"],
  Partial<Record<GeoEvent["markerIcon"], { x: number; y: number }>>
> = {
  USA: {
    WAR: { x: -12, y: -8 },
    CB: { x: 12, y: -16 },
    POL: { x: -14, y: 8 },
    VOTE: { x: 14, y: 10 },
    NAT: { x: 0, y: 18 },
  },
  Europe: {
    WAR: { x: -16, y: -8 },
    CB: { x: 12, y: -18 },
    POL: { x: -14, y: 10 },
    VOTE: { x: 14, y: 10 },
    NAT: { x: 0, y: 18 },
  },
  Asia: {
    WAR: { x: -14, y: -8 },
    CB: { x: 10, y: -16 },
    POL: { x: -14, y: 8 },
    VOTE: { x: 14, y: 12 },
    NAT: { x: 2, y: 18 },
  },
  Global: {
    OIL: { x: 0, y: 0 },
    POL: { x: 12, y: -8 },
    CB: { x: -10, y: -10 },
  },
};

const COUNTRY_TOKEN_MAP: Array<{ ids: string[]; terms: string[] }> = [
  { ids: ["us"], terms: ["united states", "usa", "u.s.", "us ", "washington", "new york", "wall street", "federal reserve", "fed"] },
  { ids: ["de"], terms: ["germany", "berlin", "dax"] },
  { ids: ["fr"], terms: ["france", "paris", "cac"] },
  { ids: ["gb"], terms: ["united kingdom", "britain", "uk ", "london", "england", "ftse"] },
  { ids: ["it"], terms: ["italy", "rome"] },
  { ids: ["es"], terms: ["spain", "madrid"] },
  { ids: ["pl"], terms: ["poland", "warsaw"] },
  { ids: ["ua"], terms: ["ukraine", "kyiv", "odesa"] },
  { ids: ["ru"], terms: ["russia", "moscow"] },
  { ids: ["tr"], terms: ["turkey", "ankara"] },
  { ids: ["il"], terms: ["israel", "gaza", "jerusalem"] },
  { ids: ["ir"], terms: ["iran", "tehran"] },
  { ids: ["sa"], terms: ["saudi", "riyadh", "opec"] },
  { ids: ["ae"], terms: ["uae", "emirates", "dubai", "abu dhabi", "gulf"] },
  { ids: ["cn"], terms: ["china", "beijing", "shanghai"] },
  { ids: ["tw"], terms: ["taiwan", "taipei"] },
  { ids: ["jp"], terms: ["japan", "tokyo", "nikkei"] },
  { ids: ["kr"], terms: ["korea", "south korea", "seoul"] },
  { ids: ["in"], terms: ["india", "mumbai", "delhi"] },
  { ids: ["br"], terms: ["brazil", "sao paulo"] },
  { ids: ["ca"], terms: ["canada", "toronto"] },
  { ids: ["mx"], terms: ["mexico", "mexico city"] },
  { ids: ["nl"], terms: ["netherlands", "amsterdam"] },
  { ids: ["ch"], terms: ["switzerland", "zurich"] },
  { ids: ["at"], terms: ["austria", "vienna"] },
  { ids: ["se"], terms: ["sweden", "stockholm"] },
  { ids: ["no"], terms: ["norway", "oslo"] },
  { ids: ["fi"], terms: ["finland", "helsinki"] },
  { ids: ["dk"], terms: ["denmark", "copenhagen"] },
];

const GEO_ZONE_COUNTRIES: Record<string, string[]> = {
  "Middle East": ["il", "ir", "sa", "ae", "tr"],
  "Eastern Europe": ["ua", "ru", "pl"],
  "Western Europe": ["de", "fr", "gb", "it", "es", "nl", "ch", "at"],
  "North Asia": ["cn", "tw", "jp", "kr"],
  "South Asia": ["in"],
  "US East": ["us"],
  "US West": ["us"],
  Europe: ["de", "fr", "gb", "it", "es", "nl", "pl"],
  Asia: ["cn", "tw", "jp", "kr", "in"],
  USA: ["us"],
};

const COUNTRY_TONE_PRIORITY: Record<CountryTone, number> = {
  red: 5,
  amber: 4,
  blue: 3,
  green: 2,
  slate: 1,
};

function formatPct(value: number) {
  if (!Number.isFinite(value)) return "N/A";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function tonePillClass(tone: string) {
  if (tone === "risk-on") return "bg-emerald-500/10 text-emerald-700";
  if (tone === "risk-off") return "bg-red-500/10 text-red-700";
  return "bg-amber-500/10 text-amber-700";
}

function regionBadgeColor(label: string) {
  if (label === "USA") return "bg-sky-500";
  if (label === "Europe") return "bg-indigo-500";
  if (label === "Asia") return "bg-fuchsia-500";
  return "bg-slate-500";
}

function regionFlag(label: string) {
  if (label === "USA") return "US";
  if (label === "Europe") return "EU";
  if (label === "Asia") return "AS";
  return "GL";
}

function regionDisplayLabel(label: string) {
  if (label === "Asia") return "Asien";
  if (label === "Europe") return "Europa";
  return label;
}

function textToneClass(tone: string) {
  if (tone === "risk-on") return "text-emerald-700";
  if (tone === "risk-off") return "text-red-700";
  return "text-amber-700";
}

function markerClass(tone: GeoEvent["markerTone"]) {
  if (tone === "red") return "border-red-500/20 bg-red-500/10 text-red-700";
  if (tone === "amber") return "border-amber-500/20 bg-amber-500/10 text-amber-700";
  if (tone === "blue") return "border-blue-500/20 bg-blue-500/10 text-blue-700";
  if (tone === "green") return "border-emerald-500/20 bg-emerald-500/10 text-emerald-700";
  return "border-slate-400/20 bg-slate-500/10 text-slate-700";
}

function markerAccentClass(tone: GeoEvent["markerTone"]) {
  if (tone === "red") return "bg-red-600";
  if (tone === "amber") return "bg-amber-500";
  if (tone === "blue") return "bg-blue-600";
  if (tone === "green") return "bg-emerald-600";
  return "bg-slate-600";
}

function countryHighlightClass(tone: CountryTone) {
  if (tone === "red") return "macro-country-red";
  if (tone === "amber") return "macro-country-amber";
  if (tone === "blue") return "macro-country-blue";
  if (tone === "green") return "macro-country-green";
  return "macro-country-slate";
}

function countryToneForEvent(item: GeoEvent): CountryTone {
  if (item.markerTone === "red" || item.markerTone === "amber" || item.markerTone === "blue" || item.markerTone === "green") {
    return item.markerTone;
  }
  const action = (item.event_intelligence?.action || "").toLowerCase();
  if (action === "long") return "green";
  return "slate";
}

function countryIdsForEvent(item: GeoEvent) {
  const ids = new Set<string>();
  const addAll = (values?: string[]) => {
    (values || []).forEach((value) => ids.add(value));
  };
  addAll(GEO_ZONE_COUNTRIES[item.geoZone || ""]);
  addAll(GEO_ZONE_COUNTRIES[item.geoPlace || ""]);
  addAll(GEO_ZONE_COUNTRIES[item.regionKey || ""]);

  const haystack = [
    item.geo?.country,
    item.geo?.place,
    item.geoPlace,
    item.geoZone,
    item.region,
    item.title,
    item.event_type,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();

  for (const entry of COUNTRY_TOKEN_MAP) {
    if (entry.terms.some((term) => haystack.includes(term))) {
      addAll(entry.ids);
    }
  }
  return Array.from(ids);
}

function buildCountryHighlights(items: GeoEvent[]) {
  const highlights = new Map<string, CountryTone>();
  for (const item of items) {
    const tone = countryToneForEvent(item);
    for (const id of countryIdsForEvent(item)) {
      const current = highlights.get(id);
      if (!current || COUNTRY_TONE_PRIORITY[tone] > COUNTRY_TONE_PRIORITY[current]) {
        highlights.set(id, tone);
      }
    }
  }
  return highlights;
}

let worldMapSvgPromise: Promise<string> | null = null;

function loadWorldMapBaseSvg() {
  if (!worldMapSvgPromise) {
    worldMapSvgPromise = fetch(worldMapSvgUrl, { cache: "force-cache" })
      .then((response) => {
        if (!response.ok) throw new Error(`World map asset failed with status ${response.status}`);
        return response.text();
      })
      .then((rawSvg) => rawSvg
        .replace(/<\?xml[^>]*>\s*/i, "")
        .replace(/<!DOCTYPE[^>]*>\s*/i, "")
        .replace(
          "<svg ",
          '<svg role="img" aria-label="Weltkarte mit Makroereignissen" class="world-map-inline" viewBox="0 0 1404.7773 600.81262" preserveAspectRatio="xMidYMid meet" ',
        ))
      .catch((error) => {
        worldMapSvgPromise = null;
        throw error;
      });
  }
  return worldMapSvgPromise;
}

const WORLD_MAP_SVG_CACHE = new Map<string, string>();

function buildInlineWorldMapSvg(baseSvg: string, highlights: Map<string, CountryTone>) {
  const signature = [...highlights.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([id, tone]) => `${id}:${tone}`)
    .join("|");
  const cached = WORLD_MAP_SVG_CACHE.get(signature);
  if (cached) return cached;

  let svg = baseSvg;

  highlights.forEach((tone, id) => {
    const className = `macro-country-highlight ${countryHighlightClass(tone)}`;
    const pattern = new RegExp(`<g id="${id}"(?![^>]*macro-country-highlight)([^>]*)>`, "i");
    svg = svg.replace(pattern, `<g id="${id}" class="${className}"$1>`);
  });
  WORLD_MAP_SVG_CACHE.set(signature, svg);
  if (WORLD_MAP_SVG_CACHE.size > 12) {
    const oldestKey = WORLD_MAP_SVG_CACHE.keys().next().value;
    if (oldestKey !== undefined) WORLD_MAP_SVG_CACHE.delete(oldestKey);
  }
  return svg;
}

function InlineWorldMap({
  highlights,
}: {
  highlights: Map<string, CountryTone>;
}) {
  const [baseSvg, setBaseSvg] = useState<string | null>(null);
  const [assetFailed, setAssetFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void loadWorldMapBaseSvg()
      .then((svg) => {
        if (!cancelled) setBaseSvg(svg);
      })
      .catch(() => {
        if (!cancelled) setAssetFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const svg = useMemo(
    () => (baseSvg ? buildInlineWorldMapSvg(baseSvg, highlights) : ""),
    [baseSvg, highlights],
  );

  if (!svg) {
    return (
      <div
        className="world-map-inline-wrap absolute inset-0 flex items-center justify-center bg-slate-50 dark:bg-[#121214]"
        role="img"
        aria-label={assetFailed ? "Weltkarte konnte nicht geladen werden" : "Weltkarte wird geladen"}
        aria-busy={!assetFailed}
      >
        <span className="sr-only">
          {assetFailed ? "Weltkarte konnte nicht geladen werden" : "Weltkarte wird geladen"}
        </span>
      </div>
    );
  }

  return (
    <div
      className="world-map-inline-wrap absolute inset-0"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}

function compactList(items?: string[] | null, limit = 3) {
  return (items || []).filter(Boolean).slice(0, limit);
}

function topGeoZones(items: GeoEvent[], limit = 3) {
  const counts = new Map<string, number>();
  for (const item of items) {
    if (!item.geoZone || item.geoZone === item.regionKey) continue;
    counts.set(item.geoZone, (counts.get(item.geoZone) || 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, limit);
}

function topGeoPlaces(items: GeoEvent[], limit = 4) {
  const counts = new Map<string, number>();
  for (const item of items) {
    if (!item.geoPlace) continue;
    counts.set(item.geoPlace, (counts.get(item.geoPlace) || 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, limit);
}

function eventTypeBreakdown(items: GeoEvent[]) {
  const counts = new Map<string, number>();
  for (const item of items) {
    const key = item.markerIcon;
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 4);
}

function buildPlaceVariantStack(items: GeoEvent[]) {
  const impactRank = { high: 3, medium: 2, low: 1 } as const;
  return [...items]
    .sort((a, b) => {
      const scoreA =
        (impactRank[a.impact as keyof typeof impactRank] || 0) +
        (a.event_intelligence?.action && a.event_intelligence.action !== "watch" ? 2 : 0) +
        (a.pulse ? 1 : 0);
      const scoreB =
        (impactRank[b.impact as keyof typeof impactRank] || 0) +
        (b.event_intelligence?.action && b.event_intelligence.action !== "watch" ? 2 : 0) +
        (b.pulse ? 1 : 0);
      return scoreB - scoreA;
    })
    .slice(0, 4)
    .map((item) => ({
      key: item.geoKey || item.title,
      label: describeEventVariant(item) || item.markerLabel,
      eventCode: item.markerIcon,
      impact: item.impact || "macro",
      action: item.event_intelligence?.action || "watch",
      freshness: freshnessLabel(item.event_intelligence?.decay, item.pulse),
      place: item.geoPlace,
      trigger: item.event_intelligence?.trigger,
      thesis: item.event_intelligence?.why_now,
      risk: item.event_intelligence?.invalidation,
      geoKey: item.geoKey,
    }));
}

function buildPlaceHeat(items: GeoEvent[]) {
  const placeMap = new Map<string, { place: string; score: number; events: number; actionable: number }>();
  for (const item of items) {
    if (!item.geoPlace) continue;
    const current = placeMap.get(item.geoPlace) || { place: item.geoPlace, score: 0, events: 0, actionable: 0 };
    const impactScore = item.impact === "high" ? 36 : item.impact === "medium" ? 22 : 10;
    const actionScore = item.event_intelligence?.action && item.event_intelligence.action !== "watch" ? 18 : 6;
    const pulseScore = item.pulse ? 8 : 0;
    current.score += impactScore + actionScore + pulseScore;
    current.events += 1;
    if (item.event_intelligence?.action && item.event_intelligence.action !== "watch") current.actionable += 1;
    placeMap.set(item.geoPlace, current);
  }
  const values = [...placeMap.values()].sort((a, b) => b.score - a.score || a.place.localeCompare(b.place)).slice(0, 5);
  const maxScore = values[0]?.score || 1;
  return values.map((item) => ({
    ...item,
    weight: Math.max(18, Math.round((item.score / maxScore) * 100)),
  }));
}

function placeOutcomeTone(action?: string) {
  if (action === "long") return "bg-emerald-500/10 text-emerald-700";
  if (action === "short") return "bg-red-500/10 text-red-700";
  if (action === "hedge") return "bg-amber-500/10 text-amber-700";
  return "bg-slate-500/10 text-slate-600";
}

function placeOutcomeLabel(action?: string) {
  if (action === "long") return "Chance";
  if (action === "short") return "Risiko";
  if (action === "hedge") return "Absichern";
  return "Beobachten";
}

function describeEventVariant(event: GeoEvent | null) {
  if (!event) return null;
  const title = `${event.title || ""} ${(event.region || "").toLowerCase()}`.toLowerCase();
  const eventType = (event.event_type || "").toLowerCase();

  if (eventType === "conflict") {
    if (/(iran|tehran|israel|gaza|lebanon|beirut|red sea)/.test(title)) return "Nahost-Konflikt";
    if (/(ukraine|kyiv|russia|moscow)/.test(title)) return "Osteuropa-Konflikt";
    if (/(taiwan|china sea|korea)/.test(title)) return "Asien-Pazifik-Konflikt";
    return "Globaler Konflikt";
  }
  if (eventType === "energy") {
    if (/(opec|saudi|gulf|middle east|brent|crude)/.test(title)) return "Öl-Angebotsschock";
    if (/(gas|lng|pipeline)/.test(title)) return "Gas- und Transportstress";
    return "Neubewertung Energie";
  }
  if (eventType === "election") {
    if (/(hungary|budapest|europe|eu|parliament)/.test(title)) return "Europäische Wahl";
    if (/(usa|u.s.|washington|president)/.test(title)) return "US-Wahl";
    return "Politische Abstimmung";
  }
  if (eventType === "policy") {
    if (/(tariff|trade|sanction)/.test(title)) return "Handel und Sanktionen";
    if (/(regulation|policy)/.test(title)) return "Regimewechsel Regulierung";
    return "Politischer Schock";
  }
  if (eventType === "disaster") {
    return "Naturkatastrophe";
  }
  if (eventType === "central_bank") {
    return "Zentralbankwechsel";
  }
  return event.markerLabel;
}

function inferGeoZone(haystack: string, regionKey: GeoEvent["regionKey"]) {
  if (/(iran|tehran|israel|gaza|lebanon|beirut|saudi|gulf|red sea|middle east)/.test(haystack)) return "Middle East";
  if (/(ukraine|kyiv|russia|moscow|poland|warsaw|hungary|budapest|eastern europe)/.test(haystack)) return "Eastern Europe";
  if (/(germany|berlin|france|paris|london|uk |britain|italy|rome|western europe)/.test(haystack)) return "Western Europe";
  if (/(china|beijing|shanghai|hong kong|taiwan|taipei|korea|seoul|japan|tokyo)/.test(haystack)) return "North Asia";
  if (/(india|mumbai|delhi|singapore|southeast asia)/.test(haystack)) return "South Asia";
  if (/(washington|new york|wall street|east coast|federal reserve)/.test(haystack)) return "US East";
  if (/(california|silicon valley|west coast)/.test(haystack)) return "US West";
  return regionKey;
}

function inferGeoPlace(haystack: string, regionKey: GeoEvent["regionKey"]) {
  if (/(hungary|budapest)/.test(haystack)) return "Hungary";
  if (/(ukraine|kyiv|odesa)/.test(haystack)) return "Ukraine";
  if (/(poland|warsaw)/.test(haystack)) return "Poland";
  if (/(germany|berlin)/.test(haystack)) return "Germany";
  if (/(france|paris)/.test(haystack)) return "France";
  if (/(uk |britain|london|england)/.test(haystack)) return "United Kingdom";
  if (/(italy|rome)/.test(haystack)) return "Italy";
  if (/(turkey|ankara)/.test(haystack)) return "Turkey";
  if (/(russia|moscow)/.test(haystack)) return "Russia";
  if (/(lebanon|beirut)/.test(haystack)) return "Lebanon";
  if (/(iran|tehran)/.test(haystack)) return "Iran";
  if (/(israel|gaza|jerusalem)/.test(haystack)) return "Israel";
  if (/(saudi|riyadh)/.test(haystack)) return "Saudi Arabia";
  if (/(opec|oil|crude|gulf|red sea|brent)/.test(haystack)) return "Gulf";
  if (/(india|mumbai|delhi)/.test(haystack)) return "India";
  if (/(china|beijing|shanghai)/.test(haystack)) return "China";
  if (/(taiwan|taipei)/.test(haystack)) return "Taiwan";
  if (/(japan|tokyo)/.test(haystack)) return "Japan";
  if (/(hong kong)/.test(haystack)) return "Hong Kong";
  if (/(korea|seoul)/.test(haystack)) return "South Korea";
  if (/(australia|sydney)/.test(haystack)) return "Australia";
  if (/(washington|new york|wall street|federal reserve)/.test(haystack)) return "US East";
  if (/(california|silicon valley)/.test(haystack)) return "US West";
  return regionKey === "Global" ? "Global" : undefined;
}

function buildHedgeIdeas(event: GeoEvent | null) {
  if (!event) return [];
  const portfolioIdeas = (event.portfolio_exposure?.hedge_candidates || [])
    .filter((item) => item?.ticker)
    .map((item) => ({
      ticker: String(item.ticker).toUpperCase(),
      label: item.label || "Portfolioabsicherung",
    }));
  if (portfolioIdeas.length) return portfolioIdeas.slice(0, 4);

  const ideas = new Map<string, { ticker: string; label: string }>();
  const eventType = (event.event_type || "").toLowerCase();
  const sectors = (event.event_intelligence?.affected_sectors || []).map((item) => item.toLowerCase());
  const assets = (event.event_intelligence?.affected_assets || []).map((item) => item.toUpperCase());
  const action = (event.event_intelligence?.action || "").toLowerCase();

  const add = (ticker: string, label: string) => {
    if (!ticker) return;
    ideas.set(ticker, { ticker, label });
  };

  if (eventType === "conflict" || action === "hedge") {
    add("GLD", "Goldabsicherung");
    add("XLE", "Energiepuffer");
    add("TLT", "Zinsabsicherung");
  }
  if (eventType === "energy" || sectors.some((item) => item.includes("energy"))) {
    add("XLE", "Energieführer");
    add("USO", "Öl-Folgebewegung");
  }
  if (eventType === "central_bank") {
    add("TLT", "Duration beobachten");
    add("UUP", "Dollarabsicherung");
    add("QQQ", "Wachstumsreaktion");
  }
  if (eventType === "election" || eventType === "policy") {
    add("XLI", "Industrie");
    add("ITA", "Verteidigung");
    add("XLF", "Banken");
  }
  if (eventType === "disaster") {
    add("GLD", "Schockabsicherung");
    add("DBA", "Rohstoffstress");
  }
  if (assets.includes("GLD")) add("GLD", "Goldabsicherung");
  if (assets.includes("TLT")) add("TLT", "Durationabsicherung");
  if (assets.includes("XLE")) add("XLE", "Energieabsicherung");
  if (assets.includes("SPY")) add("SPY", "Indexreaktion");

  return Array.from(ideas.values()).slice(0, 4);
}

function tradeImpactActionClass(action?: string) {
  if (action === "long") return "bg-emerald-500/10 text-emerald-700";
  if (action === "short" || action === "watch-short") return "bg-red-500/10 text-red-700";
  if (action === "hedge") return "bg-amber-500/10 text-amber-700";
  if (action === "rebound_or_avoid") return "bg-orange-500/10 text-orange-700";
  return "bg-slate-500/10 text-slate-600";
}

function tradeImpactActionLabel(action?: string) {
  if (action === "long") return "Long nur nach Bestätigung";
  if (action === "short" || action === "watch-short") return "Short-Risiko prüfen";
  if (action === "hedge") return "Risiko zuerst absichern";
  if (action === "rebound_or_avoid") return "Schwache Erholung meiden";
  return "Bestätigung abwarten";
}

function macroConfidenceLabel(score?: number, decisionQuality?: string) {
  const value = Number(score || 0);
  const quality = String(decisionQuality || "").toLowerCase();
  if (value >= 82 && !quality.includes("low") && !quality.includes("weak")) {
    return "Hoch · trotzdem bestätigen";
  }
  if (value >= 62 && !quality.includes("weak")) return "Mittel · zweite Bestätigung";
  return "Niedrig · nur beobachten";
}

function macroSignalStatus(event: GeoEvent | null) {
  const intelligence = event?.event_intelligence;
  const confidence = Number(intelligence?.confidence_score || 0);
  const quality = String(intelligence?.decision_quality || "").toLowerCase();
  const hasDecisionFrame = Boolean(intelligence?.trigger && intelligence?.invalidation);
  if (confidence >= 82 && hasDecisionFrame && !quality.includes("low") && !quality.includes("weak")) {
    return {
      label: "Setup prüfen",
      detail: "Noch kein Trade · Preis und Volumen müssen bestätigen",
      tone: "bg-emerald-500/10 text-emerald-700",
    };
  }
  if (confidence >= 62 && !quality.includes("weak")) {
    return {
      label: "Nur beobachten",
      detail: "Quelle und Marktreaktion weiter bestätigen",
      tone: "bg-amber-500/10 text-amber-700",
    };
  }
  return {
    label: "Blockiert",
    detail: "Quellenlage reicht nicht für eine Entscheidung",
    tone: "bg-red-500/10 text-red-700",
  };
}

function macroHorizonLabel(event: GeoEvent | null) {
  if (!event) return "Zeitraum offen";
  const explicitWindow = String(event.event_intelligence?.execution_window || "").trim();
  if (explicitWindow) return explicitWindow;
  const decay = String(event.event_intelligence?.decay || "").toLowerCase();
  const eventType = String(event.event_type || "").toLowerCase();
  if (decay.includes("fast") || eventType === "central_bank") return "Sofort bis 1 Handelstag";
  if (["conflict", "energy", "election", "policy"].includes(eventType)) return "Heute bis 3 Handelstage";
  return "Mehrere Handelstage prüfen";
}

function exposureToneClass(value?: string) {
  if (value === "high") return "bg-red-500/10 text-red-700";
  if (value === "medium") return "bg-amber-500/10 text-amber-700";
  return "bg-emerald-500/10 text-emerald-700";
}

function freshnessLabel(decay?: string, pulse?: boolean) {
  if (pulse) return "live";
  if (decay === "developing") return "new";
  if (decay === "active") return "active";
  if (decay === "fading") return "fading";
  return "watch";
}

function freshnessClass(label: string) {
  if (label === "live") return "bg-red-500/10 text-red-700";
  if (label === "new") return "bg-emerald-500/10 text-emerald-700";
  if (label === "active") return "bg-blue-500/10 text-blue-700";
  if (label === "fading") return "bg-slate-500/10 text-slate-600";
  return "bg-amber-500/10 text-amber-700";
}

function freshnessDisplayLabel(label: string) {
  if (label === "live") return "Live";
  if (label === "new") return "Neu";
  if (label === "active") return "Aktiv";
  if (label === "fading") return "Abklingend";
  return "Beobachten";
}

function decisionToneClass(value?: string) {
  if (value === "high conviction") return "bg-emerald-500/10 text-emerald-700";
  if (value === "selective") return "bg-sky-500/10 text-sky-700";
  if (value === "tactical only") return "bg-amber-500/10 text-amber-700";
  return "bg-slate-500/10 text-slate-600";
}

function decisionQualityLabel(value?: string) {
  const quality = String(value || "").toLowerCase();
  if (quality === "high conviction") return "Hohe Überzeugung";
  if (quality === "selective") return "Selektiv";
  if (quality === "tactical only") return "Nur taktisch";
  if (quality === "low" || quality === "weak") return "Schwach";
  return normalizeGermanDisplayText(value || "Beobachten");
}

function sectorHeatProfile(sector: string, action?: string) {
  const sectorKey = sector.toLowerCase();
  const longish = action === "long";
  const hedgeish = action === "hedge";
  const shortish = action === "short";

  let level = 52;
  if (/(energy|defense|gold)/.test(sectorKey)) level = hedgeish || longish ? 88 : 68;
  else if (/(airlines|transport|consumer|growth|reits)/.test(sectorKey)) level = shortish ? 82 : 58;
  else if (/(financial|banks|utilities|industrials|semis|autos)/.test(sectorKey)) level = 72;

  const toneClass =
    hedgeish || longish
      ? "bg-emerald-500"
      : shortish
        ? "bg-red-500"
        : "bg-sky-500";

  return { level, toneClass };
}

function stableHash(value: string) {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }
  return hash;
}

function getRegionKey(region?: string) {
  const value = (region || "").toLowerCase();
  if (value === "usa" || value === "us") return "USA";
  if (value === "europe") return "Europe";
  if (value === "asia") return "Asia";
  return "Global";
}

function getRegionNews(news: MapNewsItem[], region: string) {
  const keywords = regionKeywords[region] || [];
  return news.filter((item) => {
    const haystack = `${item.region || ""} ${item.title || ""}`.toLowerCase();
    return keywords.some((keyword) => haystack.includes(keyword));
  });
}

function isRegionFocusMatch(regionLabel: string | undefined, item: GeoEvent) {
  if (!regionLabel) return true;
  return item.regionKey === regionLabel || item.regionKey === "Global";
}

function resolveGeoAnchor(item: MapNewsItem, haystack: string, regionKey: GeoEvent["regionKey"], markerIcon: string): MapAnchor {
  const explicitAnchor = anchorFromGeo(item.geo);
  if (explicitAnchor) return explicitAnchor;
  const matched = geoAnchors.find((entry) => entry.terms.some((term) => haystack.includes(term)));
  if (matched) return matched.anchor;
  if (markerIcon === "OIL") return { left: "55.8%", top: "46.6%" };
  if (markerIcon === "VOTE" && regionKey === "Europe") return { left: "50.5%", top: "36.5%" };
  if (markerIcon === "WAR" && regionKey === "Europe") return { left: "53.4%", top: "34.7%" };
  if (markerIcon === "CB" && regionKey === "USA") return { left: "23%", top: "41.5%" };
  return markerLayout[regionKey];
}

function expandConflictAnchors(item: MapNewsItem, haystack: string): MapAnchor[] {
  const explicitAnchor = anchorFromGeo(item.geo);
  if (explicitAnchor) return [explicitAnchor];
  const orderedMatches = geoAnchors.filter((entry) => entry.terms.some((term) => haystack.includes(term)));
  const unique = new Map<string, MapAnchor>();
  for (const match of orderedMatches) {
    const key = `${match.anchor.left}-${match.anchor.top}`;
    if (!unique.has(key)) unique.set(key, match.anchor);
  }
  return Array.from(unique.values()).slice(0, 3);
}

function classifyGeoEvents(item: MapNewsItem): GeoEvent[] {
  const haystack = `${item.title || ""} ${item.impact || ""} ${item.region || ""} ${item.event_type || ""}`.toLowerCase();
  const regionKey = getRegionKey(item.region);
  const geoZone = item.geo?.country || inferGeoZone(haystack, regionKey);
  const geoPlace = item.geo?.place || inferGeoPlace(haystack, regionKey);
  const pulse = item.impact === "high";

  if (/(war|missile|attack|iran|israel|russia|ukraine|lebanon|beirut|conflict)/.test(haystack)) {
    const anchors = expandConflictAnchors(item, haystack);
    const finalAnchors = anchors.length ? anchors : [resolveGeoAnchor(item, haystack, regionKey, "WAR")];
    return finalAnchors.map((anchor, index) => ({
      ...item,
      geoKey: `${item.title || "conflict"}-${index}`,
      markerLabel: "Konflikt",
      markerTone: "red",
      markerIcon: "WAR",
      pulse,
      geoZone,
      geoPlace,
      regionKey,
      markerPosition: anchor,
    }));
  }
  if (/(fed|ecb|boj|central[_ -]?bank|rate|yield)/.test(haystack)) {
    return [{
      ...item,
      markerLabel: "Zentralbank",
      markerTone: "blue",
      markerIcon: "CB",
      pulse,
      geoZone,
      geoPlace,
      regionKey,
      markerPosition: resolveGeoAnchor(item, haystack, regionKey === "Global" ? "USA" : regionKey, "CB"),
    }];
  }
  if (/(oil|opec|crude|gas|energy)/.test(haystack)) {
    return [{
      ...item,
      markerLabel: "Energie",
      markerTone: "amber",
      markerIcon: "OIL",
      pulse: item.impact !== "low",
      geoZone,
      geoPlace,
      regionKey,
      markerPosition: resolveGeoAnchor(item, haystack, regionKey, "OIL"),
    }];
  }
  if (/(election|vote|ballot|president|prime minister|parliament|coalition|campaign)/.test(haystack)) {
    return [{
      ...item,
      markerLabel: "Wahl",
      markerTone: "blue",
      markerIcon: "VOTE",
      pulse,
      geoZone,
      geoPlace,
      regionKey,
      markerPosition: resolveGeoAnchor(item, haystack, regionKey === "Global" ? "Europe" : regionKey, "VOTE"),
    }];
  }
  if (/(earthquake|wildfire|flood|storm|hurricane|typhoon|tsunami|drought|disaster)/.test(haystack)) {
    return [{
      ...item,
      markerLabel: "Katastrophe",
      markerTone: "red",
      markerIcon: "NAT",
      pulse,
      geoZone,
      geoPlace,
      regionKey,
      markerPosition: resolveGeoAnchor(item, haystack, regionKey === "Global" ? "Asia" : regionKey, "NAT"),
    }];
  }
  if (/(tariff|sanction|trade|policy|regulation)/.test(haystack)) {
    return [{
      ...item,
      markerLabel: "Politik",
      markerTone: "slate",
      markerIcon: "POL",
      pulse,
      geoZone,
      geoPlace,
      regionKey,
      markerPosition: resolveGeoAnchor(item, haystack, regionKey === "Global" ? "USA" : regionKey, "POL"),
    }];
  }
  return [];
}

function buildTimeline(regions: RegionSummary[], activeRegionNews: MapNewsItem[]) {
  const lookup = Object.fromEntries(regions.map((region) => [region.label, region]));
  const order = ["Asia", "Europe", "USA"];
  return order
    .filter((label) => lookup[label])
    .map((label, index) => {
      const region = lookup[label];
      const localNews = activeRegionNews.filter((item) => item.region?.toLowerCase() === label.toLowerCase());
      const driver =
        localNews[0]?.title ||
        region.assets?.[0]?.label ||
        (region.tone === "risk-on"
          ? "buyers in control"
          : region.tone === "risk-off"
            ? "defensive rotation"
            : "cross-asset confirmation needed");
      return {
        key: label,
        stage: index === 0 ? "Asien-Schluss" : index === 1 ? "Europa-Übergang" : "US-Eröffnung",
        label,
        tone: region.tone,
        move: region.avg_change_1d,
        driver,
      };
    });
}

export default function WorldMarketMap({
  regions,
  selectedRegion,
  onSelectRegion,
  dataCurrent = true,
  news = [],
  eventLayer = [],
  eventPings = [],
  watchlistImpact = [],
  contrarianSignals = [],
  openingTimeline = [],
  onAnalyze,
  focusTicker,
}: WorldMarketMapProps) {
  const [activeFilter, setActiveFilter] = useState<EventFilter>("all");
  const [sortMode, setSortMode] = useState<EventSort>("impact");
  const [timeLens, setTimeLens] = useState<TimeLens>("24h");
  const [showLegend, setShowLegend] = useState(false);
  const [showRegionCards, setShowRegionCards] = useState(false);
  const [showLiveAlert, setShowLiveAlert] = useState(true);
  const [showEventLayer, setShowEventLayer] = useState(true);
  const [selectedGeoPlace, setSelectedGeoPlace] = useState<string | null>(null);
  const [pinnedEventIndex, setPinnedEventIndex] = useState(0);
  const [hoveredEventIndex, setHoveredEventIndex] = useState<number | null>(null);
  const [impactDrawerOpen, setImpactDrawerOpen] = useState(false);
  const [mapView, setMapView] = useState<MapViewState>({ zoom: 1, x: 0, y: 0 });
  const [isMapDragging, setIsMapDragging] = useState(false);
  const mapPointerRef = useRef<Map<number, { x: number; y: number }>>(new Map());
  const drawerPreviousFocusRef = useRef<HTMLElement | null>(null);
  const mapDragRef = useRef<{ x: number; y: number; view: MapViewState } | null>(null);
  const mapPinchRef = useRef<{ distance: number; view: MapViewState } | null>(null);
  const mapZoom = mapView.zoom;
  const setMapZoom = useCallback((next: number | ((value: number) => number)) => {
    setMapView((current) => {
      const nextZoom = typeof next === "function" ? next(current.zoom) : next;
      return clampMapView({ ...current, zoom: nextZoom });
    });
  }, []);
  const zoomIntoMap = useCallback(() => {
    setMapZoom((value) => Number((value + 0.32).toFixed(2)));
  }, [setMapZoom]);
  const resetMapView = useCallback(() => {
    setMapView({ zoom: 1, x: 0, y: 0 });
    mapPointerRef.current.clear();
    mapDragRef.current = null;
    mapPinchRef.current = null;
    setIsMapDragging(false);
  }, []);
  const mapContentStyle = useMemo(
    () => ({
      transform: `translate3d(${mapView.x}px, ${mapView.y}px, 0) scale(${mapView.zoom})`,
      cursor: isMapDragging ? "grabbing" : mapView.zoom > 1.01 ? "grab" : "default",
    }),
    [isMapDragging, mapView],
  );
  const mapZoomLabel = `${Math.round(mapZoom * 100)}%`;
  const mapCanvasHandlers = useMemo(() => {
    const pointerDistance = () => {
      const points = [...mapPointerRef.current.values()];
      if (points.length < 2) return 0;
      const [a, b] = points;
      return Math.hypot(a.x - b.x, a.y - b.y);
    };

    return {
      onWheel: (event: React.WheelEvent<HTMLDivElement>) => {
        event.preventDefault();
        const direction = event.deltaY > 0 ? -1 : 1;
        const step = event.ctrlKey ? 0.18 : 0.1;
        setMapZoom((value) => Number((value + direction * step).toFixed(2)));
      },
      onDoubleClick: (event: React.MouseEvent<HTMLDivElement>) => {
        event.preventDefault();
        zoomIntoMap();
      },
      onPointerDown: (event: React.PointerEvent<HTMLDivElement>) => {
        if (event.button !== 0 && event.pointerType === "mouse") return;
        event.currentTarget.setPointerCapture(event.pointerId);
        mapPointerRef.current.set(event.pointerId, { x: event.clientX, y: event.clientY });

        if (mapPointerRef.current.size >= 2) {
          mapPinchRef.current = { distance: pointerDistance(), view: mapView };
          mapDragRef.current = null;
          setIsMapDragging(true);
          return;
        }

        mapDragRef.current = { x: event.clientX, y: event.clientY, view: mapView };
        setIsMapDragging(mapView.zoom > 1.01 || event.pointerType !== "mouse");
      },
      onPointerMove: (event: React.PointerEvent<HTMLDivElement>) => {
        if (!mapPointerRef.current.has(event.pointerId)) return;
        mapPointerRef.current.set(event.pointerId, { x: event.clientX, y: event.clientY });

        if (mapPointerRef.current.size >= 2 && mapPinchRef.current) {
          const distance = pointerDistance();
          if (distance <= 0 || mapPinchRef.current.distance <= 0) return;
          const nextZoom = mapPinchRef.current.view.zoom * (distance / mapPinchRef.current.distance);
          setMapView(clampMapView({ ...mapPinchRef.current.view, zoom: nextZoom }));
          return;
        }

        if (!mapDragRef.current) return;
        const dx = event.clientX - mapDragRef.current.x;
        const dy = event.clientY - mapDragRef.current.y;
        setMapView(clampMapView({
          ...mapDragRef.current.view,
          x: mapDragRef.current.view.x + dx,
          y: mapDragRef.current.view.y + dy,
        }));
      },
      onPointerUp: (event: React.PointerEvent<HTMLDivElement>) => {
        mapPointerRef.current.delete(event.pointerId);
        mapDragRef.current = null;
        mapPinchRef.current = null;
        setIsMapDragging(false);
      },
      onPointerCancel: (event: React.PointerEvent<HTMLDivElement>) => {
        mapPointerRef.current.delete(event.pointerId);
        mapDragRef.current = null;
        mapPinchRef.current = null;
        setIsMapDragging(false);
      },
    };
  }, [mapView, setMapZoom, zoomIntoMap]);
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") resetMapView();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [resetMapView]);
  useEffect(() => {
    if (!impactDrawerOpen) return;
    drawerPreviousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusFrame = window.requestAnimationFrame(() => {
      document.querySelector<HTMLElement>("#map-impact-dialog button")?.focus();
    });
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setImpactDrawerOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      window.removeEventListener("keydown", closeOnEscape);
      document.body.style.overflow = previousOverflow;
      drawerPreviousFocusRef.current?.focus();
    };
  }, [impactDrawerOpen]);
  const activeRegion =
    regions.find((region) => region.label === selectedRegion) || regions[0] || null;
  const displayRegion = activeRegion;

  const activeRegionNews = useMemo(
    () => (activeRegion ? getRegionNews(news, activeRegion.label).slice(0, 4) : []),
    [activeRegion, news],
  );

  const normalizedPingLayer = useMemo<MapNewsItem[]>(
    () =>
      (eventPings || []).map((ping) => {
        const type = String(ping.type || "macro").toLowerCase();
        const severity = String(ping.severity || "normal").toLowerCase();
        const impact =
          severity === "critical" ? "high" : severity === "elevated" ? "medium" : "low";
        const eventTypeMap: Record<string, string> = {
          war: "conflict",
          conflict: "conflict",
          cb: "central_bank",
          central_bank: "central_bank",
          oil: "energy",
          energy: "energy",
          vote: "election",
          election: "election",
          nat: "disaster",
          disaster: "disaster",
          pol: "policy",
          policy: "policy",
        };
        const event_type = eventTypeMap[type] || type || "macro";
        const symbols = Array.isArray(ping.symbols) ? ping.symbols.filter(Boolean) : [];
        const tradeImpact = ping.trade_impact || {};
        return {
          title: ping.title || `${event_type.replace("_", " ")} signal`,
          region: ping.region || "global",
          impact,
          event_type,
          severity,
          ticker: symbols[0],
          publisher: "Event Ping",
          map_priority: severity === "critical" ? 10 : severity === "elevated" ? 20 : 40,
          event_intelligence: {
            impact_score: severity === "critical" ? 90 : severity === "elevated" ? 74 : 58,
            confidence_score: Number.isFinite(Number(ping.confidence)) ? Number(ping.confidence) : 60,
            decay: "developing",
            affected_assets: Array.isArray(tradeImpact.symbols) && tradeImpact.symbols.length ? tradeImpact.symbols : symbols,
            action: tradeImpact.action || "watch",
            leverage: "avoid",
            trigger: tradeImpact.trigger || "Erste Marktreaktion nach der Eröffnung beobachten.",
            invalidation: tradeImpact.invalidation || "Das Signal ist ungültig, wenn sich die erste Bewegung vollständig umkehrt.",
            execution_window: tradeImpact.window || "open+60m",
            why_now: tradeImpact.baseline_scenario || "Der Makro-Katalysator ist aktiv.",
          },
          portfolio_exposure: tradeImpact.hedge_idea
            ? {
                status: "watch",
                note: `Absicherungsidee: ${tradeImpact.hedge_idea}`,
                action: "hedge",
                exposure_strength: "medium",
              }
            : undefined,
        };
      }),
    [eventPings],
  );

  const geoSignals = useMemo(
    () =>
      ((eventLayer.length ? [...eventLayer, ...normalizedPingLayer] : [...news, ...normalizedPingLayer]))
        .flatMap(classifyGeoEvents)
        .filter((item) => item!.impact === "high" || item!.impact === "medium")
        .sort((a, b) => {
          const impactRank = { high: 0, medium: 1, low: 2 };
          return (impactRank[a!.impact as keyof typeof impactRank] ?? 3) - (impactRank[b!.impact as keyof typeof impactRank] ?? 3);
        })
        .slice(0, 12) as GeoEvent[],
    [eventLayer, news, normalizedPingLayer],
  );

  const filteredGeoSignals = useMemo(
    () =>
      geoSignals.filter((item) => {
        const filterMatch = activeFilter === "all" ? true : item.markerIcon === activeFilter;
        if (!filterMatch) return false;
        if (timeLens === "7d") return true;
        if (timeLens === "24h") return item.event_intelligence?.decay !== "fading";
        return item.pulse || item.event_intelligence?.decay === "developing";
      }),
    [geoSignals, activeFilter, timeLens],
  );

  const orderedGeoSignals = useMemo(() => {
    const impactRank = { high: 0, medium: 1, low: 2 } as const;
    const items = [...filteredGeoSignals];
    if (sortMode === "region") {
      items.sort((a, b) => {
        const regionCompare = (a.region || "").localeCompare(b.region || "");
        if (regionCompare !== 0) return regionCompare;
        return (impactRank[a.impact as keyof typeof impactRank] ?? 3) - (impactRank[b.impact as keyof typeof impactRank] ?? 3);
      });
      return items;
    }
    if (sortMode === "latest") {
      return items.reverse();
    }
    items.sort(
      (a, b) => {
        const priorityDelta = (a.map_priority ?? 999) - (b.map_priority ?? 999);
        if (priorityDelta !== 0) return priorityDelta;
        return (
          (impactRank[a.impact as keyof typeof impactRank] ?? 3) -
          (impactRank[b.impact as keyof typeof impactRank] ?? 3)
        );
      },
    );
    return items;
  }, [filteredGeoSignals, sortMode]);

  const focusRegionSignals = useMemo(
    () => orderedGeoSignals.filter((item) => isRegionFocusMatch(activeRegion?.label, item)),
    [orderedGeoSignals, activeRegion],
  );

  const focusedPlaceSignals = useMemo(
    () =>
      selectedGeoPlace
        ? focusRegionSignals.filter((item) => item.geoPlace === selectedGeoPlace)
        : focusRegionSignals,
    [focusRegionSignals, selectedGeoPlace],
  );

  const positionedGeoSignals = useMemo(() => {
    const orbitOffsets = [
      { x: 0, y: 0 },
      { x: 10, y: -8 },
      { x: -10, y: -8 },
      { x: 14, y: 10 },
      { x: -14, y: 10 },
      { x: 0, y: 15 },
      { x: 18, y: 0 },
      { x: -18, y: 0 },
    ];
    const collisionBuckets = new Map<string, number>();
    return orderedGeoSignals.map((item) => {
      const baseOffset = markerOffsets[item.regionKey]?.[item.markerIcon] || { x: 0, y: 0 };
      const bucketKey = `${item.markerPosition.left}|${item.markerPosition.top}`;
      const bucketIndex = collisionBuckets.get(bucketKey) || 0;
      collisionBuckets.set(bucketKey, bucketIndex + 1);
      const hash = stableHash(`${item.geoKey || item.title || item.markerIcon}-${bucketIndex}`);
      const orbit = orbitOffsets[(hash + bucketIndex) % orbitOffsets.length];
      const stackLift = Math.floor(bucketIndex / orbitOffsets.length) * 12;
      return {
        ...item,
        adjustedStyle: {
          left: `clamp(2rem, calc(${item.markerPosition.left} + ${baseOffset.x + orbit.x}px), calc(100% - 4rem))`,
          top: `clamp(2rem, calc(${item.markerPosition.top} + ${baseOffset.y + orbit.y + stackLift}px), calc(100% - 3rem))`,
        },
      };
    });
  }, [orderedGeoSignals]);

  const timeline = useMemo(
    () => (openingTimeline.length ? openingTimeline : buildTimeline(regions, news)),
    [openingTimeline, regions, news],
  );

  const regionalContrarian = useMemo(
    () =>
      contrarianSignals.filter((item) =>
        activeRegion ? (item.region || "").toLowerCase() === activeRegion.label.toLowerCase() : true,
      ),
    [contrarianSignals, activeRegion],
  );

  const activePulseEvent = useMemo(
    () => focusRegionSignals.find((item) => item.pulse) || positionedGeoSignals.find((item) => item.pulse) || null,
    [focusRegionSignals, positionedGeoSignals],
  );

  useEffect(() => {
    if (!positionedGeoSignals.length) {
      setPinnedEventIndex(0);
      setHoveredEventIndex(null);
      return;
    }
    if (pinnedEventIndex >= positionedGeoSignals.length) {
      setPinnedEventIndex(0);
    }
    if (hoveredEventIndex != null && hoveredEventIndex >= positionedGeoSignals.length) {
      setHoveredEventIndex(null);
    }
  }, [hoveredEventIndex, pinnedEventIndex, positionedGeoSignals]);

  useEffect(() => {
    if (!selectedGeoPlace) return;
    const stillExists = focusRegionSignals.some((item) => item.geoPlace === selectedGeoPlace);
    if (!stillExists) {
      setSelectedGeoPlace(null);
    }
  }, [focusRegionSignals, selectedGeoPlace]);

  const eventTempo = useMemo(() => {
    const stats = { developing: 0, active: 0, fading: 0 };
    for (const item of positionedGeoSignals) {
      const decay = item.event_intelligence?.decay;
      if (decay === "developing") stats.developing += 1;
      else if (decay === "fading") stats.fading += 1;
      else stats.active += 1;
    }
    return stats;
  }, [positionedGeoSignals]);

  const mapSignalSummary = useMemo(() => {
    const highImpact = positionedGeoSignals.filter((item) => item.impact === "high").length;
    const actionable = positionedGeoSignals.filter((item) => {
      const action = item.event_intelligence?.action;
      return action && action !== "watch";
    }).length;
    return {
      total: positionedGeoSignals.length,
      highImpact,
      actionable,
    };
  }, [positionedGeoSignals]);

  const visibleEventLayerSignals = useMemo(
    () =>
      selectedGeoPlace
        ? positionedGeoSignals.filter((item) => item.geoPlace === selectedGeoPlace)
        : positionedGeoSignals,
    [positionedGeoSignals, selectedGeoPlace],
  );

  const countryHighlights = useMemo(
    () => buildCountryHighlights(visibleEventLayerSignals.length ? visibleEventLayerSignals : positionedGeoSignals),
    [positionedGeoSignals, visibleEventLayerSignals],
  );

  const activeGeoEvent = useMemo(
    () =>
      (hoveredEventIndex != null ? positionedGeoSignals[hoveredEventIndex] : null) ||
      positionedGeoSignals[pinnedEventIndex] ||
      focusedPlaceSignals[0] ||
      focusRegionSignals[0] ||
      positionedGeoSignals[0] ||
      activePulseEvent ||
      null,
    [activePulseEvent, hoveredEventIndex, pinnedEventIndex, positionedGeoSignals, focusedPlaceSignals, focusRegionSignals],
  );

  const hedgeIdeas = useMemo(
    () => buildHedgeIdeas(activeGeoEvent),
    [activeGeoEvent],
  );

  const tradeImpactAssets = useMemo(
    () => compactList(activeGeoEvent?.event_intelligence?.affected_assets, 4),
    [activeGeoEvent],
  );

  const tradeImpactCards = useMemo(() => {
    if (!activeGeoEvent?.event_intelligence) return [];
    const intelligence = activeGeoEvent.event_intelligence;
    const signalStatus = macroSignalStatus(activeGeoEvent);
    return [
      {
        label: "Signalstatus",
        value: `${signalStatus.label} · ${signalStatus.detail}`,
        tone: signalStatus.tone,
      },
      {
        label: "Handlung",
        value: tradeImpactActionLabel(intelligence.action),
        tone: tradeImpactActionClass(intelligence.action),
      },
      {
        label: "Zeithorizont",
        value: macroHorizonLabel(activeGeoEvent),
        tone: "bg-sky-500/10 text-sky-700",
      },
      {
        label: "Belastbarkeit",
        value: macroConfidenceLabel(intelligence.confidence_score, intelligence.decision_quality),
        tone: "bg-slate-500/10 text-slate-600",
      },
    ];
  }, [activeGeoEvent]);

  const activeVariantLabel = useMemo(
    () => describeEventVariant(activeGeoEvent),
    [activeGeoEvent],
  );

  const macroDecisionFacts = useMemo(() => {
    if (!activeGeoEvent) return [];
    const intelligence = activeGeoEvent.event_intelligence || {};
    const signalStatus = macroSignalStatus(activeGeoEvent);
    return [
      {
        label: "Status",
        value: `${signalStatus.label} · ${signalStatus.detail}`,
      },
      {
        label: "Ereignis",
        value: activeVariantLabel || activeGeoEvent.markerLabel || activeGeoEvent.event_type || "Makro-Ereignis",
      },
      {
        label: "Region / Wirkung",
        value: `${activeGeoEvent.geoPlace || activeGeoEvent.geoZone || activeGeoEvent.region || "Global"} · ${
          intelligence.impact_score ? `${intelligence.impact_score}/100` : activeGeoEvent.impact || "beobachten"
        }`,
      },
      {
        label: "Assets",
        value: compactList(intelligence.affected_assets, 3).join(" | ") || activeGeoEvent.ticker || "Marktkorb",
      },
      {
        label: "Trigger",
        value: normalizeGermanDisplayText(intelligence.trigger || "Bestätigung und Preisreaktion abwarten."),
      },
      {
        label: "Invalidierung",
        value: normalizeGermanDisplayText(intelligence.invalidation || "Die These fällt, wenn Meldung oder Preisreaktion nicht bestätigt werden."),
      },
    ];
  }, [activeGeoEvent, activeVariantLabel]);

  useEffect(() => {
    if (!activeGeoEvent) {
      setImpactDrawerOpen(false);
    }
  }, [activeGeoEvent]);

  const whyItMatters = useMemo(() => {
    const lines: string[] = [];
    const relevantEvent =
      activeGeoEvent ||
      positionedGeoSignals.find((item) =>
        activeRegion ? item.regionKey.toLowerCase() === activeRegion.label.toLowerCase() || item.regionKey === "Global" : true,
      );
    if (relevantEvent?.title) lines.push(`${relevantEvent.markerLabel}: ${relevantEvent.title}`);
    if (relevantEvent?.event_intelligence?.why_now) {
      lines.push(`Warum jetzt: ${relevantEvent.event_intelligence.why_now}`);
    }
    if (activeRegionNews[0]?.title) lines.push(`Regionaler Treiber: ${activeRegionNews[0].title}`);
    if (focusTicker) {
      const impacted = watchlistImpact.find((item) => (item.ticker || "").toUpperCase() === focusTicker.toUpperCase());
      if (impacted?.summary) {
        lines.push(`${focusTicker}: ${impacted.summary}`);
      } else if (activeRegion?.assets?.some((asset) => asset.ticker?.toUpperCase() === focusTicker.toUpperCase())) {
        lines.push(`${focusTicker}: direkt mit ${regionDisplayLabel(activeRegion.label)} verknüpft und damit dem aktiven Makroblock ausgesetzt.`);
      }
    }
    if (regionalContrarian[0]?.ticker && regionalContrarian[0]?.reason) {
      lines.push(`Gegenläufiges Setup: ${regionalContrarian[0].ticker} | ${regionalContrarian[0].reason}`);
    }
    return lines.slice(0, 4);
  }, [activeGeoEvent, positionedGeoSignals, activeRegion, activeRegionNews, focusTicker, watchlistImpact, regionalContrarian]);

  const replayEvents = useMemo(
    () =>
      orderedGeoSignals.slice(0, 6).map((item, index) => ({
        key: item.geoKey || `${item.title}-${index}`,
        title: item.title,
        region: item.region || "Global",
        geoZone: item.geoZone,
        geoPlace: item.geoPlace,
        variant: describeEventVariant(item) || item.markerLabel,
        freshness: freshnessLabel(item.event_intelligence?.decay, item.pulse),
        impact: item.impact || "macro",
        action: item.event_intelligence?.action || "watch",
        asset: compactList(item.event_intelligence?.affected_assets, 1)[0] || item.ticker,
        trigger: item.event_intelligence?.trigger,
      })),
    [orderedGeoSignals],
  );

  const regionDrilldown = useMemo(() => {
    const items = focusedPlaceSignals.slice(0, 4);
    const actionable = items.filter((item) => item.event_intelligence?.action && item.event_intelligence.action !== "watch").length;
    const highImpact = items.filter((item) => item.impact === "high").length;
    const zones = topGeoZones(focusRegionSignals, 4);
    const places = topGeoPlaces(focusRegionSignals, 5);
    const placeHeat = buildPlaceHeat(focusRegionSignals);
    const eventMix = eventTypeBreakdown(focusedPlaceSignals);
    const placeStack = buildPlaceVariantStack(focusedPlaceSignals);
    return {
      total: items.length,
      actionable,
      highImpact,
      items,
      zones,
      places,
      placeHeat,
      eventMix,
      placeStack,
    };
  }, [focusRegionSignals, focusedPlaceSignals]);

  const mapRegionCards = useMemo(
    () =>
      regions
        .filter((region) => Boolean(positions[region.label]))
        .map((region) => {
          const pos = positions[region.label];
          const leadAsset = (region.assets || [])[0];
          return {
            label: region.label,
            top: `calc(${pos.y}% - 4.8rem)`,
            left: `calc(${pos.x}% - 1.2rem)`,
            avgChange: dataCurrent ? formatPct(region.avg_change_1d) : "—",
            assetLabel: leadAsset?.label || "Macro basket",
            assetTicker: leadAsset?.ticker || "MIX",
            tone: region.tone,
          };
        }),
    [dataCurrent, regions],
  );

  return (
    <section className="surface-panel world-market-map relative overflow-hidden rounded-[2.5rem] p-5 sm:p-8">

      <div className="relative space-y-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="text-[11px] font-extrabold uppercase tracking-[0.24em] text-slate-500">
                Weltmarktkarte
              </div>
              <span
                role="status"
                aria-label={dataCurrent ? "Aktuelle Regionaldaten" : "Ersatzansicht ohne aktuelle Regionaldaten"}
                className={`rounded-full border px-2.5 py-1 text-[9px] font-extrabold uppercase tracking-[0.14em] ${
                  dataCurrent
                    ? "border-emerald-500/15 bg-emerald-500/8 text-emerald-700"
                    : "border-amber-500/20 bg-amber-500/10 text-amber-800"
                }`}
              >
                {dataCurrent ? "Regionaldaten aktuell" : "Ersatzansicht · Werte ausstehend"}
              </span>
            </div>
            <h3 className="mt-2 text-3xl text-slate-900 sm:text-4xl">Globale Marktbewegungen über Nacht</h3>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600">
              Regionen, Makro-Ton, geopolitische Ereignisse und der Übergang bis zur US-Eröffnung
              in einer kompakten Makro-Ansicht.
            </p>
          </div>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Weltmarktregion auswählen">
            {regions.map((region) => (
              <button
                key={region.label}
                type="button"
                onClick={() => onSelectRegion(region.label)}
                aria-pressed={selectedRegion === region.label}
                aria-label={`${regionDisplayLabel(region.label)} auswählen`}
                className={`min-h-10 rounded-full px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] transition-all ${
                  selectedRegion === region.label
                    ? "bg-[var(--accent)] text-white shadow-[0_16px_34px_rgba(15,118,110,0.18)]"
                    : "border border-black/8 bg-white/70 text-slate-500"
                }`}
              >
                {regionDisplayLabel(region.label)}
              </button>
            ))}
          </div>
        </div>

        <div className="map-filter-strip flex flex-nowrap items-center gap-2 overflow-x-auto pb-1 no-scrollbar sm:flex-wrap sm:overflow-visible sm:pb-0" role="group" aria-label="Ereignistyp filtern" tabIndex={0}>
          {[
            { key: "all", label: "Alle" },
            { key: "WAR", label: "Krieg" },
            { key: "VOTE", label: "Wahlen" },
            { key: "OIL", label: "Öl" },
            { key: "CB", label: "Zentralbank" },
            { key: "NAT", label: "Katastrophe" },
            { key: "POL", label: "Politik" },
          ].map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setActiveFilter(item.key as EventFilter)}
              aria-pressed={activeFilter === item.key}
              className={`min-h-10 shrink-0 rounded-full px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] transition-all ${
                activeFilter === item.key
                  ? "bg-[#101114] text-white shadow-[0_10px_24px_rgba(15,23,42,0.12)]"
                  : "border border-black/8 bg-white/70 text-slate-500"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="flex flex-col gap-2 rounded-[1.2rem] border border-black/8 bg-white/70 px-3 py-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between sm:gap-3">
          <div className="map-control-strip flex w-full flex-nowrap items-center gap-2 overflow-x-auto pb-1 no-scrollbar sm:w-auto sm:flex-wrap sm:overflow-visible sm:pb-0" role="group" aria-label="Ereignisse sortieren" tabIndex={0}>
            <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
              Sortierung
            </div>
            {[ 
              { key: "impact", label: "Wirkung" },
              { key: "region", label: "Region" },
              { key: "latest", label: "Neueste" },
            ].map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => setSortMode(item.key as EventSort)}
                aria-pressed={sortMode === item.key}
                className={`min-h-10 shrink-0 rounded-full px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] transition-all ${
                  sortMode === item.key
                    ? "bg-[var(--accent)] text-white"
                    : "border border-black/8 bg-white text-slate-500"
                }`}
              >
                {item.label}
              </button>
            ))}
            <span className="ml-1 rounded-full border border-black/8 bg-white px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
              {mapSignalSummary.total} Ereignisse
            </span>
            <span className="rounded-full border border-red-500/12 bg-red-500/6 px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] text-red-700">
              {mapSignalSummary.highImpact} hoch
            </span>
            <span className="rounded-full border border-emerald-500/12 bg-emerald-500/6 px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] text-emerald-700">
              {mapSignalSummary.actionable} aktive Setups
            </span>
          </div>
          <div className="map-control-strip flex w-full flex-nowrap items-center gap-2 overflow-x-auto pb-1 no-scrollbar sm:w-auto sm:flex-wrap sm:overflow-visible sm:pb-0" role="group" aria-label="Kartenzeitraum und Ebenen" tabIndex={0}>
            <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
              Zeitraum
            </div>
            {[
              { key: "live", label: "Live" },
              { key: "24h", label: "24h" },
              { key: "7d", label: "7d" },
            ].map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => setTimeLens(item.key as TimeLens)}
                aria-pressed={timeLens === item.key}
                className={`min-h-10 shrink-0 rounded-full px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] transition-all ${
                  timeLens === item.key
                    ? "bg-[var(--accent)] text-white"
                    : "border border-black/8 bg-white text-slate-500"
                }`}
              >
                {item.label}
              </button>
            ))}
            {[
              { key: "legend", label: "Legende", value: showLegend, set: setShowLegend },
              { key: "regions", label: "Regionen", value: showRegionCards, set: setShowRegionCards },
              { key: "alert", label: "Live-Alarm", value: showLiveAlert, set: setShowLiveAlert },
              { key: "layer", label: "Ereignisebene", value: showEventLayer, set: setShowEventLayer },
            ].map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => item.set(!item.value)}
                aria-pressed={item.value}
                className={`min-h-10 shrink-0 rounded-full px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] transition-all ${
                  item.value
                    ? "bg-[#101114] text-white"
                    : "border border-black/8 bg-white text-slate-500"
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        <div className="world-map-mobile-card sm:hidden rounded-[1.45rem] border border-black/8 bg-white/78 p-3 shadow-[0_18px_40px_rgba(15,23,42,0.08)]">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-[10px] font-extrabold uppercase tracking-[0.2em] text-slate-500">
                Weltkarte
              </div>
              <div className="mt-1 text-base font-black text-slate-900">
                Ereignisse und Marktwirkung
              </div>
            </div>
            <button
              type="button"
              onClick={() => setImpactDrawerOpen(true)}
              className="shrink-0 rounded-full border border-black/8 bg-white px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.14em] text-[var(--accent)]"
            >
              {mapSignalSummary.total} Hinweise
            </button>
          </div>

          <div
            className="world-map-canvas interactive-world-map relative mt-3 h-[220px] overflow-hidden rounded-[1.15rem] border border-black/6 bg-[#f5f5f7] dark:bg-[#121214] min-[430px]:h-[246px]"
            {...mapCanvasHandlers}
          >
            <div className="world-map-glow absolute inset-0 bg-gradient-to-b from-white/60 to-transparent dark:from-white/5 dark:to-transparent" />
            <div className="world-map-interactive-layer absolute inset-0" style={mapContentStyle}>
              <InlineWorldMap highlights={countryHighlights} />
              {showEventLayer && positionedGeoSignals.slice(0, 12).map((item, index) => (
                <button
                  key={item.geoKey || `${item.title}-${index}`}
                  type="button"
                  onPointerDown={(event) => event.stopPropagation()}
                  onClick={() => {
                    setPinnedEventIndex(index);
                    setImpactDrawerOpen(true);
                  }}
                  className={`absolute z-10 -translate-x-1/2 -translate-y-1/2 rounded-full border px-2 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.12em] shadow-[0_12px_28px_rgba(15,23,42,0.18)] ${markerClass(
                    item.markerTone,
                  )} ${pinnedEventIndex === index ? "ring-2 ring-white/90" : ""}`}
                  style={item.adjustedStyle}
                  aria-label={`${item.title} öffnen`}
                >
                  {item.pulse ? (
                    <span
                      className={`absolute inset-0 rounded-full opacity-25 blur-sm ${markerAccentClass(
                        item.markerTone,
                      )} animate-ping`}
                    />
                  ) : null}
                  <span className="relative inline-flex items-center gap-1">
                    <span className={`h-2 w-2 rounded-full ${markerAccentClass(item.markerTone)}`} />
                    {item.markerIcon}
                  </span>
                </button>
              ))}
            </div>
            <div className="world-map-zoom-controls absolute right-2 top-2 z-30 flex gap-1 rounded-full border border-black/8 bg-white/90 p-1 shadow-[0_10px_24px_rgba(15,23,42,0.1)]">
              {[
                { label: "-", action: () => setMapZoom((value) => Number((value - 0.18).toFixed(2))) },
                { label: "1x", action: resetMapView },
                { label: "+", action: () => setMapZoom((value) => Number((value + 0.18).toFixed(2))) },
              ].map((item) => (
                <button
                  key={item.label}
                  type="button"
                  onPointerDown={(event) => event.stopPropagation()}
                  onClick={item.action}
                  className="h-8 min-w-8 rounded-full px-2 text-[10px] font-black text-slate-600 transition-colors hover:bg-[var(--accent-soft)] hover:text-[var(--accent)]"
                  aria-label={`Kartenzoom ${item.label}`}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <div className="world-map-gesture-hint absolute bottom-2 left-2 z-30 rounded-full border border-black/8 bg-white/88 px-2.5 py-1 text-[9px] font-extrabold uppercase tracking-[0.12em] text-slate-500 shadow-[0_8px_18px_rgba(15,23,42,0.08)]">
              Ziehen / Pinch / {mapZoomLabel}
            </div>

            {!positionedGeoSignals.length ? (
              <div className="absolute inset-x-4 top-1/2 -translate-y-1/2 rounded-[1rem] border border-black/8 bg-white/88 p-3 text-center text-xs font-semibold text-slate-600">
                Keine priorisierten Event-Pings im aktuellen Filter.
              </div>
            ) : null}
          </div>

          {visibleEventLayerSignals.length ? (
            <div className="mt-3 grid gap-2">
              {visibleEventLayerSignals.slice(0, 3).map((item, index) => (
                <button
                  key={`mobile-top-${item.geoKey || item.title || index}`}
                  type="button"
                  onClick={() => {
                    const nextIndex = positionedGeoSignals.findIndex((candidate) => candidate.geoKey === item.geoKey);
                    setPinnedEventIndex(Math.max(0, nextIndex));
                    setImpactDrawerOpen(true);
                  }}
                  className="rounded-[1rem] border border-black/8 bg-white/88 p-3 text-left"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.14em] ${markerClass(item.markerTone)}`}>
                      <span className={`h-2 w-2 rounded-full ${markerAccentClass(item.markerTone)}`} />
                      {item.markerIcon}
                    </span>
                    <span className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-400">
                      Wirkung {item.event_intelligence?.impact_score || item.impact || "beobachten"}
                    </span>
                  </div>
                  <div className="mt-2 line-clamp-2 text-sm font-black text-slate-900">{item.title}</div>
                  <div className="mt-1 text-xs font-semibold text-slate-500">
                    {item.geoPlace || item.geoZone || item.region || "Global"} / {item.event_intelligence?.action || "watch"}
                  </div>
                </button>
              ))}
            </div>
          ) : null}

          <div className="mt-3 grid grid-cols-3 gap-2">
            {regions.map((region) => (
              <button
                key={region.label}
                type="button"
                onClick={() => onSelectRegion(region.label)}
                className={`min-w-0 rounded-[0.9rem] border px-1.5 py-2 text-center transition-all ${
                  selectedRegion === region.label
                    ? "border-[var(--accent)]/25 bg-[var(--accent-soft)] text-[var(--accent)]"
                    : "border-black/8 bg-white text-slate-600"
                }`}
              >
                <span className="block truncate text-[9px] font-extrabold uppercase tracking-[0.1em]">
                  {regionFlag(region.label)} {regionDisplayLabel(region.label)}
                </span>
                <span className="mt-0.5 block text-[10px] font-black">
                  {dataCurrent ? formatPct(region.avg_change_1d) : "—"}
                </span>
              </button>
            ))}
          </div>

          {activeGeoEvent ? (
            <button
              type="button"
              onClick={() => setImpactDrawerOpen(true)}
              className="mt-3 block w-full rounded-[1.05rem] border border-black/8 bg-white/88 p-3 text-left"
            >
              <div className="flex items-center justify-between gap-2">
                <span
                  className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.14em] ${markerClass(
                    activeGeoEvent.markerTone,
                  )}`}
                >
                  <span className={`h-2 w-2 rounded-full ${markerAccentClass(activeGeoEvent.markerTone)}`} />
                  {activeGeoEvent.markerIcon}
                </span>
                <span className="text-[9px] font-extrabold uppercase tracking-[0.16em] text-slate-400">
                  Handelswirkung
                </span>
              </div>
              <div className="mt-2 line-clamp-2 text-sm font-black text-slate-900">
                {activeGeoEvent.title}
              </div>
              <div className="mt-1 text-xs font-semibold text-slate-500">
                {activeGeoEvent.region || "Global"} / {activeGeoEvent.event_intelligence?.action || "watch"}
              </div>
              {macroDecisionFacts.length ? (
                <div className="mt-3 grid gap-2">
                  {macroDecisionFacts.slice(0, 4).map((fact) => (
                    <div key={fact.label} className="rounded-[0.85rem] border border-black/8 bg-white/78 px-3 py-2">
                      <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-400">
                        {fact.label}
                      </div>
                      <div className="mt-1 line-clamp-2 text-[11px] font-bold leading-4 text-slate-700">
                        {fact.value}
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
            </button>
          ) : null}
        </div>

        <div className="hidden items-start gap-5 sm:grid xl:items-start xl:grid-cols-[1.3fr_0.7fr]">
          <div className="world-map-shell relative hidden h-fit overflow-hidden rounded-[2rem] border border-black/8 bg-[#eaf0f6] p-4 sm:block sm:p-5">
            <div
              className="world-map-canvas interactive-world-map relative w-full min-h-[260px] max-h-[min(76vh,760px)] [aspect-ratio:16/8.6] overflow-hidden rounded-[1.4rem] border border-black/6 bg-[#f5f5f7] dark:bg-[#121214] sm:min-h-[320px] xl:min-h-[430px]"
              {...mapCanvasHandlers}
            >
            <div className="absolute inset-0 rounded-[1.4rem] opacity-95">
              <div className="world-map-glow absolute inset-0 bg-gradient-to-b from-white/60 to-transparent dark:from-white/5 dark:to-transparent" />
              <div className="world-map-interactive-layer absolute inset-0" style={mapContentStyle}>
                <InlineWorldMap highlights={countryHighlights} />
              </div>
            </div>

            <div className="absolute left-4 top-4 z-30 hidden w-12 flex-col items-center gap-2 rounded-[1rem] border border-black/8 bg-white/92 p-2 shadow-[0_14px_30px_rgba(15,23,42,0.12)] md:flex">
              {[
                { key: "regions", label: "Regionenkarten", value: showRegionCards, set: setShowRegionCards, Icon: MapPinned },
                { key: "legend", label: "Legende", value: showLegend, set: setShowLegend, Icon: ListFilter },
                { key: "events", label: "Ereignisebene", value: showEventLayer, set: setShowEventLayer, Icon: Layers3 },
                { key: "alert", label: "Live-Alarm", value: showLiveAlert, set: setShowLiveAlert, Icon: Bell },
              ].map((item) => (
                <button
                  key={item.key}
                  type="button"
                  onPointerDown={(event) => event.stopPropagation()}
                  onClick={() => item.set(!item.value)}
                  aria-label={item.label}
                  aria-pressed={item.value}
                  title={item.label}
                  className={`flex h-8 w-8 items-center justify-center rounded-[0.7rem] border text-slate-500 transition-colors hover:bg-[var(--accent-soft)] hover:text-[var(--accent)] ${
                    item.value ? "border-[var(--accent)]/25 bg-[var(--accent-soft)] text-[var(--accent)]" : "border-black/8 bg-white"
                  }`}
                >
                  <item.Icon size={15} aria-hidden="true" />
                </button>
              ))}
            </div>

            <div className="world-map-zoom-controls absolute right-4 top-4 z-30 hidden w-12 flex-col items-center gap-2 rounded-[1rem] border border-black/8 bg-white/92 p-2 shadow-[0_14px_30px_rgba(15,23,42,0.12)] md:flex">
              {[
                { label: "+", action: () => setMapZoom((value) => Number((value + 0.18).toFixed(2))) },
                { label: "-", action: () => setMapZoom((value) => Number((value - 0.18).toFixed(2))) },
                { label: "1x", action: resetMapView },
              ].map((item) => (
                <button
                  key={item.label}
                  type="button"
                  onPointerDown={(event) => event.stopPropagation()}
                  onClick={item.action}
                  className="h-8 w-8 rounded-[0.7rem] border border-black/8 bg-white text-[11px] font-black uppercase tracking-[0.14em] text-slate-500 transition-colors hover:bg-[var(--accent-soft)] hover:text-[var(--accent)]"
                  aria-label={`Kartenzoom ${item.label}`}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <div className="world-map-gesture-hint absolute bottom-4 left-4 z-30 hidden rounded-full border border-black/8 bg-white/90 px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500 shadow-[0_10px_24px_rgba(15,23,42,0.1)] md:block">
              Rad zoomt / ziehen bewegt / Esc reset / {mapZoomLabel}
            </div>

            {showRegionCards
              ? mapRegionCards.map((card) => (
                  <button
                    key={card.label}
                    type="button"
                    onClick={() => onSelectRegion(card.label)}
                    className="absolute z-20 hidden min-w-[160px] rounded-[0.95rem] border border-black/8 bg-white/95 px-3 py-2 text-left shadow-[0_16px_36px_rgba(15,23,42,0.14)] transition-all hover:-translate-y-[1px] md:block"
                    style={{ left: card.left, top: card.top }}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className={`inline-flex h-6 min-w-[1.8rem] items-center justify-center rounded-[0.45rem] px-1 text-[9px] font-black text-white ${regionBadgeColor(card.label)}`}>
                          {regionFlag(card.label)}
                        </span>
                        <div className="text-[11px] font-extrabold uppercase tracking-[0.14em] text-slate-700">
                          {regionDisplayLabel(card.label)}
                        </div>
                      </div>
                      <span className={`text-[11px] font-black ${textToneClass(card.tone)}`}>
                        {card.avgChange}
                      </span>
                    </div>
                    <div className="mt-1 text-[10px] font-bold text-slate-600">
                      {card.assetTicker} · {card.assetLabel}
                    </div>
                  </button>
                ))
              : null}

            {showLegend ? (
            <div className="absolute bottom-4 left-4 z-30 hidden max-w-[20rem] flex-wrap gap-2 rounded-[1rem] border border-black/8 bg-white/92 px-3 py-2 shadow-[0_10px_24px_rgba(15,23,42,0.08)] sm:flex">
              {[
                { icon: "WAR", label: "Konflikt", tone: "red" as const },
                { icon: "CB", label: "Zentralbank", tone: "blue" as const },
                { icon: "OIL", label: "Energie", tone: "amber" as const },
                { icon: "VOTE", label: "Wahl", tone: "blue" as const },
                { icon: "NAT", label: "Katastrophe", tone: "red" as const },
                { icon: "POL", label: "Politik", tone: "slate" as const },
              ].map((item) => (
                <div key={item.icon} className="flex items-center gap-2 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-600">
                  <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 ${markerClass(item.tone)}`}>
                    <span className={`h-2 w-2 rounded-full ${markerAccentClass(item.tone)}`} />
                    {item.icon}
                  </span>
                  <span className="hidden sm:inline">{item.label}</span>
                </div>
              ))}
            </div>
            ) : null}

            <div className="absolute inset-x-10 top-[60%] hidden h-px bg-[linear-gradient(90deg,rgba(15,23,42,0),rgba(15,23,42,0.28),rgba(15,23,42,0))] lg:block" />

            {activeGeoEvent ? (
              <div className="map-event-focus absolute left-20 top-4 z-30 hidden max-w-[18rem] rounded-[1.1rem] border border-black/8 bg-white/94 px-4 py-3 shadow-[0_14px_30px_rgba(15,23,42,0.1)] sm:block">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                    Focus
                  </div>
                  <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.14em] ${markerClass(activeGeoEvent.markerTone)}`}>
                    <span className={`h-2 w-2 rounded-full ${markerAccentClass(activeGeoEvent.markerTone)}`} />
                    {activeGeoEvent.markerIcon}
                  </span>
                </div>
                <div className="mt-2 line-clamp-3 text-sm font-bold leading-5 text-slate-900">
                  {activeGeoEvent.title}
                </div>
                <div className="mt-2 flex flex-wrap gap-2 text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                  {activeVariantLabel ? (
                    <span className="rounded-full border border-black/8 bg-[var(--accent-soft)] px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.14em] text-[var(--accent)]">
                      {activeVariantLabel}
                    </span>
                  ) : null}
                  {activeGeoEvent.geoZone && activeGeoEvent.geoZone !== activeGeoEvent.regionKey ? (
                    <span className="rounded-full border border-black/8 bg-white px-2 py-1">
                      {activeGeoEvent.geoZone}
                    </span>
                  ) : null}
                  {activeGeoEvent.geoPlace && activeGeoEvent.geoPlace !== activeGeoEvent.geoZone && activeGeoEvent.geoPlace !== activeGeoEvent.regionKey ? (
                    <span className="rounded-full border border-black/8 bg-white px-2 py-1">
                      {activeGeoEvent.geoPlace}
                    </span>
                  ) : null}
                  <span className="rounded-full border border-black/8 bg-white px-2 py-1">
                    {activeGeoEvent.region || "Global"}
                  </span>
                  {activeGeoEvent.event_intelligence?.action ? (
                    <span className="rounded-full border border-black/8 bg-white px-2 py-1">
                      {activeGeoEvent.event_intelligence.action}
                    </span>
                  ) : null}
                  {activeGeoEvent.event_intelligence?.impact_score ? (
                    <span className="rounded-full border border-black/8 bg-white px-2 py-1">
                      impact {activeGeoEvent.event_intelligence.impact_score}
                    </span>
                  ) : null}
                </div>
                {macroDecisionFacts.length ? (
                  <div className="mt-3 grid grid-cols-2 gap-2">
                    {macroDecisionFacts.slice(0, 4).map((fact) => (
                      <div key={fact.label} className="rounded-[0.85rem] border border-black/8 bg-white/78 px-2.5 py-2">
                        <div className="text-[8px] font-extrabold uppercase tracking-[0.14em] text-slate-400">
                          {fact.label}
                        </div>
                        <div className="mt-1 line-clamp-2 text-[10px] font-bold leading-4 text-slate-700">
                          {fact.value}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}

            <div className="world-map-interactive-layer pointer-events-none absolute inset-0" style={mapContentStyle}>
            {showEventLayer && positionedGeoSignals.map((item, index) => (
              <button
                key={item.geoKey || `${item.title}-${index}`}
                type="button"
                onPointerDown={(event) => event.stopPropagation()}
                className={`pointer-events-auto absolute z-10 group transition-opacity ${
                  isRegionFocusMatch(activeRegion?.label, item) &&
                  (!selectedGeoPlace || item.geoPlace === selectedGeoPlace)
                    ? "opacity-100"
                    : "opacity-25 hover:opacity-70"
                }`}
                style={item.adjustedStyle}
                title={item.title}
                aria-label={`${item.title} öffnen`}
                onMouseEnter={() => setHoveredEventIndex(index)}
                onMouseLeave={() => setHoveredEventIndex(null)}
                onFocus={() => setHoveredEventIndex(index)}
                onBlur={() => setHoveredEventIndex(null)}
                onClick={() => {
                  setPinnedEventIndex(index);
                  setImpactDrawerOpen(true);
                }}
              >
                <div className="relative">
                  {item.pulse && (
                    <div className={`absolute inset-0 rounded-full opacity-25 blur-sm ${markerAccentClass(item.markerTone)} animate-ping`} />
                  )}
                  <div
                    className={`relative flex items-center gap-1.5 rounded-full border px-2.5 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] shadow-[0_12px_28px_rgba(15,23,42,0.16)] ${markerClass(item.markerTone)} ${pinnedEventIndex === index ? "ring-2 ring-white/90" : ""} ${
                      isRegionFocusMatch(activeRegion?.label, item) ? "scale-100" : "scale-[0.94]"
                    }`}
                  >
                    <span className={`h-2 w-2 rounded-full ${markerAccentClass(item.markerTone)}`} />
                    <span>{item.markerIcon}</span>
                  </div>
                  <div className="pointer-events-none absolute left-1/2 top-full z-10 mt-2 hidden w-72 -translate-x-1/2 rounded-[1rem] border border-black/8 bg-white/96 p-3 text-left opacity-0 shadow-[0_16px_34px_rgba(15,23,42,0.14)] transition-all duration-150 group-hover:opacity-100 group-focus-within:opacity-100 md:block">
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                        {item.geoPlace && item.geoPlace !== item.regionKey
                          ? `${item.region || "Global"} | ${item.geoPlace}`
                          : item.geoZone && item.geoZone !== item.regionKey
                            ? `${item.region || "Global"} | ${item.geoZone}`
                            : item.region || "Global"}
                      </div>
                      <div className={`rounded-full px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.16em] ${markerClass(item.markerTone)}`}>
                        {item.impact || "macro"}
                      </div>
                    </div>
                    <div className="mt-2 text-sm font-bold leading-5 text-slate-900">{item.title}</div>
                    {item.publisher ? (
                      <div className="mt-2 text-[11px] text-slate-500">{item.publisher}</div>
                    ) : null}
                    {item.event_intelligence ? (
                      <div className="mt-3 space-y-2 text-[11px] text-slate-600">
                        <div className="flex flex-wrap gap-2">
                          <span className="rounded-full border border-black/8 bg-white px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                            impact {item.event_intelligence.impact_score}
                          </span>
                          <span className="rounded-full border border-black/8 bg-white px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                            confidence {item.event_intelligence.confidence_score}
                          </span>
                          {item.event_intelligence.action ? (
                            <span className="rounded-full border border-black/8 bg-[var(--accent-soft)] px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.14em] text-[var(--accent)]">
                              {item.event_intelligence.action}
                            </span>
                          ) : null}
                        </div>
                        {item.event_intelligence.why_now ? (
                          <div className="line-clamp-3 text-[11px] leading-5 text-slate-600">
                            {item.event_intelligence.why_now}
                          </div>
                        ) : null}
                        {item.event_intelligence.affected_assets?.length ? (
                          <div className="line-clamp-2 text-[10px] leading-5 text-slate-500">
                            Assets: {item.event_intelligence.affected_assets.join(" | ")}
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                </div>
              </button>
            ))}
            </div>

            {showLiveAlert && activePulseEvent && hoveredEventIndex == null ? (
                <a
                href={activePulseEvent.link}
                target="_blank"
                rel="noreferrer"
                className="absolute right-4 bottom-4 z-30 hidden max-w-[15rem] rounded-[1rem] border border-black/8 bg-white/94 p-3 shadow-[0_12px_28px_rgba(15,23,42,0.1)] sm:block"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.14em] ${markerClass(activePulseEvent.markerTone)}`}>
                    <span className={`h-2 w-2 rounded-full ${markerAccentClass(activePulseEvent.markerTone)}`} />
                    Live-Alarm
                  </span>
                  <span className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-400">
                    {activePulseEvent.region || "Global"}
                  </span>
                </div>
                <div className="mt-2 line-clamp-3 text-[12px] font-semibold leading-5 text-slate-800">
                  {activePulseEvent.title}
                </div>
                {activePulseEvent.event_intelligence ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    <span className="rounded-full border border-black/8 bg-white px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                      impact {activePulseEvent.event_intelligence.impact_score}
                    </span>
                    <span className="rounded-full border border-black/8 bg-white px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                      {activePulseEvent.event_intelligence.action}
                    </span>
                  </div>
                ) : null}
                {compactList(activePulseEvent.event_intelligence?.affected_sectors, 2).length ? (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {compactList(activePulseEvent.event_intelligence?.affected_sectors, 2).map((sector) => (
                      <span
                        key={sector}
                        className="rounded-full border border-black/8 bg-[var(--accent-soft)] px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.14em] text-[var(--accent)]"
                      >
                        {sector}
                      </span>
                    ))}
                  </div>
                ) : null}
                <button
                  type="button"
                  onClick={(event) => {
                    event.preventDefault();
                    setImpactDrawerOpen(true);
                  }}
                  className="mt-3 rounded-full border border-black/8 bg-[var(--accent-soft)] px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] text-[var(--accent)]"
                >
                  Handelswirkung
                </button>
              </a>
            ) : null}
            </div>

            <div className="mt-4 space-y-3 sm:hidden">
              {activeGeoEvent ? (
                <div className="rounded-[1.05rem] border border-black/8 bg-white/90 px-4 py-3 shadow-[0_12px_24px_rgba(15,23,42,0.08)]">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                      Focus
                    </div>
                    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.14em] ${markerClass(activeGeoEvent.markerTone)}`}>
                      <span className={`h-2 w-2 rounded-full ${markerAccentClass(activeGeoEvent.markerTone)}`} />
                      {activeGeoEvent.markerIcon}
                    </span>
                  </div>
                  <div className="mt-2 text-sm font-bold leading-5 text-slate-900">
                    {activeGeoEvent.title}
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2 text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                    <span className="rounded-full border border-black/8 bg-white px-2 py-1">
                      {activeGeoEvent.region || "Global"}
                    </span>
                    {activeGeoEvent.event_intelligence?.action ? (
                      <span className="rounded-full border border-black/8 bg-[var(--accent-soft)] px-2 py-1 text-[var(--accent)]">
                        {activeGeoEvent.event_intelligence.action}
                      </span>
                    ) : null}
                    {activeGeoEvent.event_intelligence?.impact_score ? (
                      <span className="rounded-full border border-black/8 bg-white px-2 py-1">
                        impact {activeGeoEvent.event_intelligence.impact_score}
                      </span>
                    ) : null}
                  </div>
                  <button
                    type="button"
                    onClick={() => setImpactDrawerOpen(true)}
                    className="mt-3 rounded-full border border-black/8 bg-[var(--accent-soft)] px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] text-[var(--accent)]"
                  >
                    Handelswirkung
                  </button>
                </div>
              ) : null}

              {showLiveAlert && activePulseEvent && hoveredEventIndex == null ? (
                <a
                  href={activePulseEvent.link}
                  target="_blank"
                  rel="noreferrer"
                  className="block rounded-[1.05rem] border border-black/8 bg-white/90 p-4 shadow-[0_12px_24px_rgba(15,23,42,0.08)]"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.14em] ${markerClass(activePulseEvent.markerTone)}`}>
                      <span className={`h-2 w-2 rounded-full ${markerAccentClass(activePulseEvent.markerTone)}`} />
                      Live-Alarm
                    </span>
                    <span className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-400">
                      {activePulseEvent.region || "Global"}
                    </span>
                  </div>
                  <div className="mt-2 text-sm font-semibold leading-5 text-slate-800">
                    {activePulseEvent.title}
                  </div>
                </a>
              ) : null}
            </div>
          </div>

          <div className="space-y-3 xl:max-h-[720px] xl:overflow-y-auto xl:pr-1">
            <div className="rounded-[1.5rem] border border-black/8 bg-white/85 p-4">
              <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                Kartenstatus
              </div>
              <div className="mt-3 grid gap-2 text-xs text-slate-500 sm:grid-cols-3 xl:grid-cols-1">
                <div className="rounded-[0.9rem] border border-black/8 bg-white/75 px-3 py-2">
                  Ereignisse <span className="font-bold text-slate-900">{mapSignalSummary.total}</span>
                </div>
                <div className="rounded-[0.9rem] border border-black/8 bg-white/75 px-3 py-2">
                  Hohe Wirkung <span className="font-bold text-slate-900">{mapSignalSummary.highImpact}</span>
                </div>
                <div className="rounded-[0.9rem] border border-black/8 bg-white/75 px-3 py-2">
                  Handlungsrelevant <span className="font-bold text-slate-900">{mapSignalSummary.actionable}</span>
                </div>
              </div>
            </div>

            {displayRegion && (
              <div className="rounded-[1.5rem] border border-black/8 bg-white/85 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                      Regionsfokus
                    </div>
                    <div className="mt-2 text-xl font-black text-slate-900">
                      {regionDisplayLabel(displayRegion.label)}
                    </div>
                  </div>
                  <div
                    className={`rounded-full px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] ${tonePillClass(displayRegion.tone)}`}
                  >
                    {localizeMarketRegime(displayRegion.tone)}
                  </div>
                </div>
                <div className={`mt-3 text-2xl font-black ${textToneClass(displayRegion.tone)}`}>
                  {dataCurrent ? formatPct(displayRegion.avg_change_1d) : "—"}
                </div>
                {regionDrilldown.zones.length ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {regionDrilldown.zones.map(([zone, count]) => (
                      <span
                        key={zone}
                        className="rounded-full border border-black/8 bg-white px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500"
                      >
                        {zone}
                        {count > 1 ? ` ${count}` : ""}
                      </span>
                    ))}
                  </div>
                ) : null}
                {regionDrilldown.places.length ? (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {regionDrilldown.places.map(([place, count]) => (
                      <button
                        key={place}
                        type="button"
                        onClick={() => {
                          const nextPlace = selectedGeoPlace === place ? null : place;
                          setSelectedGeoPlace(nextPlace);
                          if (!nextPlace) return;
                          const nextIndex = positionedGeoSignals.findIndex((candidate) => candidate.geoPlace === nextPlace);
                          if (nextIndex >= 0) setPinnedEventIndex(nextIndex);
                        }}
                        className={`rounded-full border px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] transition-all ${
                          selectedGeoPlace === place
                            ? "border-[var(--accent)] bg-[var(--accent)] text-white shadow-[0_10px_20px_rgba(15,118,110,0.18)]"
                            : "border-[var(--accent)]/12 bg-[var(--accent-soft)] text-[var(--accent)]"
                        }`}
                      >
                        {place}
                        {count > 1 ? ` ${count}` : ""}
                      </button>
                    ))}
                    {selectedGeoPlace ? (
                      <button
                        type="button"
                        onClick={() => setSelectedGeoPlace(null)}
                        className="rounded-full border border-black/8 bg-white px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500"
                      >
                        Auswahl löschen
                      </button>
                    ) : null}
                  </div>
                ) : null}
                {regionDrilldown.placeHeat.length ? (
                  <div className="mt-4 space-y-2">
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                      Länderaktivität
                    </div>
                    {regionDrilldown.placeHeat.map((item) => (
                      <button
                        key={item.place}
                        type="button"
                        onClick={() => {
                          const nextPlace = selectedGeoPlace === item.place ? null : item.place;
                          setSelectedGeoPlace(nextPlace);
                          if (!nextPlace) return;
                          const nextIndex = positionedGeoSignals.findIndex((candidate) => candidate.geoPlace === nextPlace);
                          if (nextIndex >= 0) setPinnedEventIndex(nextIndex);
                        }}
                        className="block w-full rounded-[0.95rem] border border-black/8 bg-white/75 px-3 py-2 text-left transition-colors hover:bg-white"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-700">
                            {item.place}
                          </div>
                          <div className="flex items-center gap-2 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-400">
                            <span>{item.events} Ereignisse</span>
                            <span>|</span>
                            <span>{item.actionable} handlungsrelevant</span>
                          </div>
                        </div>
                        <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
                          <div
                            className={`h-full rounded-full ${selectedGeoPlace === item.place ? "bg-[var(--accent)]" : "bg-slate-900/75"}`}
                            style={{ width: `${item.weight}%` }}
                          />
                        </div>
                      </button>
                    ))}
                  </div>
                ) : null}
                <div className="mt-3 space-y-2">
                  {(displayRegion.assets || []).slice(0, 1).map((asset) => (
                    <div
                      key={asset.ticker}
                      className="flex items-center justify-between rounded-[0.95rem] border border-black/8 bg-white/75 px-3 py-2"
                    >
                      <div>
                        <div className="text-sm font-bold text-slate-900">{asset.label}</div>
                        <div className="text-[11px] text-slate-500">{asset.ticker}</div>
                      </div>
                      <div
                        className={`text-sm font-bold ${
                          (asset.change_1d || 0) >= 0 ? "text-emerald-700" : "text-red-700"
                        }`}
                      >
                        {formatPct(asset.change_1d || 0)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {displayRegion ? (
              <div className="rounded-[1.5rem] border border-black/8 bg-white/85 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                    Regionsdetails
                  </div>
                  <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-400">
                    {regionDisplayLabel(displayRegion.label)}
                  </div>
                </div>
                <div className="mt-3 grid gap-2 text-xs text-slate-500 sm:grid-cols-3 xl:grid-cols-1">
                  <div className="rounded-[0.9rem] border border-black/8 bg-white/75 px-3 py-2">
                    Ereignisse <span className="font-bold text-slate-900">{regionDrilldown.total}</span>
                  </div>
                  <div className="rounded-[0.9rem] border border-black/8 bg-white/75 px-3 py-2">
                    Hohe Wirkung <span className="font-bold text-slate-900">{regionDrilldown.highImpact}</span>
                  </div>
                  <div className="rounded-[0.9rem] border border-black/8 bg-white/75 px-3 py-2">
                    Handlungsrelevant <span className="font-bold text-slate-900">{regionDrilldown.actionable}</span>
                  </div>
                </div>
                <div className="mt-4 space-y-2">
                  {selectedGeoPlace ? (
                    <div className="rounded-[0.9rem] border border-[var(--accent)]/12 bg-[var(--accent-soft)] px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.14em] text-[var(--accent)]">
                      Ortsfokus: {selectedGeoPlace}
                    </div>
                  ) : null}
                  {selectedGeoPlace && regionDrilldown.eventMix.length ? (
                    <div className="flex flex-wrap gap-2">
                      {regionDrilldown.eventMix.map(([eventCode, count]) => (
                        <span
                          key={eventCode}
                          className="rounded-full border border-black/8 bg-white px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500"
                        >
                          {eventCode} {count}
                        </span>
                      ))}
                    </div>
                  ) : null}
                  {selectedGeoPlace && regionDrilldown.placeStack.length ? (
                    <div className="grid gap-2">
                      {regionDrilldown.placeStack.map((item) => (
                        <button
                          key={item.key}
                          type="button"
                          onClick={() => {
                            const nextIndex = positionedGeoSignals.findIndex((candidate) => candidate.geoKey === item.geoKey);
                            if (nextIndex >= 0) setPinnedEventIndex(nextIndex);
                            setImpactDrawerOpen(true);
                          }}
                          className="rounded-[0.95rem] border border-black/8 bg-white px-3 py-2 text-left transition-colors hover:bg-[var(--accent-soft)]"
                        >
                          <div className="flex items-center justify-between gap-3">
                            <div className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                              {item.eventCode} | {item.label}
                            </div>
                            <div className={`rounded-full px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.14em] ${freshnessClass(item.freshness)}`}>
                              {item.freshness}
                            </div>
                          </div>
                          <div className="mt-2 flex flex-wrap gap-2 text-[10px] font-extrabold uppercase tracking-[0.14em]">
                            <span className="rounded-full border border-black/8 bg-white px-2 py-1 text-slate-500">
                              {item.impact}
                            </span>
                            <span className="rounded-full border border-[var(--accent)]/12 bg-[var(--accent-soft)] px-2 py-1 text-[var(--accent)]">
                              {item.action}
                            </span>
                            <span className={`rounded-full px-2 py-1 ${placeOutcomeTone(item.action)}`}>
                              {placeOutcomeLabel(item.action)}
                            </span>
                          </div>
                          {item.thesis ? (
                            <div className="mt-2 line-clamp-2 text-[11px] leading-5 text-slate-600">
                              {item.thesis}
                            </div>
                          ) : null}
                          {item.trigger ? (
                            <div className="mt-2 line-clamp-2 text-[11px] leading-5 text-slate-500">
                              Trigger: {item.trigger}
                            </div>
                          ) : null}
                          {item.risk ? (
                            <div className="mt-2 line-clamp-2 text-[11px] leading-5 text-slate-400">
                              Risk: {item.risk}
                            </div>
                          ) : null}
                        </button>
                      ))}
                    </div>
                  ) : null}
                  {regionDrilldown.items.length ? (
                    regionDrilldown.items.map((item, index) => (
                      <button
                        key={item.geoKey || `${item.title}-${index}`}
                        onClick={() => {
                          const nextIndex = positionedGeoSignals.findIndex((candidate) => candidate.geoKey === item.geoKey);
                          if (nextIndex >= 0) setPinnedEventIndex(nextIndex);
                        }}
                        className={`block w-full rounded-[1rem] border p-3 text-left transition-colors ${
                          activeGeoEvent?.geoKey === item.geoKey
                            ? "border-[var(--accent)] bg-[var(--accent-soft)]/70"
                            : "border-black/8 bg-white/75 hover:bg-white"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                            {describeEventVariant(item) || item.markerLabel}
                          </div>
                          <div className={`rounded-full px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.14em] ${freshnessClass(freshnessLabel(item.event_intelligence?.decay, item.pulse))}`}>
                            {freshnessDisplayLabel(freshnessLabel(item.event_intelligence?.decay, item.pulse))}
                          </div>
                        </div>
                        <div className="mt-2 line-clamp-2 text-sm font-bold text-slate-900">{item.title}</div>
                        {item.geoPlace && item.geoPlace !== item.regionKey ? (
                          <div className="mt-2 text-[10px] font-extrabold uppercase tracking-[0.14em] text-[var(--accent)]">
                            {item.geoPlace}
                          </div>
                        ) : null}
                        {item.geoZone && item.geoZone !== item.regionKey ? (
                          <div className="mt-2 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-400">
                            {item.geoZone}
                          </div>
                        ) : null}
                        {item.event_intelligence?.affected_assets?.length ? (
                          <div className="mt-2 text-[11px] leading-5 text-slate-500">
                            Assets: {compactList(item.event_intelligence.affected_assets, 2).join(" | ")}
                          </div>
                        ) : null}
                      </button>
                    ))
                  ) : (
                    <div className="rounded-[1rem] border border-black/8 bg-white/75 p-3 text-sm text-slate-500">
                      Keine dominanten Regionsdetails für {regionDisplayLabel(displayRegion.label)} im aktuellen Filter.
                    </div>
                  )}
                </div>
              </div>
            ) : null}

            {activeGeoEvent ? (
              <div className="rounded-[1.5rem] border border-black/8 bg-white/85 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                      Markt-Auswirkung
                    </div>
                    <div className="mt-1 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-400">
                      Entscheidungsrahmen
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setImpactDrawerOpen(true)}
                      className="rounded-full border border-black/8 bg-[var(--accent-soft)] px-2.5 py-1 text-[9px] font-extrabold uppercase tracking-[0.16em] text-[var(--accent)] lg:hidden"
                    >
                      Open
                    </button>
                    <div className={`rounded-full border px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.16em] ${markerClass(activeGeoEvent.markerTone)}`}>
                      {activeGeoEvent.markerIcon}
                    </div>
                  </div>
                </div>
                <div className="mt-3 line-clamp-3 text-sm font-bold leading-6 text-slate-900">
                  {activeGeoEvent.title}
                </div>
                {tradeImpactCards.length ? (
                  <div className="mt-3 grid gap-2 sm:grid-cols-3">
                    {tradeImpactCards.map((card) => (
                      <div key={card.label} className="rounded-[0.95rem] border border-black/8 bg-white/80 px-3 py-2">
                        <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                          {regionDisplayLabel(card.label)}
                        </div>
                        <div className={`mt-2 inline-flex rounded-full px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.14em] ${card.tone}`}>
                          {card.value}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : null}
                <div className="mt-3 flex flex-wrap gap-2 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                  {activeVariantLabel ? (
                    <span className="rounded-full border border-black/8 bg-[var(--accent-soft)] px-2 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-[var(--accent)]">
                      {activeVariantLabel}
                    </span>
                  ) : null}
                  {activeGeoEvent.geoZone && activeGeoEvent.geoZone !== activeGeoEvent.regionKey ? (
                    <span className="rounded-full border border-black/8 bg-white px-2 py-1">
                      {activeGeoEvent.geoZone}
                    </span>
                  ) : null}
                  {activeGeoEvent.geoPlace && activeGeoEvent.geoPlace !== activeGeoEvent.geoZone && activeGeoEvent.geoPlace !== activeGeoEvent.regionKey ? (
                    <span className="rounded-full border border-black/8 bg-white px-2 py-1">
                      {activeGeoEvent.geoPlace}
                    </span>
                  ) : null}
                  <span className="rounded-full border border-black/8 bg-white px-2 py-1">
                    {activeGeoEvent.region || "Global"}
                  </span>
                  <span className="rounded-full border border-black/8 bg-white px-2 py-1">
                    {activeGeoEvent.impact || "macro"}
                  </span>
                  {activeGeoEvent.event_intelligence?.action ? (
                    <span className="rounded-full border border-black/8 bg-white px-2 py-1">
                      {activeGeoEvent.event_intelligence.action}
                    </span>
                  ) : null}
                  <span
                    className={`rounded-full px-2 py-1 ${freshnessClass(
                      freshnessLabel(activeGeoEvent.event_intelligence?.decay, activeGeoEvent.pulse),
                    )}`}
                  >
                    {freshnessDisplayLabel(freshnessLabel(activeGeoEvent.event_intelligence?.decay, activeGeoEvent.pulse))}
                  </span>
                  {activeGeoEvent.event_intelligence?.leverage ? (
                    <span className="rounded-full border border-black/8 bg-white px-2 py-1">
                      leverage {activeGeoEvent.event_intelligence.leverage}
                    </span>
                  ) : null}
                  {activeGeoEvent.event_intelligence?.decision_quality ? (
                    <span className={`rounded-full px-2 py-1 ${decisionToneClass(activeGeoEvent.event_intelligence.decision_quality)}`}>
                      {decisionQualityLabel(activeGeoEvent.event_intelligence.decision_quality)}
                    </span>
                  ) : null}
                </div>
                {activeGeoEvent.event_intelligence ? (
                  <div className="mt-3">
                    <div className="grid gap-2 text-xs text-slate-500 sm:grid-cols-3">
                      <div className="rounded-[0.9rem] border border-black/8 bg-white/75 px-3 py-2">
                        Marktwirkung <span className="font-bold text-slate-900">{activeGeoEvent.event_intelligence.impact_score}/100</span>
                      </div>
                      <div className="rounded-[0.9rem] border border-black/8 bg-white/75 px-3 py-2">
                        Belastbarkeit <span className="font-bold text-slate-900">{macroConfidenceLabel(activeGeoEvent.event_intelligence.confidence_score, activeGeoEvent.event_intelligence.decision_quality)}</span>
                      </div>
                      <div className="rounded-[0.9rem] border border-black/8 bg-white/75 px-3 py-2">
                        Zeithorizont <span className="font-bold text-slate-900">{macroHorizonLabel(activeGeoEvent)}</span>
                      </div>
                    </div>
                    <div className="mt-2 rounded-[0.9rem] border border-amber-500/15 bg-amber-500/8 px-3 py-2 text-[11px] leading-5 text-slate-600">
                      Belastbarkeit bewertet Quellen- und Signalstruktur. Sie garantiert nicht, dass die Meldung wahr ist oder der Markt wie erwartet reagiert.
                    </div>
                  </div>
                ) : null}
                {compactList(activeGeoEvent.event_intelligence?.affected_sectors).length ? (
                  <div className="mt-3">
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                      Betroffene Sektoren
                    </div>
                    <div className="mt-2 grid gap-2">
                      {compactList(activeGeoEvent.event_intelligence?.affected_sectors).map((sector) => {
                        const heat = sectorHeatProfile(sector, activeGeoEvent.event_intelligence?.action);
                        return (
                          <div
                            key={sector}
                            className="rounded-[0.95rem] border border-black/8 bg-white px-3 py-2"
                          >
                            <div className="flex items-center justify-between gap-3">
                              <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-700">
                                {sector}
                              </span>
                              <span className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                                {heat.level}
                              </span>
                            </div>
                            <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
                              <div
                                className={`h-full rounded-full ${heat.toneClass}`}
                                style={{ width: `${heat.level}%` }}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ) : null}
                {compactList(activeGeoEvent.event_intelligence?.affected_assets, 4).length ? (
                  <div className="mt-3">
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                      Betroffene Assets
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {compactList(activeGeoEvent.event_intelligence?.affected_assets, 4).map((asset) => (
                        <button
                          key={asset}
                          onClick={() => onAnalyze(asset)}
                          className="rounded-full border border-[var(--accent)]/15 bg-[var(--accent-soft)] px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--accent)]"
                        >
                          {asset}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}
                {activeGeoEvent.portfolio_exposure?.note ? (
                  <div className="mt-3 rounded-[0.9rem] border border-black/8 bg-[var(--accent-soft)] px-3 py-2 text-xs text-slate-700">
                    <div className="flex items-center justify-between gap-2">
                      <span>{activeGeoEvent.portfolio_exposure.note}</span>
                      {activeGeoEvent.portfolio_exposure.exposure_strength ? (
                        <span
                          className={`rounded-full px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.14em] ${exposureToneClass(
                            activeGeoEvent.portfolio_exposure.exposure_strength,
                          )}`}
                        >
                          Portfolio-Exposure {activeGeoEvent.portfolio_exposure.exposure_strength}
                        </span>
                      ) : null}
                    </div>
                    {compactList(activeGeoEvent.portfolio_exposure.matched_holdings, 4).length ? (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {compactList(activeGeoEvent.portfolio_exposure.matched_holdings, 4).map((holding) => (
                          <button
                            key={holding}
                            onClick={() => onAnalyze(holding)}
                            className="rounded-full border border-black/8 bg-white px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-700"
                          >
                            {holding}
                          </button>
                        ))}
                      </div>
                    ) : null}
                    {compactList(activeGeoEvent.portfolio_exposure.matched_sectors, 3).length ? (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {compactList(activeGeoEvent.portfolio_exposure.matched_sectors, 3).map((sector) => (
                          <span
                            key={sector}
                            className="rounded-full border border-black/8 bg-white px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500"
                          >
                            {sector}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
                {hedgeIdeas.length ? (
                  <div className="mt-3">
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                      Absicherungs-Ideen
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {hedgeIdeas.map((idea) => (
                        <button
                          key={idea.ticker}
                          onClick={() => onAnalyze(idea.ticker)}
                          className="rounded-full border border-black/8 bg-white px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-600"
                        >
                          {idea.ticker} - {idea.label}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}
                <div className="mt-3 space-y-2">
                  {activeGeoEvent.event_intelligence?.execution_bias ? (
                    <div className="rounded-[0.9rem] border border-black/8 bg-white/75 px-3 py-2 text-xs leading-6 text-slate-600">
                      Handelsrichtung: {activeGeoEvent.event_intelligence.execution_bias} | Positionsgröße: {activeGeoEvent.event_intelligence.size_guidance}
                    </div>
                  ) : null}
                  {activeGeoEvent.event_intelligence?.trigger ? (
                    <div className="rounded-[0.9rem] border border-black/8 bg-white/75 px-3 py-2 text-xs leading-6 text-slate-600">
                      Trigger: {activeGeoEvent.event_intelligence.trigger}
                    </div>
                  ) : null}
                  {activeGeoEvent.event_intelligence?.invalidation ? (
                    <div className="rounded-[0.9rem] border border-black/8 bg-white/75 px-3 py-2 text-xs leading-6 text-slate-600">
                      These ungültig wenn: {activeGeoEvent.event_intelligence.invalidation}
                    </div>
                  ) : null}
                </div>
                {activeGeoEvent.event_intelligence?.execution_window ? (
                  <div className="mt-2 text-[11px] font-bold uppercase tracking-[0.14em] text-slate-500">
                    Zeithorizont: {activeGeoEvent.event_intelligence.execution_window}
                  </div>
                ) : null}
              </div>
            ) : null}

            <div className="rounded-[1.5rem] border border-black/8 bg-[linear-gradient(180deg,rgba(15,118,110,0.07),rgba(255,255,255,0.88))] p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                  Warum das wichtig ist
                </div>
                {focusTicker ? (
                  <button
                    onClick={() => onAnalyze(focusTicker)}
                    className="rounded-full border border-black/8 bg-white px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-600"
                  >
                    {focusTicker}
                  </button>
                ) : null}
              </div>
              <div className="mt-4 space-y-3">
                {whyItMatters.length ? (
                  whyItMatters.map((item, index) => (
                    <div
                      key={`${item}-${index}`}
                      className="rounded-[1rem] border border-black/8 bg-white/78 p-3 text-sm leading-6 text-slate-700"
                    >
                      {item}
                    </div>
                  ))
                ) : (
                  <div className="rounded-[1rem] border border-black/8 bg-white/78 p-3 text-sm leading-6 text-slate-500">
                    Der aktive Welt- und Makroblock wird geladen. Sobald neue Ereignisse klassifiziert sind, erscheint hier die direkte Relevanz für Region, Risiko und mögliche Marktreaktion.
                  </div>
                )}
              </div>
            </div>

            <div className="rounded-[1.5rem] border border-black/8 bg-white/85 p-4">
              <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                Ereignisebene
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-3">
                <div className="rounded-[0.9rem] border border-black/8 bg-white/75 px-3 py-2 text-xs text-slate-500">
                  Neu <span className="font-bold text-slate-900">{eventTempo.developing}</span>
                </div>
                <div className="rounded-[0.9rem] border border-black/8 bg-white/75 px-3 py-2 text-xs text-slate-500">
                  Aktiv <span className="font-bold text-slate-900">{eventTempo.active}</span>
                </div>
                <div className="rounded-[0.9rem] border border-black/8 bg-white/75 px-3 py-2 text-xs text-slate-500">
                  Abklingend <span className="font-bold text-slate-900">{eventTempo.fading}</span>
                </div>
              </div>
              <div className="mt-4 space-y-3">
                {showEventLayer && visibleEventLayerSignals.length ? (
                  visibleEventLayerSignals.slice(0, 4).map((item) => (
                    <a
                      key={item.geoKey || item.title}
                      href={item.link}
                      target="_blank"
                      rel="noreferrer"
                      onMouseEnter={() => {
                        const nextIndex = positionedGeoSignals.findIndex((candidate) => candidate.geoKey === item.geoKey);
                        if (nextIndex >= 0) setHoveredEventIndex(nextIndex);
                      }}
                      onMouseLeave={() => setHoveredEventIndex(null)}
                      onFocus={() => {
                        const nextIndex = positionedGeoSignals.findIndex((candidate) => candidate.geoKey === item.geoKey);
                        if (nextIndex >= 0) setHoveredEventIndex(nextIndex);
                      }}
                      onBlur={() => setHoveredEventIndex(null)}
                      onClick={() => {
                        const nextIndex = positionedGeoSignals.findIndex((candidate) => candidate.geoKey === item.geoKey);
                        if (nextIndex >= 0) setPinnedEventIndex(nextIndex);
                        setImpactDrawerOpen(true);
                      }}
                      className={`block rounded-[1rem] border p-3 transition-colors hover:bg-white ${
                        activeGeoEvent?.title === item.title
                          ? "border-[var(--accent)] bg-[var(--accent-soft)]/70"
                          : "border-black/8 bg-white/75"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div
                          className={`rounded-full border px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.16em] ${markerClass(item.markerTone)}`}
                        >
                          {describeEventVariant(item) || item.markerLabel}
                        </div>
                      <div className="flex items-center gap-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                        <span>{item.region || "Global"}</span>
                        {item.geoPlace && item.geoPlace !== item.regionKey ? (
                          <>
                            <span>|</span>
                            <span>{item.geoPlace}</span>
                          </>
                        ) : null}
                        {item.geoZone && item.geoZone !== item.regionKey ? (
                          <>
                            <span>|</span>
                            <span>{item.geoZone}</span>
                          </>
                        ) : null}
                        <span>|</span>
                        <span>{item.impact || "macro"}</span>
                          <span
                            className={`rounded-full px-2 py-1 ${freshnessClass(
                              freshnessLabel(item.event_intelligence?.decay, item.pulse),
                            )}`}
                          >
                            {freshnessDisplayLabel(freshnessLabel(item.event_intelligence?.decay, item.pulse))}
                          </span>
                        </div>
                      </div>
                      <div className="mt-2 line-clamp-2 text-sm font-bold text-slate-900">{item.title}</div>
                      {item.event_intelligence ? (
                        <div className="mt-3 space-y-2 text-xs text-slate-500">
                          <div className="flex flex-wrap gap-2">
                            <span>Wirkung {item.event_intelligence.impact_score}</span>
                            <span>Belastbarkeit {item.event_intelligence.confidence_score}</span>
                            <span>{item.event_intelligence.decay}</span>
                          </div>
                          <div className="line-clamp-2">
                            Action: {item.event_intelligence.action} | Leverage {item.event_intelligence.leverage}
                          </div>
                          {item.event_intelligence.decision_quality ? (
                            <div className="flex flex-wrap gap-2">
                              <span className={`rounded-full px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.14em] ${decisionToneClass(item.event_intelligence.decision_quality)}`}>
                                {decisionQualityLabel(item.event_intelligence.decision_quality)}
                              </span>
                              {item.event_intelligence.size_guidance ? (
                                <span className="rounded-full border border-black/8 bg-white px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                                  {item.event_intelligence.size_guidance}
                                </span>
                              ) : null}
                            </div>
                          ) : null}
                          {compactList(item.event_intelligence.affected_sectors, 2).length ? (
                            <div className="flex flex-wrap gap-2">
                              {compactList(item.event_intelligence.affected_sectors, 2).map((sector) => (
                                <span
                                  key={sector}
                                  className="rounded-full border border-black/8 bg-white px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500"
                                >
                                  {sector}
                                </span>
                              ))}
                            </div>
                          ) : null}
                          {activeGeoEvent?.geoKey === item.geoKey ? (
                            <>
                              {item.event_intelligence.trigger ? (
                                <div className="line-clamp-2">
                                  Trigger: {item.event_intelligence.trigger}
                                </div>
                              ) : null}
                            </>
                          ) : null}
                        </div>
                      ) : null}
                      {item.portfolio_exposure?.note ? (
                        <div className="mt-2 rounded-[0.9rem] border border-black/8 bg-[var(--accent-soft)] px-3 py-2 text-xs text-slate-700">
                          <div className="flex items-center justify-between gap-2">
                            <span>{item.portfolio_exposure.note}</span>
                            {item.portfolio_exposure.exposure_strength ? (
                              <span
                                className={`rounded-full px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.14em] ${exposureToneClass(
                                  item.portfolio_exposure.exposure_strength,
                                )}`}
                              >
                                {item.portfolio_exposure.exposure_strength}
                              </span>
                            ) : null}
                          </div>
                          {compactList(item.portfolio_exposure.matched_holdings, 3).length ? (
                            <div className="mt-2 flex flex-wrap gap-2">
                              {compactList(item.portfolio_exposure.matched_holdings, 3).map((holding) => (
                                <button
                                  key={holding}
                                  onClick={(event) => {
                                    event.preventDefault();
                                    onAnalyze(holding);
                                  }}
                                  className="rounded-full border border-black/8 bg-white px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-700"
                                >
                                  {holding}
                                </button>
                              ))}
                            </div>
                          ) : null}
                        </div>
                      ) : null}
                    </a>
                  ))
                ) : (
                  <div className="rounded-[1rem] border border-black/8 bg-white/75 p-3 text-sm text-slate-500">
                    {showEventLayer
                      ? `Keine dominanten Ereignisse im aktuellen Filter${selectedGeoPlace ? ` für ${selectedGeoPlace}` : ""} für ${timeLens}.`
                      : "Die Ereignisebene ist ausgeblendet."}
                  </div>
                )}
              </div>
            </div>

            <div className="rounded-[1.5rem] border border-black/8 bg-white/85 p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                  Kontra-Radar
                </div>
                <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-400">
                  Medienabkühlung
                </div>
              </div>
              <div className="mt-4 space-y-3">
                {regionalContrarian.length ? (
                  regionalContrarian.slice(0, 2).map((item, index) => (
                    <div
                      key={`${item.ticker}-${index}`}
                      className="rounded-[1rem] border border-black/8 bg-white/75 p-3"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <button
                          onClick={() => item.ticker && onAnalyze(item.ticker)}
                          className="text-sm font-black text-slate-900"
                        >
                          {item.ticker}
                        </button>
                        <div
                          className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${
                            item.contrarian_bias === "long"
                              ? "bg-emerald-500/10 text-emerald-700"
                              : "bg-red-500/10 text-red-700"
                          }`}
                        >
                          inverse {item.contrarian_bias}
                        </div>
                      </div>
                      <div className="mt-2 text-sm text-slate-600">{item.reason}</div>
                    </div>
                  ))
                ) : (
                  <div className="rounded-[1rem] border border-black/8 bg-white/75 p-3 text-sm text-slate-500">
                    Kein bestaetigtes kontraeres Mediensetup in der aktiven Region.
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="hidden gap-4 sm:grid md:grid-cols-3">
          {timeline.slice(0, 3).map((item: any) => (
            <div
              key={item.stage}
              className="rounded-[1.5rem] border border-black/8 bg-white/78 p-4"
            >
              <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                {item.stage}
              </div>
              <div className="mt-2 flex items-center justify-between gap-3">
                <div className="text-lg font-black text-slate-900">{item.label}</div>
                <div className={`rounded-full px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.16em] ${tonePillClass(item.tone)}`}>
                  {localizeMarketRegime(item.tone)}
                </div>
              </div>
              <div className={`mt-3 text-2xl font-black ${textToneClass(item.tone)}`}>
                {formatPct(item.move)}
              </div>
              <div className="mt-2 text-sm leading-6 text-slate-600">{item.driver}</div>
            </div>
          ))}
        </div>

        <div className="hidden rounded-[1.6rem] border border-black/8 bg-white/80 p-4 sm:block">
          <div className="flex items-center justify-between gap-3">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Ereignisverlauf
            </div>
            <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-400">
              {timeLens} lens
            </div>
          </div>
          <div className="mt-4 grid gap-3 xl:grid-cols-3">
            {replayEvents.length ? (
              replayEvents.map((item) => (
                <div
                  key={item.key}
                  className="rounded-[1.2rem] border border-black/8 bg-white/75 p-4"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                      {item.region}
                    </div>
                    <div className={`rounded-full px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.14em] ${freshnessClass(item.freshness)}`}>
                      {item.freshness}
                    </div>
                  </div>
                  <div className="mt-2 text-sm font-bold text-slate-900">{item.variant}</div>
                  {item.geoPlace && item.geoPlace !== item.region ? (
                    <div className="mt-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-[var(--accent)]">
                      {item.geoPlace}
                    </div>
                  ) : null}
                  {item.geoZone && item.geoZone !== item.region ? (
                    <div className="mt-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-400">
                      {item.geoZone}
                    </div>
                  ) : null}
                  <div className="mt-2 line-clamp-2 text-sm text-slate-600">{item.title}</div>
                  <div className="mt-3 flex flex-wrap gap-2 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                    <span className="rounded-full border border-black/8 bg-white px-2 py-1">
                      {item.impact}
                    </span>
                    <span className="rounded-full border border-black/8 bg-white px-2 py-1">
                      {item.action}
                    </span>
                    {item.asset ? (
                      <button
                        onClick={() => onAnalyze(item.asset!)}
                        className="rounded-full border border-[var(--accent)]/15 bg-[var(--accent-soft)] px-2 py-1 text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--accent)]"
                      >
                        {item.asset}
                      </button>
                    ) : null}
                  </div>
                  {item.trigger ? (
                    <div className="mt-3 text-xs leading-6 text-slate-500">
                      Trigger: {item.trigger}
                    </div>
                  ) : null}
                </div>
              ))
            ) : (
              <div className="rounded-[1.2rem] border border-black/8 bg-white/75 p-4 text-sm text-slate-500 xl:col-span-3">
                Kein Replay im aktuellen Kartenfilter. Wechsle auf `24h` oder `7d`, um den breiteren Event-Verlauf zu sehen.
              </div>
            )}
          </div>
        </div>
      </div>

      {impactDrawerOpen && activeGeoEvent ? (
        <>
          <button
            type="button"
            aria-label="Marktwirkungsbereich schließen"
            onClick={() => setImpactDrawerOpen(false)}
            className="fixed inset-0 z-[70] bg-black/18 backdrop-blur-[1px] lg:hidden"
          />
          <div id="map-impact-dialog" role="dialog" aria-modal="true" aria-labelledby="map-impact-title" className="world-map-impact-drawer fixed inset-x-2 bottom-[calc(0.5rem+env(safe-area-inset-bottom))] z-[71] max-h-[min(78dvh,42rem)] overflow-y-auto rounded-[1.6rem] border border-black/8 bg-[rgba(250,248,244,0.98)] p-4 shadow-[0_-18px_48px_rgba(17,24,39,0.18)] backdrop-blur-3xl lg:hidden">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
                  Markt-Auswirkung
                </div>
                <div id="map-impact-title" className="mt-1 text-base font-black text-slate-900">
                  {activeVariantLabel || activeGeoEvent.markerLabel}
                </div>
              </div>
              <button
                type="button"
                onClick={() => setImpactDrawerOpen(false)}
                className="min-h-10 rounded-full border border-black/8 bg-white px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500"
              >
                Schließen
              </button>
            </div>

            <div className="mt-3 text-sm font-bold leading-6 text-slate-900">
              {activeGeoEvent.title}
            </div>

            {tradeImpactCards.length ? (
              <div className="mt-4">
                <div className="grid gap-2">
                  {tradeImpactCards.map((card) => (
                    <div key={card.label} className="rounded-[1rem] border border-black/8 bg-white/82 px-3 py-3">
                      <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                        {regionDisplayLabel(card.label)}
                      </div>
                      <div className={`mt-2 inline-flex rounded-full px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.14em] ${card.tone}`}>
                        {card.value}
                      </div>
                    </div>
                  ))}
                </div>
                <div className="mt-2 rounded-[1rem] border border-amber-500/15 bg-amber-500/8 px-3 py-2 text-[11px] leading-5 text-slate-600">
                  Hohe Belastbarkeit ist keine Garantie. Quelle, zweite Bestätigung und echte Preisreaktion bleiben Pflicht.
                </div>
              </div>
            ) : null}

            {activeGeoEvent.event_intelligence?.why_now ? (
              <div className="mt-4 rounded-[1rem] border border-black/8 bg-white/82 px-3 py-3 text-sm leading-6 text-slate-700">
                <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                  Warum jetzt
                </div>
                <div className="mt-2">{activeGeoEvent.event_intelligence.why_now}</div>
              </div>
            ) : null}

            <div className="mt-4 space-y-2">
              {activeGeoEvent.event_intelligence?.trigger ? (
                <div className="rounded-[1rem] border border-black/8 bg-white/82 px-3 py-3 text-sm leading-6 text-slate-700">
                  <span className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">Trigger</span>
                  <div className="mt-2">{activeGeoEvent.event_intelligence.trigger}</div>
                </div>
              ) : null}
              {activeGeoEvent.event_intelligence?.invalidation ? (
                <div className="rounded-[1rem] border border-black/8 bg-white/82 px-3 py-3 text-sm leading-6 text-slate-700">
                  <span className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">These ungültig wenn</span>
                  <div className="mt-2">{activeGeoEvent.event_intelligence.invalidation}</div>
                </div>
              ) : null}
              {activeGeoEvent.event_intelligence?.execution_bias ? (
                <div className="rounded-[1rem] border border-black/8 bg-white/82 px-3 py-3 text-sm leading-6 text-slate-700">
                  <span className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">Umsetzung</span>
                  <div className="mt-2">
                    {activeGeoEvent.event_intelligence.execution_bias}
                    {activeGeoEvent.event_intelligence.size_guidance ? ` | ${activeGeoEvent.event_intelligence.size_guidance}` : ""}
                  </div>
                </div>
              ) : null}
            </div>

            {tradeImpactAssets.length ? (
              <div className="mt-4">
                <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                  Betroffene Assets
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {tradeImpactAssets.map((asset) => (
                    <button
                      key={asset}
                      onClick={() => onAnalyze(asset)}
                      className="rounded-full border border-[var(--accent)]/15 bg-[var(--accent-soft)] px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.14em] text-[var(--accent)]"
                    >
                      {asset}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            {hedgeIdeas.length ? (
              <div className="mt-4">
                <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                  Absicherungs-Ideen
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {hedgeIdeas.map((idea) => (
                    <button
                      key={idea.ticker}
                      onClick={() => onAnalyze(idea.ticker)}
                      className="rounded-full border border-black/8 bg-white px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.14em] text-slate-600"
                    >
                      {idea.ticker} - {idea.label}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </>
      ) : null}
    </section>
  );
}
