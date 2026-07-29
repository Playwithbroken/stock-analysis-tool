const GERMAN_ASCII_WORDS: Record<string, string> = {
  fuer: "für",
  ueber: "über",
  pruefen: "prüfen",
  prueft: "prüft",
  geprueft: "geprüft",
  bestaetigen: "bestätigen",
  bestaetigt: "bestätigt",
  bestaetigung: "bestätigung",
  naechste: "nächste",
  naechster: "nächster",
  moeglich: "möglich",
  moegliche: "mögliche",
  faellt: "fällt",
  oeffnen: "öffnen",
  eroeffnung: "eröffnung",
  laedt: "lädt",
};

const REGIME_LABELS: Record<string, string> = {
  mixed: "Gemischt",
  neutral: "Neutral",
  normal: "Normal",
  "risk-on": "Risikofreudig",
  "risk off": "Risikoscheu",
  "risk-off": "Risikoscheu",
  defensive: "Defensiv",
  volatile: "Volatil",
  bullish: "Positiv",
  bearish: "Negativ",
};

const RESOLUTION_CONFIDENCE_LABELS: Record<string, string> = {
  high: "Hohe Sicherheit",
  medium: "Mittlere Sicherheit",
  low: "Niedrige Sicherheit",
  resolved: "Erfolgreich aufgelöst",
};

const ANALYSIS_LABELS: Record<string, string> = {
  "price performance": "Kursentwicklung",
  "volatility & risk": "Volatilität & Risiko",
  volatility: "Volatilität",
  fundamentals: "Fundamentaldaten",
  "fundamental analysis": "Fundamentalanalyse",
  "earnings quality": "Ergebnisqualität",
  "fear factors & risks": "Risikofaktoren",
  "opportunities & catalysts": "Chancen & Katalysatoren",
  "recent news": "Aktuelle Nachrichten",
  "news analysis": "Nachrichtenanalyse",
  "insider activity": "Insider-Aktivität",
  "peer benchmarking": "Vergleich mit Wettbewerbern",
  "potential analysis": "Potenzialanalyse",
  "rebound analysis": "Erholungsanalyse",
  "technical analysis": "Technische Analyse",
  "sentiment analysis": "Sentimentanalyse",
  "data state": "Datenstatus",
  "insufficient signal": "Signal unzureichend",
  coverage: "Datenabdeckung",
  partial: "Teilweise",
  confidence: "Belastbarkeit",
  low: "Niedrig",
  "current price": "Aktueller Kurs",
  "performance 1 week": "Performance 1 Woche",
  "performance 1 month": "Performance 1 Monat",
  "performance 6 months": "Performance 6 Monate",
  "performance 1 year": "Performance 1 Jahr",
  "from 52-week high": "Abstand zum 52-Wochen-Hoch",
  "from 52-week low": "Abstand zum 52-Wochen-Tief",
  "annualized volatility": "Annualisierte Volatilität",
  "volume ratio (vs avg)": "Volumenquote (zum Durchschnitt)",
  "p/e ratio": "KGV",
  "forward p/e": "Erwartetes KGV",
  "p/b ratio": "KBV",
  "profit margin": "Gewinnmarge",
  "return on equity": "Eigenkapitalrendite",
  "revenue growth": "Umsatzwachstum",
  "debt/equity": "Verschuldungsgrad",
  "free cash flow": "Freier Cashflow",
  "market cap": "Marktkapitalisierung",
  "short interest (% float)": "Leerverkaufsquote (% Streubesitz)",
  "days to cover": "Eindeckungsdauer",
  "high volatility": "Hohe Volatilität",
  "strong growth": "Starkes Wachstum",
  "high profitability": "Hohe Profitabilität",
  "net cash position": "Nettoliquidität",
  "insider buy (ceo)": "Insiderkauf (CEO)",
  "insider sell (cfo)": "Insiderverkauf (CFO)",
  "p/e relative to sector": "KGV im Branchenvergleich",
  "revenue growth vs sector": "Umsatzwachstum zur Branche",
  "reported eps": "Gemeldetes EPS",
  "eps estimate": "EPS-Schätzung",
  "eps surprise": "EPS-Abweichung",
  "4q pattern": "Muster der letzten 4 Quartale",
  "revenue yoy": "Umsatz zum Vorjahr",
  "forward eps": "Erwartetes EPS",
  "rev growth": "Umsatzwachstum",
  margin: "Marge",
  "fcf yield": "FCF-Rendite",
  "analyst upside": "Analystenpotenzial",
  "net debt": "Nettoverschuldung",
  met: "Erfüllt",
  missed: "Verfehlt",
  solid: "Solide",
  inline: "Im Rahmen",
  "in line": "Im Rahmen",
  beat: "Übertroffen",
  miss: "Verfehlt",
  unknown: "Unbekannt",
  "no signal": "Kein Signal",
  equity: "Aktie",
  etf: "ETF",
  crypto: "Krypto",
  medium: "Mittel",
  high: "Hoch",
  speculative: "Spekulativ",
  intermediate: "Fortgeschritten",
  beginner: "Einsteiger",
  advanced: "Sehr erfahren",
  "heavily undervalued": "Stark unterbewertet",
  undervalued: "Unterbewertet",
  "fairly valued": "Fair bewertet",
  overvalued: "Überbewertet",
  "heavily overvalued": "Stark überbewertet",
};

const ANALYSIS_TEXT: Record<string, string> = {
  "no data available": "Keine Daten verfügbar",
  "strong uptrend over the past year": "Starker Aufwärtstrend im vergangenen Jahr",
  "moderate positive performance": "Moderate positive Kursentwicklung",
  "sideways movement, no clear trend": "Seitwärtsbewegung ohne klaren Trend",
  "moderate decline over the past year": "Moderater Rückgang im vergangenen Jahr",
  "significant downtrend - caution advised": "Deutlicher Abwärtstrend – Vorsicht geboten",
  "high volatility stock - suitable for risk-tolerant investors": "Hohe Volatilität – nur für risikotolerante Anleger geeignet",
  "moderate volatility": "Moderate Volatilität",
  "relatively stable stock": "Relativ stabile Aktie",
  "strong fundamentals - quality company at reasonable valuation": "Starke Fundamentaldaten – Qualitätsunternehmen mit vertretbarer Bewertung",
  "earnings quality supports a stronger buy/accumulate case.": "Die Ergebnisqualität stützt einen stärkeren Kauf- beziehungsweise Aufbau-Case.",
  "mixed or neutral news sentiment": "Gemischte oder neutrale Nachrichtenstimmung",
  "slightly positive insider sentiment": "Leicht positive Insider-Stimmung",
  "competitive position within industry": "Wettbewerbsfähige Position innerhalb der Branche",
  "no clear guidance read": "Kein klares Ausblickssignal",
  "12,500 shares": "12.500 Aktien",
  "2,000 shares": "2.000 Aktien",
};

const RECOMMENDATION_ACTIONS: Record<string, string> = {
  "strong buy": "Stark kaufen",
  buy: "Kaufen",
  accumulate: "Aufbauen",
  "hold / accumulate": "Halten / Aufbauen",
  hold: "Halten",
  watch: "Beobachten",
  wait: "Abwarten",
  avoid: "Meiden",
  sell: "Verkaufen",
  "strong sell": "Stark verkaufen",
};

const SECTOR_LABELS: Record<string, string> = {
  "basic materials": "Grundstoffe",
  "communication services": "Kommunikationsdienste",
  "consumer cyclical": "Zyklischer Konsum",
  "consumer defensive": "Basiskonsumgüter",
  energy: "Energie",
  "financial services": "Finanzdienstleistungen",
  healthcare: "Gesundheitswesen",
  industrials: "Industrie",
  "real estate": "Immobilien",
  technology: "Technologie",
  utilities: "Versorger",
};

function preserveInitialCase(source: string, translated: string) {
  if (!source || source[0] !== source[0].toUpperCase()) return translated;
  return translated.charAt(0).toUpperCase() + translated.slice(1);
}

function sourceLabel(value: string) {
  const normalized = value.trim().toLowerCase().replace(/[\s-]+/g, "_");
  if (normalized === "morning_brief") return "Morning Briefing";
  if (normalized === "top_news") return "Top-Nachrichten";
  if (normalized === "signal_score") return "Signalbewertung";
  return value.replace(/[_-]+/g, " ").trim();
}

export function normalizeGermanDisplayText(value: unknown) {
  let text = String(value ?? "").trim();
  if (!text) return "";

  text = text.replace(/preisbestaetigung/gi, (word) => preserveInitialCase(word, "preisbestätigung"));
  text = text.replace(/positionsgroesse/gi, (word) => preserveInitialCase(word, "positionsgröße"));

  text = text.replace(
    /\b(fuer|ueber|pruefen|prueft|geprueft|bestaetigen|bestaetigt|bestaetigung|naechste|naechster|moeglich|moegliche|faellt|oeffnen|eroeffnung|laedt)\b/gi,
    (word) => preserveInitialCase(word, GERMAN_ASCII_WORDS[word.toLowerCase()] || word),
  );

  return text;
}

export function localizeMarketRegime(value: unknown) {
  const text = String(value ?? "").trim();
  if (!text) return "Neutral";
  return REGIME_LABELS[text.toLowerCase()] || normalizeGermanDisplayText(text);
}

export function localizeResolutionConfidence(value: unknown) {
  const text = String(value ?? "").trim();
  if (!text) return RESOLUTION_CONFIDENCE_LABELS.resolved;
  return RESOLUTION_CONFIDENCE_LABELS[text.toLowerCase()] || normalizeGermanDisplayText(text);
}

export function localizeAnalysisLabel(value: unknown) {
  const text = String(value ?? "").trim();
  if (!text) return "";
  return ANALYSIS_LABELS[text.toLowerCase()] || normalizeGermanDisplayText(text);
}

export function localizeAnalysisText(value: unknown) {
  const text = String(value ?? "").trim();
  if (!text) return "";

  const exact = ANALYSIS_TEXT[text.toLowerCase()];
  if (exact) return exact;

  const riskCount = text.match(/^Identified\s+(\d+)\s+significant risk factors?$/i);
  if (riskCount) {
    const count = Number(riskCount[1]);
    return `${count} wesentliche${count === 1 ? "r Risikofaktor" : " Risikofaktoren"} erkannt`;
  }

  const positiveCount = text.match(/^Identified\s+(\d+)\s+positive factors?$/i);
  if (positiveCount) {
    const count = Number(positiveCount[1]);
    return `${count} positive${count === 1 ? "r Faktor" : " Faktoren"} erkannt`;
  }

  return normalizeGermanDisplayText(text)
    .replace(/\b(\d+(?:[.,]\d+)?)\s+days?\b/gi, "$1 Tage")
    .replace(/\b(\d+(?:[.,]\d+)?)%\s+annual\b/gi, "$1% jährlich")
    .replace(/\brevenue growth\b/gi, "Umsatzwachstum")
    .replace(/\bprofit margin\b/gi, "Gewinnmarge")
    .replace(/\bnet cash\b/gi, "Nettoliquidität");
}

export function localizeRecommendationAction(value: unknown) {
  const text = String(value ?? "").trim();
  if (!text) return "";
  return RECOMMENDATION_ACTIONS[text.toLowerCase()] || normalizeGermanDisplayText(text);
}

export function localizeSector(value: unknown) {
  const text = String(value ?? "").trim();
  if (!text) return "";
  return SECTOR_LABELS[text.toLowerCase()] || normalizeGermanDisplayText(text);
}

export function localizeLearningMessage(value: unknown) {
  const text = String(value ?? "").trim();
  if (!text) return "";

  const outcome = text.match(
    /^(promote|demote|keep)\s+([^:]+):\s*([\d.,]+)%\s+hit rate across\s+(\d+)\s+evaluated outcomes\.?$/i,
  );
  if (outcome) {
    const [, direction, source, rate, count] = outcome;
    const action = direction.toLowerCase() === "promote"
      ? "ausbauen"
      : direction.toLowerCase() === "demote"
        ? "zurückstufen"
        : "beibehalten";
    return `${sourceLabel(source)} ${action}: ${rate.replace(".", ",")}% Trefferquote aus ${count} ausgewerteten Ergebnissen.`;
  }

  return normalizeGermanDisplayText(text);
}
