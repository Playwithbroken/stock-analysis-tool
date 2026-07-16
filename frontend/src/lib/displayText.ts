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
