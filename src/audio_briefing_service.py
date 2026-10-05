"""
Audio Briefing Service: Generates spoken voice memos & audio daily briefings
for Telegram broadcast using clean, conversational text synthesis.
"""
from __future__ import annotations

import io
import re
from datetime import datetime
from typing import Any, Dict, Optional, Tuple
import logging

try:
    from gtts import gTTS
    HAS_GTTS = True
except ImportError:
    HAS_GTTS = False

logger = logging.getLogger(__name__)


class AudioBriefingService:
    """
    Transforms morning briefings, macro warnings, and trading setups
    into crisp spoken German audio memos (MP3) ready for Telegram voice delivery.
    """

    def __init__(self, default_lang: str = "de") -> None:
        self.default_lang = default_lang

    @staticmethod
    def _clean_for_speech(text: str) -> str:
        """Cleans abbreviations, tickers, and symbols to ensure natural spoken German."""
        if not text:
            return ""

        # Remove HTML and Markdown tags
        t = re.sub(r"<[^>]+>", " ", text)
        t = re.sub(r"[*_`#~]", " ", t)

        # 1. Specific symbols and HTML entities
        t = t.replace("&amp;", " und ").replace("&", " und ")
        t = re.sub(r"(?<=\d)%", " Prozent", t)
        t = t.replace("%", " Prozent")
        t = re.sub(r"\s+-\s+", " minus ", t)
        t = re.sub(r"(?<=\s)-(\d+)", r"Minus \1", t)
        t = re.sub(r"\+(\d+)", r"Plus \1", t)

        # 2. Pronounceable ticker and acronym replacements with word boundaries
        word_replacements = {
            "SAP.DE": "S A P",
            "RHM.DE": "Rheinmetall",
            "SIE.DE": "Siemens",
            "ASML.AS": "A S M L",
            "NVDA": "Nvidia",
            "PLTR": "Palantir",
            "MSFT": "Microsoft",
            "AAPL": "Apple",
            "SPY": "S und P 500",
            "QQQ": "Nasdaq",
            "DAX": "Dax",
            "VIX": "Vix Volatilitätsindex",
            "FOMC": "F O M C US-Notenbank",
            "EZB": "E Z B Europäische Zentralbank",
            "NFP": "N F P US-Arbeitsmarktbericht",
            "CPI": "C P I Verbraucherpreisindex",
            "PCE": "P C E Kerninflationsrate",
            "AVWAP": "Anchored V-Wapp",
            "VWAP": "V-Wapp",
            "GEX": "Gamma Exposure",
            "POC": "Point of Control",
            "VAH": "Value Area High",
            "VAL": "Value Area Low",
            "FVG": "Fair Value Gap",
            "ORB": "Opening Range Breakout",
            "R:R": "Chance-Risiko-Verhältnis",
            "CRV": "Chance-Risiko-Verhältnis",
            "EUR": "Euro",
            "USD": "US-Dollar",
            "Ø": "Durchschnittlich",
        }

        for k, v in word_replacements.items():
            if "." in k or ":" in k:
                t = re.sub(re.escape(k), v, t, flags=re.IGNORECASE)
            else:
                t = re.sub(r"\b" + re.escape(k) + r"\b", v, t, flags=re.IGNORECASE)

        # Collapse whitespace
        t = re.sub(r"\s+", " ", t).strip()
        return t

    def build_spoken_script(self, brief_data: Optional[Dict[str, Any]] = None) -> str:
        """
        Builds a crisp, structured radio-style script for the daily briefing.
        Target length: 60 to 90 seconds spoken audio.
        """
        now = datetime.now()
        date_str = now.strftime("%d. %B %Y")

        parts = [
            f"Guten Morgen! Hier ist dein institutionelles Audio-Briefing für {date_str}."
        ]

        if not brief_data:
            parts.append(
                "Die Märkte bereiten sich auf die heutige Handelssitzung vor. "
                "Überprüfe vor Handelsstart den 360-Grad-Check und deinen Makro-Shield."
            )
            return " ".join(parts)

        # 1. Market Regime & Sentiment
        regime = brief_data.get("market_regime") or brief_data.get("regime") or {}
        stance = regime.get("stance") or brief_data.get("stance") or "NEUTRAL"
        vix_val = (regime.get("vix") or {}).get("value")

        if "RISK_ON" in str(stance).upper():
            parts.append(
                "Das übergeordnete Marktregime steht auf Risk-On. "
                "Die Bullen haben das Momentum, Wachstums- und Techwerte zeigen Stärke."
            )
        elif "RISK_OFF" in str(stance).upper():
            parts.append(
                "Das Marktregime signalisiert Risk-Off. Erhöhte Vorsicht ist geboten, "
                "defensive Sektoren und Absicherungen sind gefragt."
            )
        else:
            parts.append("Das Sentiment ist aktuell ausgeglichen und konsolidiert vor den nächsten Impulsen.")

        if vix_val:
            parts.append(f"Der Volatilitätsindex VIX notiert bei rund {float(vix_val):.1f} Punkten.")

        # 2. Macro Catalysts
        macro_events = brief_data.get("economic_calendar") or brief_data.get("macro_catalysts") or []
        if macro_events:
            first_event = macro_events[0]
            e_title = first_event.get("title", "High-Impact Notenbank-Termin")
            e_time = first_event.get("time", "14:30")
            parts.append(
                f"Auf der Makroseite steht heute besonders {e_title} um {e_time} Uhr im Fokus. "
                f"Halte den 30-Minuten-Blackout-Shield ein, um Whipsaw-Verluste zu vermeiden."
            )

        # 3. Top Trading Setups
        ideas = brief_data.get("trade_ideas") or brief_data.get("setups") or []
        if ideas:
            top_idea = ideas[0]
            ticker = top_idea.get("ticker", "dem Hauptfavoriten")
            setup_name = top_idea.get("setup_name") or top_idea.get("setup_type") or "Key-Level-Rebound"
            parts.append(
                f"Im Fokus der Watchlist steht heute {self._clean_for_speech(ticker)} mit einem {setup_name} Setup. "
                f"Achte auf Bestätigung am Point of Control und das berechnete Chance-Risiko-Verhältnis."
            )

        # 4. Golden Rule of the Day
        parts.append(
            "Die eiserne Regel für heute: Riskiere maximal ein Prozent deines Kapitals pro Trade. "
            "Sichere nach Erreichen des ersten Kursziels die Restposition auf Break-Even ab. "
            "Ich wünsche dir einen erfolgreichen und disziplinierten Handelstag!"
        )

        full_script = " ".join(parts)
        return self._clean_for_speech(full_script)

    def generate_audio_mp3(self, text: str, lang: Optional[str] = None) -> bytes:
        """
        Converts text into MP3 audio bytes using gTTS.
        """
        if not HAS_GTTS:
            raise RuntimeError("gTTS is not installed. Please install gTTS to generate audio briefings.")

        clean_text = self._clean_for_speech(text)
        if not clean_text:
            clean_text = "Kein Text für das Audio Briefing vorhanden."

        target_lang = lang or self.default_lang
        tts = gTTS(text=clean_text, lang=target_lang, slow=False)
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf.getvalue()

    def generate_daily_briefing_audio(
        self, brief_data: Optional[Dict[str, Any]] = None, lang: Optional[str] = None
    ) -> Tuple[bytes, str]:
        """
        Builds the daily briefing script and returns (mp3_bytes, spoken_script).
        """
        script = self.build_spoken_script(brief_data)
        audio_bytes = self.generate_audio_mp3(script, lang=lang)
        return audio_bytes, script


# Global singleton instance
_audio_briefing_instance: Optional[AudioBriefingService] = None


def get_audio_briefing_service() -> AudioBriefingService:
    global _audio_briefing_instance
    if _audio_briefing_instance is None:
        _audio_briefing_instance = AudioBriefingService()
    return _audio_briefing_instance
