export interface AnalysisDataQuality {
  price_source?: string;
  degraded?: boolean;
  insufficient_signal?: boolean;
}

export const getAnalysisQualityState = (quality?: AnalysisDataQuality) => {
  if (quality?.insufficient_signal) {
    return {
      level: "insufficient" as const,
      label: "Daten unzureichend",
      title: "Keine belastbare Trade-Entscheidung",
      detail: "Kurs- oder Fundamentaldaten fehlen. Analyse erneut laden, bevor du Score, Trigger oder Positionsgroesse verwendest.",
      classes: "border-red-500/25 bg-red-500/10 text-red-900",
      badgeClasses: "bg-red-500/12 text-red-800",
      blocksDecision: true,
    };
  }
  if (quality?.degraded) {
    return {
      level: "degraded" as const,
      label: "Snapshot / Fallback",
      title: "Datensatz nur teilweise verfuegbar",
      detail: "Der schnelle Kurs-Snapshot ersetzt keinen vollstaendigen Abruf. Signale beobachten und vor einer Umsetzung erneut bestaetigen.",
      classes: "border-amber-500/30 bg-amber-500/10 text-amber-900",
      badgeClasses: "bg-amber-500/12 text-amber-800",
      blocksDecision: true,
    };
  }
  return {
    level: "full" as const,
    label: "Vollstaendiger Abruf",
    title: "Datensatz vollstaendig geladen",
    detail: "Kurs-, Fundamental- und Analysedaten wurden fuer dieses Dossier abgerufen.",
    classes: "border-emerald-500/20 bg-emerald-500/8 text-emerald-900",
    badgeClasses: "bg-emerald-500/10 text-emerald-800",
    blocksDecision: false,
  };
};

export const formatAnalysisFetchTime = (value?: string): string | null => {
  if (!value) return null;
  const parsed = new Date(value.replace(" ", "T"));
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" });
};
