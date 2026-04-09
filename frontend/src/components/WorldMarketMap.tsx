import React, { useEffect, useMemo, useState } from "react";
import worldMapSvg from "../assets/world-map-wikimedia.svg";

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
  };
  portfolio_exposure?: {
    status?: string;
    note?: string;
    action?: string;
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
  markerPosition: { left: string; top: string };
}

interface MapAnchor {
  left: string;
  top: string;
}

type EventFilter = "all" | "WAR" | "CB" | "OIL" | "VOTE" | "NAT" | "POL";
type EventSort = "impact" | "region" | "latest";

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
  USA: { x: 18.5, y: 45.5, align: "left", cardWidth: 150, lineLength: 38, cardOffsetX: 52, cardOffsetY: -10 },
  Europe: { x: 48.5, y: 39.5, align: "right", cardWidth: 148, lineLength: 34, cardOffsetX: 44, cardOffsetY: -42 },
  Asia: { x: 73.5, y: 47.5, align: "right", cardWidth: 148, lineLength: 34, cardOffsetX: 44, cardOffsetY: -8 },
};

const regionKeywords: Record<string, string[]> = {
  USA: ["usa", "u.s.", "us ", "federal reserve", "fed", "washington", "wall street"],
  Europe: ["europe", "eu", "ecb", "france", "germany", "uk", "britain", "italy"],
  Asia: ["asia", "china", "japan", "hong kong", "taiwan", "korea", "india"],
};

const markerLayout = {
  USA: { left: "22%", top: "47%" },
  Europe: { left: "49.5%", top: "41.5%" },
  Asia: { left: "74%", top: "48.5%" },
  Global: { left: "58.5%", top: "60%" },
};

const geoAnchors: Array<{ terms: string[]; anchor: MapAnchor }> = [
  { terms: ["hungary", "budapest"], anchor: { left: "50.5%", top: "38%" } },
  { terms: ["ukraine", "kyiv", "odesa"], anchor: { left: "53.4%", top: "34.7%" } },
  { terms: ["poland", "warsaw"], anchor: { left: "49.5%", top: "34.5%" } },
  { terms: ["germany", "berlin"], anchor: { left: "46.5%", top: "33.5%" } },
  { terms: ["france", "paris"], anchor: { left: "44.5%", top: "35.5%" } },
  { terms: ["uk ", "britain", "london", "england"], anchor: { left: "42.5%", top: "31.5%" } },
  { terms: ["italy", "rome"], anchor: { left: "47.8%", top: "39.5%" } },
  { terms: ["turkey", "ankara"], anchor: { left: "51.8%", top: "39.4%" } },
  { terms: ["russia", "moscow"], anchor: { left: "57%", top: "28.5%" } },
  { terms: ["lebanon", "beirut"], anchor: { left: "52.6%", top: "41.1%" } },
  { terms: ["iran", "tehran"], anchor: { left: "56.8%", top: "42.2%" } },
  { terms: ["israel", "gaza", "jerusalem"], anchor: { left: "52.8%", top: "42.9%" } },
  { terms: ["saudi", "riyadh"], anchor: { left: "55.4%", top: "47.5%" } },
  { terms: ["opec", "oil", "crude", "middle east", "gulf", "red sea", "brent"], anchor: { left: "55.8%", top: "46.6%" } },
  { terms: ["india", "mumbai", "delhi"], anchor: { left: "65%", top: "48%" } },
  { terms: ["china", "beijing", "shanghai"], anchor: { left: "73%", top: "40%" } },
  { terms: ["taiwan", "taipei"], anchor: { left: "77.5%", top: "46.5%" } },
  { terms: ["japan", "tokyo"], anchor: { left: "83.5%", top: "40.5%" } },
  { terms: ["hong kong"], anchor: { left: "76%", top: "46%" } },
  { terms: ["korea", "seoul"], anchor: { left: "79.5%", top: "40.5%" } },
  { terms: ["australia", "sydney"], anchor: { left: "83%", top: "74%" } },
  { terms: ["usa", "u.s.", "washington", "wall street", "new york"], anchor: { left: "23%", top: "42%" } },
  { terms: ["california", "silicon valley"], anchor: { left: "16.5%", top: "45%" } },
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

function buildHedgeIdeas(event: GeoEvent | null) {
  if (!event) return [];
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
  const [showLegend, setShowLegend] = useState(true);
  const [showRegionCards, setShowRegionCards] = useState(true);
  const [showLiveAlert, setShowLiveAlert] = useState(true);
  const [showEventLayer, setShowEventLayer] = useState(true);
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
      geoSignals.filter((item) =>
        activeFilter === "all" ? true : item.markerIcon === activeFilter,
      ),
    [geoSignals, activeFilter],
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
    () => positionedGeoSignals.find((item) => item.pulse) || null,
    [positionedGeoSignals],
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

  const activeGeoEvent = useMemo(
    () =>
      (hoveredEventIndex != null ? positionedGeoSignals[hoveredEventIndex] : null) ||
      positionedGeoSignals[pinnedEventIndex] ||
      positionedGeoSignals[0] ||
      activePulseEvent ||
      null,
    [activePulseEvent, hoveredEventIndex, pinnedEventIndex, positionedGeoSignals],
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
                className="absolute inset-0 block opacity-90 contrast-[1.24] brightness-[0.97] saturate-[0.7] mix-blend-multiply"
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
                className="absolute z-10 group"
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
                    className={`relative flex items-center gap-1.5 rounded-full border px-1.5 py-1 text-[9px] font-extrabold uppercase tracking-[0.16em] shadow-[0_10px_24px_rgba(15,23,42,0.12)] ${markerClass(item.markerTone)} ${pinnedEventIndex === index ? "ring-2 ring-white/90" : ""}`}
                  >
                    <span className={`h-1.5 w-1.5 rounded-full ${markerAccentClass(item.markerTone)}`} />
                    <span>{item.markerIcon}</span>
                  </div>
                  <div className="pointer-events-none absolute left-1/2 top-full z-10 mt-2 w-72 -translate-x-1/2 rounded-[1rem] border border-black/8 bg-white/96 p-3 text-left opacity-0 shadow-[0_16px_34px_rgba(15,23,42,0.14)] transition-all duration-150 group-hover:opacity-100 group-focus-within:opacity-100">
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                        {item.region || "Global"}
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
                  {activeGeoEvent.event_intelligence?.leverage ? (
                    <span className="rounded-full border border-black/8 bg-white px-2 py-1">
                      leverage {activeGeoEvent.event_intelligence.leverage}
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
                    <div className="mt-2 flex flex-wrap gap-2">
                      {compactList(activeGeoEvent.event_intelligence?.affected_sectors).map((sector) => (
                        <span
                          key={sector}
                          className="rounded-full border border-black/8 bg-white px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-600"
                        >
                          {sector}
                        </span>
                      ))}
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
                    {activeGeoEvent.portfolio_exposure.note}
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
                          {idea.ticker} · {idea.label}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}
                <div className="mt-3 space-y-2">
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
                {showEventLayer && positionedGeoSignals.length ? (
                  positionedGeoSignals.slice(0, 4).map((item, index) => (
                    <a
                      key={item.geoKey || `${item.title}-${index}`}
                      href={item.link}
                      target="_blank"
                      rel="noreferrer"
                      onMouseEnter={() => setHoveredEventIndex(index)}
                      onMouseLeave={() => setHoveredEventIndex(null)}
                      onFocus={() => setHoveredEventIndex(index)}
                      onBlur={() => setHoveredEventIndex(null)}
                      onClick={() => setPinnedEventIndex(index)}
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
                        <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-slate-500">
                          {item.region || "Global"} | {item.impact || "macro"}
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
                          {item.portfolio_exposure.note}
                        </div>
                      ) : null}
                    </a>
                  ))
                ) : (
                  <div className="rounded-[1rem] border border-black/8 bg-white/75 p-3 text-sm text-slate-500">
                    {showEventLayer ? "Keine dominanten Events im aktuellen Filter." : "Event Layer ist ausgeblendet."}
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
      </div>
    </section>
  );
}
