export interface GeoRegionAsset {
  ticker: string;
  label: string;
  change_1d?: number | null;
}

export interface GeoRegionSummary {
  label: string;
  tone: string;
  avg_change_1d: number;
  assets: GeoRegionAsset[];
}

export const DEFAULT_GEO_REGIONS: GeoRegionSummary[] = [
  {
    label: "Asia",
    tone: "mixed",
    avg_change_1d: 0,
    assets: [{ ticker: "^N225", label: "Nikkei 225", change_1d: 0 }],
  },
  {
    label: "Europe",
    tone: "mixed",
    avg_change_1d: 0,
    assets: [{ ticker: "^GDAXI", label: "DAX", change_1d: 0 }],
  },
  {
    label: "USA",
    tone: "mixed",
    avg_change_1d: 0,
    assets: [{ ticker: "SPY", label: "S&P 500 ETF", change_1d: 0 }],
  },
];

export function normalizeGeoRegions(regions: unknown): GeoRegionSummary[] {
  const sourceRegions = regions && typeof regions === "object" && !Array.isArray(regions)
    ? regions as Record<string, any>
    : {};

  return DEFAULT_GEO_REGIONS.map((fallback) => {
    const key = fallback.label.toLowerCase();
    const source = sourceRegions[key] && typeof sourceRegions[key] === "object" && !Array.isArray(sourceRegions[key])
      ? sourceRegions[key]
      : {};
    const assets = Array.isArray(source.assets) && source.assets.length ? source.assets : fallback.assets;
    const change = Number(source.avg_change_1d ?? source.change_1d ?? fallback.avg_change_1d);

    return {
      ...fallback,
      ...source,
      label: source.label || fallback.label,
      tone: source.tone || fallback.tone,
      avg_change_1d: Number.isFinite(change) ? change : fallback.avg_change_1d,
      assets,
    };
  });
}
