import React, { useEffect, useMemo, useState } from "react";

// Lazy-load world map SVG — keeps initial bundle ~280KB smaller
const worldMapSvg = new URL("../assets/world-map-wikimedia.svg", import.meta.url).href;

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

interface WorldMarketMapProps {
  regions: RegionSummary[];
  selectedRegion: string;
  onSelectRegion: (regionLabel: string) => void;
  news?: MapNewsItem[];
  eventLayer?: MapNewsItem[];
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
  markerTone: "red" | "amber" | "blue" | "slate";
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
  USA:    { left: "22%",   top: "42%" },
  Europe: { left: "48%",   top: "36%" },
  Asia:   { left: "74%",   top: "40%" },
  Global: { left: "55%",   top: "55%" },
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

function formatPct(value: number) {
  if (!Number.isFinite(value)) return "N/A";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function tonePillClass(tone: string) {
  if (tone === "risk-on") return "bg-emerald-500/10 text-emerald-700";
  if (tone === "risk-off") return "bg-red-500/10 text-red-700";
  return "bg-amber-500/10 text-amber-700";
}

function toneDotClass(tone: string) {
  if (tone === "risk-on") return "bg-emerald-600";
  if (tone === "risk-off") return "bg-red-600";
  return "bg-amber-600";
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
  return "border-slate-400/20 bg-slate-500/10 text-slate-700";
}

function markerAccentClass(tone: GeoEvent["markerTone"]) {
  if (tone === "red") return "bg-red-600";
  if (tone === "amber") return "bg-amber-500";
  if (tone === "blue") return "bg-blue-600";
  return "bg-slate-600";
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
  if (action === "short") return "Risk";
  if (action === "hedge") return "Protect";
  return "Watch";
}

function describeEventVariant(event: GeoEvent | null) {
  if (!event) return null;
  const title = `${event.title || ""} ${(event.region || "").toLowerCase()}`.toLowerCase();
  const eventType = (event.event_type || "").toLowerCase();

  if (eventType === "conflict") {
    if (/(iran|tehran|israel|gaza|lebanon|beirut|red sea)/.test(title)) return "Middle East conflict";
    if (/(ukraine|kyiv|russia|moscow)/.test(title)) return "Eastern Europe conflict";
    if (/(taiwan|china sea|korea)/.test(title)) return "Asia-Pacific conflict";
    return "Global conflict";
  }
  if (eventType === "energy") {
    if (/(opec|saudi|gulf|middle east|brent|crude)/.test(title)) return "Oil supply shock";
    if (/(gas|lng|pipeline)/.test(title)) return "Gas and transport stress";
    return "Energy repricing";
  }
  if (eventType === "election") {
    if (/(hungary|budapest|europe|eu|parliament)/.test(title)) return "European election";
    if (/(usa|u.s.|washington|president)/.test(title)) return "US election";
    return "Political vote";
  }
  if (eventType === "policy") {
    if (/(tariff|trade|sanction)/.test(title)) return "Trade and sanctions";
    if (/(regulation|policy)/.test(title)) return "Policy regime shift";
    return "Policy shock";
  }
  if (eventType === "disaster") {
    return "Natural disaster";
  }
  if (eventType === "central_bank") {
    return "Central bank shift";
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
      label: item.label || "Portfolio hedge",
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
    add("GLD", "Gold hedge");
    add("XLE", "Energy cushion");
    add("TLT", "Rates hedge");
  }
  if (eventType === "energy" || sectors.some((item) => item.includes("energy"))) {
    add("XLE", "Energy leaders");
    add("USO", "Oil follow-through");
  }
  if (eventType === "central_bank") {
    add("TLT", "Duration watch");
    add("UUP", "Dollar hedge");
    add("QQQ", "Growth reaction");
  }
  if (eventType === "election" || eventType === "policy") {
    add("XLI", "Industrials");
    add("ITA", "Defense");
    add("XLF", "Banks");
  }
  if (eventType === "disaster") {
    add("GLD", "Shock hedge");
    add("DBA", "Commodity stress");
  }
  if (assets.includes("GLD")) add("GLD", "Gold hedge");
  if (assets.includes("TLT")) add("TLT", "Duration hedge");
  if (assets.includes("XLE")) add("XLE", "Energy hedge");
  if (assets.includes("SPY")) add("SPY", "Index reaction");

  return Array.from(ideas.values()).slice(0, 4);
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

function decisionToneClass(value?: string) {
  if (value === "high conviction") return "bg-emerald-500/10 text-emerald-700";
  if (value === "selective") return "bg-sky-500/10 text-sky-700";
  if (value === "tactical only") return "bg-amber-500/10 text-amber-700";
  return "bg-slate-500/10 text-slate-600";
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

function resolveGeoAnchor(haystack: string, regionKey: GeoEvent["regionKey"], markerIcon: string): MapAnchor {
  const matched = geoAnchors.find((entry) => entry.terms.some((term) => haystack.includes(term)));
  if (matched) return matched.anchor;
  if (markerIcon === "OIL") return { left: "55.8%", top: "46.6%" };
  if (markerIcon === "VOTE" && regionKey === "Europe") return { left: "50.5%", top: "36.5%" };
  if (markerIcon === "WAR" && regionKey === "Europe") return { left: "53.4%", top: "34.7%" };
  if (markerIcon === "CB" && regionKey === "USA") return { left: "23%", top: "41.5%" };
  return markerLayout[regionKey];
}

function expandConflictAnchors(haystack: string): MapAnchor[] {
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
  const geoZone = inferGeoZone(haystack, regionKey);
  const geoPlace = inferGeoPlace(haystack, regionKey);
  const pulse = item.impact === "high";

  if (/(war|missile|attack|iran|israel|russia|ukraine|lebanon|beirut|conflict)/.test(haystack)) {
    const anchors = expandConflictAnchors(haystack);
    const finalAnchors = anchors.length ? anchors : [resolveGeoAnchor(haystack, regionKey, "WAR")];
    return finalAnchors.map((anchor, index) => ({
      ...item,
      geoKey: `${item.title || "conflict"}-${index}`,
      markerLabel: "Conflict",
      markerTone: "red",
      markerIcon: "WAR",
      pulse,
      geoZone,
      geoPlace,
      regionKey: anchor.left === "53.4%" ? "Europe" : anchor.left === "56.8%" || anchor.left === "52.6%" || anchor.left === "52.8%" ? "Global" : regionKey,
      markerPosition: anchor,
    }));
  }
  if (/(fed|ecb|boj|central bank|rate|yield)/.test(haystack)) {
    return [{
      ...item,
      markerLabel: "Central Bank",
      markerTone: "blue",
      markerIcon: "CB",
      pulse,
      geoZone,
      geoPlace,
      regionKey,
      markerPosition: resolveGeoAnchor(haystack, regionKey === "Global" ? "USA" : regionKey, "CB"),
    }];
  }
  if (/(oil|opec|crude|gas|energy)/.test(haystack)) {
    return [{
      ...item,
      markerLabel: "Energy",
      markerTone: "amber",
      markerIcon: "OIL",
      pulse: item.impact !== "low",
      geoZone,
      geoPlace,
      regionKey,
      markerPosition: resolveGeoAnchor(haystack, regionKey, "OIL"),
    }];
  }
  if (/(election|vote|ballot|president|prime minister|parliament|coalition|campaign)/.test(haystack)) {
    return [{
      ...item,
      markerLabel: "Election",
      markerTone: "blue",
      markerIcon: "VOTE",
      pulse,
      geoZone,
      geoPlace,
      regionKey,
      markerPosition: resolveGeoAnchor(haystack, regionKey === "Global" ? "Europe" : regionKey, "VOTE"),
    }];
  }
  if (/(earthquake|wildfire|flood|storm|hurricane|typhoon|tsunami|drought|disaster)/.test(haystack)) {
    return [{
      ...item,
      markerLabel: "Disaster",
      markerTone: "red",
      markerIcon: "NAT",
      pulse,
      geoZone,
      geoPlace,
      regionKey,
      markerPosition: resolveGeoAnchor(haystack, regionKey === "Global" ? "Asia" : regionKey, "NAT"),
    }];
  }
  if (/(tariff|sanction|trade|policy|regulation)/.test(haystack)) {
    return [{
      ...item,
      markerLabel: "Policy",
      markerTone: "slate",
      markerIcon: "POL",
      pulse,
      geoZone,
      geoPlace,
      regionKey,
      markerPosition: resolveGeoAnchor(haystack, regionKey === "Global" ? "USA" : regionKey, "POL"),
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
        stage: index === 0 ? "Asia close" : index === 1 ? "Europe handoff" : "US open",
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
  news = [],
  eventLayer = [],
  watchlistImpact = [],
  contrarianSignals = [],
  openingTimeline = [],
  onAnalyze,
  focusTicker,
}: WorldMarketMapProps) {
  const [activeFilter, setActiveFilter] = useState<EventFilter>("all");
  const [sortMode, setSortMode] = useState<EventSort>("impact");
  const [timeLens, setTimeLens] = useState<TimeLens>("24h");
  const [showLegend, setShowLegend] = useState(true);
  const [showRegionCards, setShowRegionCards] = useState(true);
  const [showLiveAlert, setShowLiveAlert] = useState(true);
  const [showEventLayer, setShowEventLayer] = useState(true);
  const [selectedGeoPlace, setSelectedGeoPlace] = useState<string | null>(null);
  const [pinnedEventIndex, setPinnedEventIndex] = useState(0);
  const [hoveredEventIndex, setHoveredEventIndex] = useState<number | null>(null);
  const [hoveredRegionLabel, setHoveredRegionLabel] = useState<string | null>(null);
  const activeRegion =
    regions.find((region) => region.label === selectedRegion) || regions[0] || null;
  const displayRegion =
    regions.find((region) => region.label === hoveredRegionLabel) || activeRegion;

  const activeRegionNews = useMemo(
    () => (activeRegion ? getRegionNews(news, activeRegion.label).slice(0, 4) : []),
    [activeRegion, news],
  );

  const geoSignals = useMemo(
    () =>
      (eventLayer.length ? eventLayer : news)
        .flatMap(classifyGeoEvents)
        .filter((item) => item!.impact === "high" || item!.impact === "medium")
        .sort((a, b) => {
          const impactRank = { high: 0, medium: 1, low: 2 };
          return (impactRank[a!.impact as keyof typeof impactRank] ?? 3) - (impactRank[b!.impact as keyof typeof impactRank] ?? 3);
        })
        .slice(0, 12) as GeoEvent[],
    [eventLayer, news],
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
      (a, b) =>
        (impactRank[a.impact as keyof typeof impactRank] ?? 3) -
        (impactRank[b.impact as keyof typeof impactRank] ?? 3),
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
      { x: 8, y: -5 },
      { x: -8, y: -5 },
      { x: 10, y: 7 },
      { x: -10, y: 7 },
      { x: 0, y: 11 },
    ];
    return orderedGeoSignals.slice(0, 6).map((item) => {
      const baseOffset = markerOffsets[item.regionKey]?.[item.markerIcon] || { x: 0, y: 0 };
      const hash = stableHash(item.geoKey || item.title || item.markerIcon);
      const orbit = orbitOffsets[hash % orbitOffsets.length];
      return {
        ...item,
        adjustedStyle: {
          left: `calc(${item.markerPosition.left} + ${baseOffset.x + orbit.x}px)`,
          top: `calc(${item.markerPosition.top} + ${baseOffset.y + orbit.y}px)`,
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

  const activeVariantLabel = useMemo(
    () => describeEventVariant(activeGeoEvent),
    [activeGeoEvent],
  );

  const whyItMatters = useMemo(() => {
    const lines: string[] = [];
    const relevantEvent =
      activeGeoEvent ||
      positionedGeoSignals.find((item) =>
        activeRegion ? item.regionKey.toLowerCase() === activeRegion.label.toLowerCase() || item.regionKey === "Global" : true,
      );
    if (relevantEvent?.title) lines.push(`${relevantEvent.markerLabel}: ${relevantEvent.title}`);
    if (relevantEvent?.event_intelligence?.why_now) {
      lines.push(`Why now: ${relevantEvent.event_intelligence.why_now}`);
    }
    if (activeRegionNews[0]?.title) lines.push(`Regional driver: ${activeRegionNews[0].title}`);
    if (focusTicker) {
      const impacted = watchlistImpact.find((item) => (item.ticker || "").toUpperCase() === focusTicker.toUpperCase());
      if (impacted?.summary) {
        lines.push(`${focusTicker}: ${impacted.summary}`);
      } else if (activeRegion?.assets?.some((asset) => asset.ticker?.toUpperCase() === focusTicker.toUpperCase())) {
        lines.push(`${focusTicker}: direkt mit ${activeRegion.label} verknuepft und damit exposed to den aktiven Makro-Block.`);
      }
    }
    if (regionalContrarian[0]?.ticker && regionalContrarian[0]?.reason) {
      lines.push(`Contrarian setup: ${regionalContrarian[0].ticker} | ${regionalContrarian[0].reason}`);
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

  return (
    <section className="surface-panel relative overflow-hidden rounded-[2.5rem] p-6 sm:p-8">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(15,118,110,0.08),transparent_30%),radial-gradient(circle_at_bottom_right,rgba(37,99,235,0.06),transparent_26%)]" />

      <div className="relative space-y-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="text-[11px] font-extrabold uppercase tracking-[0.24em] text-slate-500">
              Market Map
            </div>
            <h3 className="mt-2 text-4xl text-slate-900">Overnight world flow</h3>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600">
              Regionen, Makro-Ton, geopolitische Events und der Hand-off bis zur US-Eroeffnung
              in einer kompakten Macro-Ansicht.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {regions.map((region) => (
              <button
                key={region.label}
                onClick={() => onSelectRegion(region.label)}
                className={`rounded-full px-4 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] transition-all ${
                  selectedRegion === region.label
                    ? "bg-[var(--accent)] text-white shadow-[0_16px_34px_rgba(15,118,110,0.18)]"
                    : "border border-black/8 bg-white/70 text-slate-500"
                }`}
              >
                {region.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {[
            { key: "all", label: "All" },
            { key: "WAR", label: "War" },
            { key: "VOTE", label: "Election" },
            { key: "OIL", label: "Oil" },
            { key: "CB", label: "CB" },
            { key: "NAT", label: "Disaster" },
            { key: "POL", label: "Policy" },
          ].map((item) => (
            <button
              key={item.key}
              onClick={() => setActiveFilter(item.key as EventFilter)}
              className={`rounded-full px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] transition-all ${
                activeFilter === item.key
                  ? "bg-[#101114] text-white shadow-[0_10px_24px_rgba(15,23,42,0.12)]"
                  : "border border-black/8 bg-white/70 text-slate-500"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 rounded-[1.2rem] border border-black/8 bg-white/70 px-3 py-2">
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
              Sort
            </div>
            {[ 
              { key: "impact", label: "Impact" },
              { key: "region", label: "Region" },
              { key: "latest", label: "Latest" },
            ].map((item) => (
              <button
                key={item.key}
                onClick={() => setSortMode(item.key as EventSort)}
                className={`rounded-full px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] transition-all ${
                  sortMode === item.key
                    ? "bg-[var(--accent)] text-white"
                    : "border border-black/8 bg-white text-slate-500"
                }`}
              >
                {item.label}
              </button>
            ))}
            <span className="ml-1 rounded-full border border-black/8 bg-white px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
              {mapSignalSummary.total} events
            </span>
            <span className="rounded-full border border-red-500/12 bg-red-500/6 px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] text-red-700">
              {mapSignalSummary.highImpact} high
            </span>
            <span className="rounded-full border border-emerald-500/12 bg-emerald-500/6 px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] text-emerald-700">
              {mapSignalSummary.actionable} active setups
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
              Lens
            </div>
            {[
              { key: "live", label: "Live" },
              { key: "24h", label: "24h" },
              { key: "7d", label: "7d" },
            ].map((item) => (
              <button
                key={item.key}
                onClick={() => setTimeLens(item.key as TimeLens)}
                className={`rounded-full px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] transition-all ${
                  timeLens === item.key
                    ? "bg-[var(--accent)] text-white"
                    : "border border-black/8 bg-white text-slate-500"
                }`}
              >
                {item.label}
              </button>
            ))}
            {[
              { key: "legend", label: "Legend", value: showLegend, set: setShowLegend },
              { key: "regions", label: "Regions", value: showRegionCards, set: setShowRegionCards },
              { key: "alert", label: "Live alert", value: showLiveAlert, set: setShowLiveAlert },
              { key: "layer", label: "Event layer", value: showEventLayer, set: setShowEventLayer },
            ].map((item) => (
              <button
                key={item.key}
                onClick={() => item.set(!item.value)}
                className={`rounded-full px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] transition-all ${
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

        <div className="grid items-start gap-5 xl:grid-cols-[1.68fr_0.32fr]">
          <div className="relative self-start min-h-[360px] lg:min-h-[410px] xl:min-h-[430px] overflow-hidden rounded-[2rem] border border-black/8 bg-[linear-gradient(180deg,rgba(255,255,255,0.94),rgba(244,240,232,0.96))] p-4 sm:p-5">
            <div className="absolute inset-0 overflow-hidden opacity-80">
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.72),transparent_30%),radial-gradient(circle_at_bottom_right,rgba(239,233,223,0.58),transparent_28%)]" />
              <img
                src={worldMapSvg}
                alt="World map"
                className="absolute inset-0 block opacity-95 contrast-[1.05] saturate-[0.85]"
                style={{
                  width: "100%",
                  height: "100%",
                  maxWidth: "100%",
                  maxHeight: "100%",
                  objectFit: "contain",
                  objectPosition: "50% 58%",
                }}
                draggable={false}
              />
            </div>

            {showLegend ? (
            <div className="absolute bottom-4 left-4 z-30 flex max-w-[20rem] flex-wrap gap-2 rounded-[1rem] border border-black/8 bg-white/92 px-3 py-2 shadow-[0_10px_24px_rgba(15,23,42,0.08)]">
              {[
                { icon: "WAR", label: "Conflict", tone: "red" as const },
                { icon: "CB", label: "Central Bank", tone: "blue" as const },
                { icon: "OIL", label: "Energy", tone: "amber" as const },
                { icon: "VOTE", label: "Election", tone: "blue" as const },
                { icon: "NAT", label: "Disaster", tone: "red" as const },
                { icon: "POL", label: "Policy", tone: "slate" as const },
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
              <div className="absolute left-4 top-4 z-30 max-w-[18rem] rounded-[1.1rem] border border-black/8 bg-white/94 px-4 py-3 shadow-[0_14px_30px_rgba(15,23,42,0.1)]">
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
              </div>
            ) : null}

            {showRegionCards ? regions.map((region) => {
              const pos = positions[region.label];
              if (!pos) return null;
              const isActive = region.label === selectedRegion;

              return (
                <button
                  key={region.label}
                  type="button"
                  onClick={() => onSelectRegion(region.label)}
                  onMouseEnter={() => setHoveredRegionLabel(region.label)}
                  onMouseLeave={() => setHoveredRegionLabel(null)}
                  onFocus={() => setHoveredRegionLabel(region.label)}
                  onBlur={() => setHoveredRegionLabel(null)}
                  className="absolute z-20 text-left group"
                  style={{ left: `${pos.x}%`, top: `${pos.y}%` }}
                >
                  <div className="relative">
                    <div className="absolute -left-5 -top-5">
                      <div
                        className={`rounded-full ${toneDotClass(region.tone)} ${isActive ? "h-10 w-10 opacity-20 blur-md" : "h-8 w-8 opacity-15 blur-sm"}`}
                      />
                    </div>
                    <div
                      className={`h-3.5 w-3.5 rounded-full ${toneDotClass(region.tone)} ring-4 ring-white/80 shadow-[0_6px_24px_rgba(15,23,42,0.18)] ${isActive ? "scale-125" : ""}`}
                    />
                    <div
                      className="absolute top-1/2 h-px w-16 bg-slate-400/55"
                      style={{
                        width: `${pos.lineLength}px`,
                        ...(pos.align === "left" ? { left: 16 } : { right: 16 }),
                      }}
                    />
                    <div
                      className={`absolute top-1/2 -translate-y-1/2 rounded-[1rem] border p-2.5 backdrop-blur transition-all ${
                        isActive
                          ? "pointer-events-auto opacity-100 border-black/12 bg-white/94 shadow-[0_20px_40px_rgba(15,23,42,0.12)]"
                          : "pointer-events-none opacity-0 scale-[0.98] border-black/8 bg-white/82 shadow-[0_14px_34px_rgba(15,23,42,0.08)] group-hover:pointer-events-auto group-hover:opacity-100 group-hover:scale-100 group-focus-visible:pointer-events-auto group-focus-visible:opacity-100 group-focus-visible:scale-100"
                      }`}
                      style={{
                        width: `${pos.cardWidth}px`,
                        marginTop: `${pos.cardOffsetY}px`,
                        ...(pos.align === "left"
                          ? { left: `${pos.cardOffsetX}px` }
                          : { right: `${pos.cardOffsetX}px` }),
                      }}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-[10px] font-extrabold uppercase tracking-[0.2em] text-slate-500">
                          {region.label}
                        </div>
                        <div
                          className={`rounded-full px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.16em] ${tonePillClass(region.tone)}`}
                        >
                          {region.tone}
                        </div>
                      </div>
                      <div className={`mt-2 text-sm font-black ${textToneClass(region.tone)}`}>
                        {formatPct(region.avg_change_1d)}
                      </div>
                      <div className="mt-1.5 text-[10px] leading-4 text-slate-500">
                        {(region.assets || []).slice(0, 2).map((asset) => asset.label).join(" | ") || "Macro mix"}
                      </div>
                    </div>
                    {!isActive ? (
                      <div className="pointer-events-none absolute top-1/2 hidden -translate-y-1/2 rounded-full border border-black/8 bg-white/90 px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.16em] text-slate-500 shadow-[0_10px_24px_rgba(15,23,42,0.08)] group-hover:block group-focus-visible:block"
                        style={pos.align === "left" ? { left: `${pos.cardOffsetX - 2}px` } : { right: `${pos.cardOffsetX - 2}px` }}
                      >
                        {region.label}
                      </div>
                    ) : null}
                  </div>
                </button>
              );
            }) : null}

            {positionedGeoSignals.map((item, index) => (
              <a
                key={item.geoKey || `${item.title}-${index}`}
                className={`absolute z-10 group transition-opacity ${
                  isRegionFocusMatch(activeRegion?.label, item) &&
                  (!selectedGeoPlace || item.geoPlace === selectedGeoPlace)
                    ? "opacity-100"
                    : "opacity-25 hover:opacity-70"
                }`}
                style={item.adjustedStyle}
                href={item.link}
                target="_blank"
                rel="noreferrer"
                title={item.title}
                onMouseEnter={() => setHoveredEventIndex(index)}
                onMouseLeave={() => setHoveredEventIndex(null)}
                onFocus={() => setHoveredEventIndex(index)}
                onBlur={() => setHoveredEventIndex(null)}
                onClick={() => setPinnedEventIndex(index)}
              >
                <div className="relative">
                  {item.pulse && (
                    <div className={`absolute inset-0 rounded-full opacity-25 blur-sm ${markerAccentClass(item.markerTone)} animate-ping`} />
                  )}
                  <div
                    className={`relative flex items-center gap-1.5 rounded-full border px-1.5 py-1 text-[9px] font-extrabold uppercase tracking-[0.16em] shadow-[0_10px_24px_rgba(15,23,42,0.12)] ${markerClass(item.markerTone)} ${pinnedEventIndex === index ? "ring-2 ring-white/90" : ""} ${
                      isRegionFocusMatch(activeRegion?.label, item) ? "scale-100" : "scale-[0.94]"
                    }`}
                  >
                    <span className={`h-1.5 w-1.5 rounded-full ${markerAccentClass(item.markerTone)}`} />
                    <span>{item.markerIcon}</span>
                  </div>
                  <div className="pointer-events-none absolute left-1/2 top-full z-10 mt-2 w-72 -translate-x-1/2 rounded-[1rem] border border-black/8 bg-white/96 p-3 text-left opacity-0 shadow-[0_16px_34px_rgba(15,23,42,0.14)] transition-all duration-150 group-hover:opacity-100 group-focus-within:opacity-100">
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
              </a>
            ))}

            {showLiveAlert && activePulseEvent && hoveredEventIndex == null ? (
              <a
                href={activePulseEvent.link}
                target="_blank"
                rel="noreferrer"
                className="absolute right-4 bottom-4 z-30 max-w-[15rem] rounded-[1rem] border border-black/8 bg-white/94 p-3 shadow-[0_12px_28px_rgba(15,23,42,0.1)]"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.14em] ${markerClass(activePulseEvent.markerTone)}`}>
                    <span className={`h-2 w-2 rounded-full ${markerAccentClass(activePulseEvent.markerTone)}`} />
                    Live alert
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
              </a>
            ) : null}
          </div>

          <div className="space-y-3">
            <div className="rounded-[1.5rem] border border-black/8 bg-white/85 p-4">
              <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                Map Status
              </div>
              <div className="mt-3 grid gap-2 text-xs text-slate-500 sm:grid-cols-3 xl:grid-cols-1">
                <div className="rounded-[0.9rem] border border-black/8 bg-white/75 px-3 py-2">
                  Events <span className="font-bold text-slate-900">{mapSignalSummary.total}</span>
                </div>
                <div className="rounded-[0.9rem] border border-black/8 bg-white/75 px-3 py-2">
                  High impact <span className="font-bold text-slate-900">{mapSignalSummary.highImpact}</span>
                </div>
                <div className="rounded-[0.9rem] border border-black/8 bg-white/75 px-3 py-2">
                  Actionable <span className="font-bold text-slate-900">{mapSignalSummary.actionable}</span>
                </div>
              </div>
            </div>

            {displayRegion && (
              <div className="rounded-[1.5rem] border border-black/8 bg-white/85 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                      Region Focus
                    </div>
                    <div className="mt-2 text-xl font-black text-slate-900">
                      {displayRegion.label}
                    </div>
                  </div>
                  <div
                    className={`rounded-full px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.16em] ${tonePillClass(displayRegion.tone)}`}
                  >
                    {displayRegion.tone}
                  </div>
                </div>
                <div className={`mt-3 text-2xl font-black ${textToneClass(displayRegion.tone)}`}>
                  {formatPct(displayRegion.avg_change_1d)}
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
                        Clear
                      </button>
                    ) : null}
                  </div>
                ) : null}
                {regionDrilldown.placeHeat.length ? (
                  <div className="mt-4 space-y-2">
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                      Country Heat
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
                            <span>{item.events} events</span>
                            <span>|</span>
                            <span>{item.actionable} actionable</span>
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
                    Region Drilldown
                  </div>
                  <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-400">
                    {displayRegion.label}
                  </div>
                </div>
                <div className="mt-3 grid gap-2 text-xs text-slate-500 sm:grid-cols-3 xl:grid-cols-1">
                  <div className="rounded-[0.9rem] border border-black/8 bg-white/75 px-3 py-2">
                    Events <span className="font-bold text-slate-900">{regionDrilldown.total}</span>
                  </div>
                  <div className="rounded-[0.9rem] border border-black/8 bg-white/75 px-3 py-2">
                    High impact <span className="font-bold text-slate-900">{regionDrilldown.highImpact}</span>
                  </div>
                  <div className="rounded-[0.9rem] border border-black/8 bg-white/75 px-3 py-2">
                    Actionable <span className="font-bold text-slate-900">{regionDrilldown.actionable}</span>
                  </div>
                </div>
                <div className="mt-4 space-y-2">
                  {selectedGeoPlace ? (
                    <div className="rounded-[0.9rem] border border-[var(--accent)]/12 bg-[var(--accent-soft)] px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.14em] text-[var(--accent)]">
                      Place focus: {selectedGeoPlace}
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
                            {freshnessLabel(item.event_intelligence?.decay, item.pulse)}
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
                      Kein dominanter Drilldown fuer {displayRegion.label} im aktuellen Filter.
                    </div>
                  )}
                </div>
              </div>
            ) : null}

            {activeGeoEvent ? (
              <div className="rounded-[1.5rem] border border-black/8 bg-white/85 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                    Event Decision
                  </div>
                  <div className={`rounded-full border px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.16em] ${markerClass(activeGeoEvent.markerTone)}`}>
                    {activeGeoEvent.markerIcon}
                  </div>
                </div>
                <div className="mt-3 line-clamp-3 text-sm font-bold leading-6 text-slate-900">
                  {activeGeoEvent.title}
                </div>
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
                    {freshnessLabel(activeGeoEvent.event_intelligence?.decay, activeGeoEvent.pulse)}
                  </span>
                  {activeGeoEvent.event_intelligence?.leverage ? (
                    <span className="rounded-full border border-black/8 bg-white px-2 py-1">
                      leverage {activeGeoEvent.event_intelligence.leverage}
                    </span>
                  ) : null}
                  {activeGeoEvent.event_intelligence?.decision_quality ? (
                    <span className={`rounded-full px-2 py-1 ${decisionToneClass(activeGeoEvent.event_intelligence.decision_quality)}`}>
                      {activeGeoEvent.event_intelligence.decision_quality}
                    </span>
                  ) : null}
                </div>
                {activeGeoEvent.event_intelligence ? (
                  <div className="mt-3 grid gap-2 text-xs text-slate-500 sm:grid-cols-3">
                    <div className="rounded-[0.9rem] border border-black/8 bg-white/75 px-3 py-2">
                      Impact <span className="font-bold text-slate-900">{activeGeoEvent.event_intelligence.impact_score}</span>
                    </div>
                    <div className="rounded-[0.9rem] border border-black/8 bg-white/75 px-3 py-2">
                      Confidence <span className="font-bold text-slate-900">{activeGeoEvent.event_intelligence.confidence_score}</span>
                    </div>
                    <div className="rounded-[0.9rem] border border-black/8 bg-white/75 px-3 py-2">
                      Decay <span className="font-bold uppercase text-slate-900">{activeGeoEvent.event_intelligence.decay}</span>
                    </div>
                  </div>
                ) : null}
                {compactList(activeGeoEvent.event_intelligence?.affected_sectors).length ? (
                  <div className="mt-3">
                    <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                      Sector Impact
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
                      Affected Assets
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
                          {activeGeoEvent.portfolio_exposure.exposure_strength} exposure
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
                      Hedge Ideas
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
                      Bias: {activeGeoEvent.event_intelligence.execution_bias} | Size: {activeGeoEvent.event_intelligence.size_guidance}
                    </div>
                  ) : null}
                  {activeGeoEvent.event_intelligence?.trigger ? (
                    <div className="rounded-[0.9rem] border border-black/8 bg-white/75 px-3 py-2 text-xs leading-6 text-slate-600">
                      Trigger: {activeGeoEvent.event_intelligence.trigger}
                    </div>
                  ) : null}
                  {activeGeoEvent.event_intelligence?.invalidation ? (
                    <div className="rounded-[0.9rem] border border-black/8 bg-white/75 px-3 py-2 text-xs leading-6 text-slate-600">
                      Invalidation: {activeGeoEvent.event_intelligence.invalidation}
                    </div>
                  ) : null}
                </div>
                {activeGeoEvent.event_intelligence?.execution_window ? (
                  <div className="mt-2 text-[11px] font-bold uppercase tracking-[0.14em] text-slate-500">
                    Window: {activeGeoEvent.event_intelligence.execution_window}
                  </div>
                ) : null}
              </div>
            ) : null}

            <div className="rounded-[1.5rem] border border-black/8 bg-[linear-gradient(180deg,rgba(15,118,110,0.07),rgba(255,255,255,0.88))] p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                  Why it matters
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
                    Der aktive Welt- und Makroblock wird geladen. Sobald neue Events klassifiziert sind, erscheint hier die direkte Relevanz fuer Region, Risiko und moegliche Marktreaktion.
                  </div>
                )}
              </div>
            </div>

            <div className="rounded-[1.5rem] border border-black/8 bg-white/85 p-4">
              <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                Event Layer
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-3">
                <div className="rounded-[0.9rem] border border-black/8 bg-white/75 px-3 py-2 text-xs text-slate-500">
                  New <span className="font-bold text-slate-900">{eventTempo.developing}</span>
                </div>
                <div className="rounded-[0.9rem] border border-black/8 bg-white/75 px-3 py-2 text-xs text-slate-500">
                  Active <span className="font-bold text-slate-900">{eventTempo.active}</span>
                </div>
                <div className="rounded-[0.9rem] border border-black/8 bg-white/75 px-3 py-2 text-xs text-slate-500">
                  Fading <span className="font-bold text-slate-900">{eventTempo.fading}</span>
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
                            {freshnessLabel(item.event_intelligence?.decay, item.pulse)}
                          </span>
                        </div>
                      </div>
                      <div className="mt-2 line-clamp-2 text-sm font-bold text-slate-900">{item.title}</div>
                      {item.event_intelligence ? (
                        <div className="mt-3 space-y-2 text-xs text-slate-500">
                          <div className="flex flex-wrap gap-2">
                            <span>Impact {item.event_intelligence.impact_score}</span>
                            <span>Confidence {item.event_intelligence.confidence_score}</span>
                            <span>{item.event_intelligence.decay}</span>
                          </div>
                          <div className="line-clamp-2">
                            Action: {item.event_intelligence.action} | Leverage {item.event_intelligence.leverage}
                          </div>
                          {item.event_intelligence.decision_quality ? (
                            <div className="flex flex-wrap gap-2">
                              <span className={`rounded-full px-2 py-1 text-[9px] font-extrabold uppercase tracking-[0.14em] ${decisionToneClass(item.event_intelligence.decision_quality)}`}>
                                {item.event_intelligence.decision_quality}
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
                      ? `Keine dominanten Events im aktuellen Filter${selectedGeoPlace ? ` fuer ${selectedGeoPlace}` : ""} fuer ${timeLens}.`
                      : "Event Layer ist ausgeblendet."}
                  </div>
                )}
              </div>
            </div>

            <div className="rounded-[1.5rem] border border-black/8 bg-white/85 p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
                  Contrarian Radar
                </div>
                <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-400">
                  media fade
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

        <div className="grid gap-4 md:grid-cols-3">
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
                  {item.tone}
                </div>
              </div>
              <div className={`mt-3 text-2xl font-black ${textToneClass(item.tone)}`}>
                {formatPct(item.move)}
              </div>
              <div className="mt-2 text-sm leading-6 text-slate-600">{item.driver}</div>
            </div>
          ))}
        </div>

        <div className="rounded-[1.6rem] border border-black/8 bg-white/80 p-4">
          <div className="flex items-center justify-between gap-3">
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-slate-500">
              Event Replay
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
    </section>
  );
}
