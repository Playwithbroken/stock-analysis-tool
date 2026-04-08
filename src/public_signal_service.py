"""
Public and personal signal service.

Combines official public sources into transparent delayed signals:
- Berkshire 13F / 13D-style monitoring from SEC
- House PTR watch parsing for selected politicians
- SEC Form 4 radar for selected tickers
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from io import BytesIO
import re
from typing import Any, Dict, List, Optional
import xml.etree.ElementTree as ET

import requests
import yfinance as yf
from bs4 import BeautifulSoup
from pypdf import PdfReader


SEC_HEADERS = {
    "User-Agent": "BrokerFreund/1.0 research@local.dev",
    "Accept-Encoding": "gzip, deflate",
    "Host": "data.sec.gov",
}

ARCHIVE_HEADERS = {
    "User-Agent": "BrokerFreund/1.0 research@local.dev",
    "Accept-Encoding": "gzip, deflate",
}

HOUSE_SEARCH_URL = "https://disclosures-clerk.house.gov/FinancialDisclosure/ViewSearch"
HOUSE_MEMBER_RESULT_URL = (
    "https://disclosures-clerk.house.gov/FinancialDisclosure/ViewMemberSearchResult"
)


@dataclass
class FilingRef:
    form: str
    filing_date: str
    accession_number: str
    cik: Optional[str] = None

    @property
    def accession_compact(self) -> str:
        return self.accession_number.replace("-", "")

    @property
    def filing_index_url(self) -> str:
        cik = self.cik or "1067983"
        cik = str(int(cik))
        return (
            f"https://www.sec.gov/Archives/edgar/data/{cik}/"
            f"{self.accession_compact}/{self.accession_number}-index.html"
        )


class PublicSignalService:
    _public_cache_value: Optional[Dict[str, Any]] = None
    _public_cache_time: Optional[datetime] = None
    _public_cache_ttl_seconds = 60 * 60 * 6

    _company_map_cache: Optional[Dict[str, Dict[str, Any]]] = None
    _company_map_time: Optional[datetime] = None

    def __init__(self) -> None:
        self.session = requests.Session()
        self._ticker_lookup_cache: Dict[str, Optional[str]] = {}

    def get_public_signals(self) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        if (
            self._public_cache_value is not None
            and self._public_cache_time is not None
            and (now - self._public_cache_time).total_seconds() < self._public_cache_ttl_seconds
        ):
            return self._public_cache_value

        payload = {
            "generated_at": now.isoformat(),
            "trackers": [
                self._build_berkshire_tracker(),
                self._build_congress_tracker(),
            ],
        }
        self._public_cache_value = payload
        self._public_cache_time = now
        return payload

    def build_watchlist_snapshot(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        watched_tickers = [item["value"] for item in items if item.get("kind") == "ticker"]
        watched_politicians = [
            item["value"] for item in items if item.get("kind") == "politician"
        ]

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "items": items,
            "ticker_signals": self._build_ticker_signals(watched_tickers),
            "politician_signals": self._build_politician_signals(watched_politicians),
        }

    def _build_berkshire_tracker(self) -> Dict[str, Any]:
        try:
            filings = self._get_recent_filings_for_cik("1067983", forms={"13F-HR", "13F-HR/A"})
            latest_13f = next((item for item in filings if item.form == "13F-HR"), None)
            previous_13f = next(
                (
                    item
                    for item in filings
                    if item.form == "13F-HR"
                    and latest_13f is not None
                    and item.accession_number != latest_13f.accession_number
                ),
                None,
            )
            if latest_13f is None:
                raise ValueError("No Berkshire 13F filing found.")

            latest_positions = self._extract_13f_positions(latest_13f)
            previous_positions = (
                self._extract_13f_positions(previous_13f) if previous_13f else {}
            )
            moves = self._compare_positions(latest_positions, previous_positions)
            for move in moves[:6]:
                move["ticker"] = self._resolve_ticker(move.get("issuer_name", ""))
            latest_meta = self._extract_13f_metadata(latest_13f)

            return {
                "id": "berkshire",
                "title": "Berkshire Radar",
                "subtitle": "Direkt aus SEC-13F-Meldungen, mit sichtbarer Verzögerung",
                "source_label": "SEC EDGAR",
                "source_url": "https://www.sec.gov/edgar/browse/?CIK=1067983&owner=exclude",
                "lag_note": "13F zeigt Quartalsbestände mit bis zu 45 Tagen Verzögerung.",
                "signal_quality": "Sehr transparent, aber deutlich verzögert",
                "report_period": latest_meta.get("report_period"),
                "filing_date": latest_13f.filing_date,
                "staleness_days": self._days_between(latest_meta.get("report_period")),
                "filed_days_ago": self._days_between(latest_13f.filing_date),
                "filing_page": latest_13f.filing_index_url,
                "highlights": moves[:6],
                "latest_filings": [
                    {
                        "form": filing.form,
                        "filed_at": filing.filing_date,
                        "url": filing.filing_index_url,
                    }
                    for filing in filings[:4]
                ],
                "why_better": [
                    "Zeigt Delay und Filing-Datum offen an statt Black-Box-Kopieren.",
                    "Springt von der Signal-Idee direkt in eure Detailanalyse.",
                    "Vergleicht die letzten 13F-Berichte und markiert neue bzw. erhöhte Positionen.",
                ],
            }
        except Exception as exc:
            return {
                "id": "berkshire",
                "title": "Berkshire Radar",
                "subtitle": "SEC-Signale konnten gerade nicht geladen werden",
                "source_label": "SEC EDGAR",
                "source_url": "https://www.sec.gov/edgar/browse/?CIK=1067983&owner=exclude",
                "lag_note": "13F zeigt Quartalsbestände mit bis zu 45 Tagen Verzögerung.",
                "signal_quality": "Transparent, aber aktuell nicht verfügbar",
                "error": str(exc),
                "highlights": [],
                "latest_filings": [],
                "why_better": [
                    "Nur öffentliche Quellen.",
                    "Keine Behauptung von Echtzeit oder Vorabinformationen.",
                ],
            }

    def _build_congress_tracker(self) -> Dict[str, Any]:
        return {
            "id": "congress",
            "title": "Congress Watch",
            "subtitle": "Persönlicher House-PTR-Feed mit Delay- und Compliance-Hinweisen",
            "source_label": "House / Senate Disclosure Portals",
            "source_url": "https://ethics.house.gov/financial-disclosure",
            "lag_note": (
                "PTR-Meldungen kommen oft erst 30 bis 45 Tage nach dem Trade oder "
                "nach Kenntnis des Trades."
            ),
            "signal_quality": "Öffentlich, aber deutlich verzögert",
            "compliance_note": (
                "House-Disclosure-Daten sind für persönliche Recherche sinnvoll. "
                "Die House-Suchseite weist explizit auf Einschränkungen für kommerzielle Nutzung hin."
            ),
            "highlights": [
                {
                    "title": "Name hinzufügen, nicht blind kopieren",
                    "detail": (
                        "Im Personal Radar unten kannst du House-Mitglieder gezielt verfolgen "
                        "und ihre letzten PTR-Transaktionen direkt lesen."
                    ),
                },
                {
                    "title": "Delay-first Bewertung",
                    "detail": (
                        "Jeder Trade wird mit Trade-Date, Filing-Date und Delay-Tagen dargestellt."
                    ),
                },
                {
                    "title": "Ticker + Politiker kombinieren",
                    "detail": (
                        "Spannend wird es, wenn ein beobachteter Politiker und Insider- oder Berkshire-Signale "
                        "denselben Ticker berühren."
                    ),
                },
            ],
            "official_links": [
                {
                    "label": "House Financial Disclosure",
                    "url": "https://ethics.house.gov/financial-disclosure",
                },
                {
                    "label": "House Clerk Search",
                    "url": "https://disclosures-clerk.house.gov/FinancialDisclosure",
                },
                {
                    "label": "Senate Financial Disclosure",
                    "url": "https://www.ethics.senate.gov/public/index.cfm/financialdisclosure",
                },
            ],
            "why_better": [
                "Keine Behauptung, wer angeblich 'die meisten Infos' hat.",
                "Persönlicher Radar statt generischer Politiker-Hype.",
                "Verbindet offizielle Meldungen mit eurem Analyzer und Watchlist-Flow.",
            ],
        }

    def _build_ticker_signals(self, tickers: List[str]) -> List[Dict[str, Any]]:
        results = []
        for ticker in tickers[:10]:
            try:
                entry = self._build_single_ticker_signal(ticker)
                if entry:
                    results.append(entry)
            except Exception as exc:
                results.append(
                    {
                        "ticker": ticker,
                        "title": ticker,
                        "error": str(exc),
                        "events": [],
                    }
                )
        return results

    def _build_single_ticker_signal(self, ticker: str) -> Dict[str, Any]:
        company_map = self._get_company_ticker_map()
        company = company_map.get(ticker.upper())
        if not company:
            return {
                "ticker": ticker.upper(),
                "title": ticker.upper(),
                "events": [],
                "note": "Ticker nicht in SEC company_tickers.json gefunden.",
            }

        cik = str(company["cik"]).zfill(10)
        filings = self._get_recent_filings_for_cik(cik, forms={"4"})
        events: List[Dict[str, Any]] = []
        for filing in filings[:8]:
            events.extend(self._extract_form4_events(filing))

        buy_sell_events = [
            event
            for event in events
            if event.get("shares") and event.get("action") in {"buy", "sell"}
        ]
        if buy_sell_events:
            buy_sell_events.sort(
                key=lambda event: (
                    0 if event["action"] == "buy" else 1,
                    -(event.get("value_usd") or 0),
                )
            )
            events = buy_sell_events
        else:
            events = [event for event in events if event.get("shares")]
            events.sort(key=lambda event: event.get("trade_date") or "", reverse=True)

        return {
            "ticker": ticker.upper(),
            "title": company["title"],
            "source_url": f"https://www.sec.gov/edgar/browse/?CIK={cik}&owner=exclude",
            "events": events[:6],
        }

    def _build_politician_signals(self, names: List[str]) -> List[Dict[str, Any]]:
        results = []
        for name in names[:10]:
            try:
                entries = self._search_house_ptr_reports(name)
                trades: List[Dict[str, Any]] = []
                for entry in entries[:3]:
                    trades.extend(self._extract_house_ptr_trades(entry["url"], entry["filed_year"]))

                trades.sort(
                    key=lambda trade: (
                        0 if trade.get("action") == "buy" else 1,
                        self._days_between(trade.get("trade_date")) or 9999,
                    )
                )

                buy_count = sum(1 for trade in trades if trade.get("action") == "buy")
                sell_count = sum(1 for trade in trades if trade.get("action") == "sell")
                latest_trade_date = next((trade.get("trade_date") for trade in trades if trade.get("trade_date")), None)
                avg_delay_days = (
                    round(
                        sum(trade.get("delay_days") or 0 for trade in trades if trade.get("delay_days") is not None)
                        / max(1, sum(1 for trade in trades if trade.get("delay_days") is not None)),
                        1,
                    )
                    if trades
                    else None
                )

                results.append(
                    {
                        "name": name,
                        "reports": entries[:3],
                        "trades": trades[:8],
                        "source_url": "https://disclosures-clerk.house.gov/FinancialDisclosure",
                        "signal_quality": "official_house_ptr",
                        "summary": {
                            "report_count": len(entries[:3]),
                            "trade_count": len(trades[:8]),
                            "buy_count": buy_count,
                            "sell_count": sell_count,
                            "latest_trade_date": latest_trade_date,
                            "avg_delay_days": avg_delay_days,
                        },
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "name": name,
                        "reports": [],
                        "trades": [],
                        "error": str(exc),
                        "source_url": "https://disclosures-clerk.house.gov/FinancialDisclosure",
                        "signal_quality": "official_house_ptr",
                        "summary": {
                            "report_count": 0,
                            "trade_count": 0,
                            "buy_count": 0,
                            "sell_count": 0,
                            "latest_trade_date": None,
                            "avg_delay_days": None,
                        },
                    }
                )
        return results

    def _search_house_ptr_reports(self, name: str) -> List[Dict[str, Any]]:
        session = requests.Session()
        search_page = session.get(HOUSE_SEARCH_URL, timeout=25)
        search_page.raise_for_status()
        soup = BeautifulSoup(search_page.text, "html.parser")
        token_input = soup.find("input", {"name": "__RequestVerificationToken"})
        if not token_input:
            raise ValueError("House search token not found.")
        token = token_input.get("value", "")

        last_name = name.split()[-1]
        filing_years = [str(datetime.now().year), str(datetime.now().year - 1)]
        reports: List[Dict[str, Any]] = []
        for filing_year in filing_years:
            form_data = {
                "LastName": last_name,
                "FilingYear": filing_year,
                "State": "",
                "District": "",
                "__RequestVerificationToken": token,
            }
            response = session.post(HOUSE_MEMBER_RESULT_URL, data=form_data, timeout=25)
            response.raise_for_status()
            result_soup = BeautifulSoup(response.text, "html.parser")

            for row in result_soup.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) < 4:
                    continue
                link = cells[0].find("a", href=True)
                if not link:
                    continue
                filing_type = cells[3].get_text(" ", strip=True)
                if "PTR" not in filing_type.upper():
                    continue
                href = link["href"]
                full_url = href if href.startswith("http") else f"https://disclosures-clerk.house.gov/{href.lstrip('/')}"
                reports.append(
                    {
                        "name": link.get_text(" ", strip=True),
                        "office": cells[1].get_text(" ", strip=True),
                        "filed_year": cells[2].get_text(" ", strip=True),
                        "filing_type": filing_type,
                        "url": full_url,
                    }
                )
        unique_reports = []
        seen = set()
        for report in reports:
            if report["url"] in seen:
                continue
            seen.add(report["url"])
            unique_reports.append(report)
        filtered_reports = [
            report for report in unique_reports if self._name_matches_house_result(name, report.get("name", ""))
        ]
        return filtered_reports or unique_reports

    def _name_matches_house_result(self, requested_name: str, result_name: str) -> bool:
        requested_tokens = [token for token in re.findall(r"[A-Za-z]+", requested_name.lower()) if token]
        result_tokens = [token for token in re.findall(r"[A-Za-z]+", result_name.lower()) if token]
        if not requested_tokens or not result_tokens:
            return True
        requested_last = requested_tokens[-1]
        if requested_last not in result_tokens:
            return False
        requested_first = requested_tokens[0]
        result_first = result_tokens[0]
        if requested_first == result_first:
            return True
        return requested_first[:1] == result_first[:1]

    def _extract_house_ptr_trades(self, pdf_url: str, filed_year: str) -> List[Dict[str, Any]]:
        response = self.session.get(pdf_url, timeout=30)
        response.raise_for_status()
        reader = PdfReader(BytesIO(response.content))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        clean_text = text.replace("\x00", "")
        pattern = re.compile(
            r"SP\s+(?P<asset>.+?)\s+\[(?P<asset_type>[A-Z]{2})\]\s+"
            r"(?P<transaction>[A-Z][^\d]{0,20}?)\s+"
            r"(?P<trade_date>\d{2}/\d{2}/\d{4})\s*"
            r"(?P<notification_date>\d{2}/\d{2}/\d{4})\s+"
            r"(?P<amount>\$[\d,]+(?:\s*-\s*\$[\d,]+)?)",
            re.S,
        )

        trades: List[Dict[str, Any]] = []
        for match in pattern.finditer(clean_text):
            asset = " ".join(match.group("asset").split())
            transaction = " ".join(match.group("transaction").split())
            action = "buy" if transaction.startswith("P") else "sell" if transaction.startswith("S") else "other"
            ticker_match = re.search(r"\(([A-Z.\-]+)\)", asset)
            trades.append(
                {
                    "asset": asset,
                    "ticker": ticker_match.group(1) if ticker_match else None,
                    "action": action,
                    "transaction_label": transaction,
                    "trade_date": self._normalize_us_date(match.group("trade_date")),
                    "notification_date": self._normalize_us_date(match.group("notification_date")),
                    "amount_range": " ".join(match.group("amount").split()),
                    "delay_days": self._delay_days(
                        self._normalize_us_date(match.group("trade_date")),
                        self._normalize_us_date(match.group("notification_date")),
                    ),
                    "source_url": pdf_url,
                    "filed_year": filed_year,
                }
            )
        return trades

    def _get_company_ticker_map(self) -> Dict[str, Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        if (
            self._company_map_cache is not None
            and self._company_map_time is not None
            and (now - self._company_map_time).total_seconds() < 86400
        ):
            return self._company_map_cache

        response = self.session.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers=ARCHIVE_HEADERS,
            timeout=30,
        )
        response.raise_for_status()
        raw = response.json()
        data: Dict[str, Dict[str, Any]] = {}
        for value in raw.values():
            ticker = (value.get("ticker") or "").upper()
            if ticker:
                data[ticker] = {
                    "cik": int(value["cik_str"]),
                    "title": value.get("title") or ticker,
                }
        self._company_map_cache = data
        self._company_map_time = now
        return data

    def _get_recent_filings_for_cik(self, cik: str, forms: set[str]) -> List[FilingRef]:
        padded_cik = str(cik).zfill(10)
        url = f"https://data.sec.gov/submissions/CIK{padded_cik}.json"
        response = self.session.get(url, headers=SEC_HEADERS, timeout=25)
        response.raise_for_status()
        data = response.json()

        filings: List[FilingRef] = []
        for form, filed_at, accession in zip(
            data["filings"]["recent"]["form"],
            data["filings"]["recent"]["filingDate"],
            data["filings"]["recent"]["accessionNumber"],
        ):
            if form in forms:
                filings.append(
                    FilingRef(
                        form=form,
                        filing_date=filed_at,
                        accession_number=accession,
                        cik=str(int(cik)),
                    )
                )
        return filings

    def _extract_form4_events(self, filing: FilingRef) -> List[Dict[str, Any]]:
        index_response = self.session.get(
            filing.filing_index_url,
            headers=ARCHIVE_HEADERS,
            timeout=25,
        )
        index_response.raise_for_status()
        soup = BeautifulSoup(index_response.text, "html.parser")
        xml_name = None
        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 4:
                continue
            document = cells[2].get_text(" ", strip=True)
            if document.lower().endswith(".xml"):
                xml_name = document
                break
        if not xml_name:
            raise ValueError(f"Form 4 XML not found for {filing.accession_number}.")

        xml_url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(filing.cik or '0')}/"
            f"{filing.accession_compact}/{xml_name}"
        )
        response = self.session.get(xml_url, headers=ARCHIVE_HEADERS, timeout=25)
        response.raise_for_status()
        root = ET.fromstring(response.text)

        issuer_ticker = root.findtext(".//issuer/issuerTradingSymbol")
        owner_name = root.findtext(".//reportingOwner/reportingOwnerId/rptOwnerName")
        owner_title = root.findtext(".//reportingOwner/reportingOwnerRelationship/officerTitle")
        period = root.findtext(".//periodOfReport")

        events: List[Dict[str, Any]] = []
        for tx in root.findall(".//nonDerivativeTransaction"):
            code = tx.findtext(".//transactionCoding/transactionCode")
            acquired_disposed = tx.findtext(
                ".//transactionAmounts/transactionAcquiredDisposedCode/value"
            )
            date_value = tx.findtext(".//transactionDate/value") or period
            shares = self._safe_float(tx.findtext(".//transactionShares/value"))
            price = self._safe_float(tx.findtext(".//transactionPricePerShare/value"))
            value_usd = shares * price if shares and price else None
            action = self._form4_action(code, acquired_disposed)
            events.append(
                {
                    "ticker": issuer_ticker,
                    "owner_name": owner_name,
                    "owner_title": owner_title,
                    "trade_date": date_value,
                    "filed_date": filing.filing_date,
                    "action": action,
                    "transaction_code": code,
                    "shares": shares,
                    "price": price,
                    "value_usd": value_usd,
                    "value_label": self._format_money(value_usd) if value_usd else None,
                    "delay_days": self._delay_days(date_value, filing.filing_date),
                    "source_url": filing.filing_index_url,
                }
            )
        return events

    def _extract_13f_metadata(self, filing: FilingRef) -> Dict[str, Optional[str]]:
        xml_url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(filing.cik or '0')}/"
            f"{filing.accession_compact}/primary_doc.xml"
        )
        response = self.session.get(xml_url, headers=ARCHIVE_HEADERS, timeout=25)
        response.raise_for_status()
        root = ET.fromstring(response.text)
        ns = {"n": "http://www.sec.gov/edgar/thirteenffiler"}
        report_period = root.findtext(".//n:periodOfReport", namespaces=ns)
        return {"report_period": self._normalize_sec_date(report_period)}

    def _extract_13f_positions(self, filing: FilingRef) -> Dict[str, Dict[str, Any]]:
        index_response = self.session.get(
            filing.filing_index_url,
            headers=ARCHIVE_HEADERS,
            timeout=25,
        )
        index_response.raise_for_status()
        soup = BeautifulSoup(index_response.text, "html.parser")

        xml_name = None
        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 4:
                continue
            description = cells[1].get_text(" ", strip=True).upper()
            document = cells[2].get_text(" ", strip=True)
            if "INFORMATION TABLE" in description and document.lower().endswith(".xml"):
                xml_name = document
                break

        if not xml_name:
            raise ValueError(f"Information table XML not found for {filing.accession_number}.")

        xml_url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(filing.cik or '0')}/"
            f"{filing.accession_compact}/{xml_name}"
        )
        response = self.session.get(xml_url, headers=ARCHIVE_HEADERS, timeout=25)
        response.raise_for_status()
        root = ET.fromstring(response.text)
        ns = {"n": "http://www.sec.gov/edgar/document/thirteenf/informationtable"}

        positions: Dict[str, Dict[str, Any]] = {}
        for info_table in root.findall("n:infoTable", ns):
            cusip = (info_table.findtext("n:cusip", "", ns) or "").strip()
            issuer_name = (info_table.findtext("n:nameOfIssuer", "", ns) or "").strip()
            shares_text = info_table.findtext("n:shrsOrPrnAmt/n:sshPrnamt", "0", ns)
            value_text = info_table.findtext("n:value", "0", ns)
            if not cusip and not issuer_name:
                continue

            key = cusip or issuer_name
            entry = positions.setdefault(
                key,
                {
                    "cusip": cusip,
                    "issuer_name": issuer_name,
                    "shares": 0,
                    "value_usd": 0,
                },
            )
            entry["shares"] += self._safe_int(shares_text)
            entry["value_usd"] += self._safe_int(value_text) * 1000

        return positions

    def _compare_positions(
        self,
        latest_positions: Dict[str, Dict[str, Any]],
        previous_positions: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        moves: List[Dict[str, Any]] = []
        for key, latest in latest_positions.items():
            previous = previous_positions.get(key, {})
            prev_shares = previous.get("shares", 0) or 0
            prev_value = previous.get("value_usd", 0) or 0
            delta_shares = (latest.get("shares", 0) or 0) - prev_shares
            delta_value = (latest.get("value_usd", 0) or 0) - prev_value
            if delta_shares == 0 and delta_value == 0:
                continue

            status = "new" if prev_shares == 0 else "increased" if delta_shares > 0 else "reduced"
            moves.append(
                {
                    "ticker": None,
                    "issuer_name": latest.get("issuer_name"),
                    "status": status,
                    "shares_now": latest.get("shares", 0),
                    "delta_shares": delta_shares,
                    "value_now": latest.get("value_usd", 0),
                    "delta_value": delta_value,
                    "value_label": self._format_money(latest.get("value_usd", 0)),
                    "delta_value_label": self._format_money(abs(delta_value)),
                }
            )

        positive_moves = [item for item in moves if item["delta_shares"] > 0]
        positive_moves.sort(
            key=lambda item: (0 if item["status"] == "new" else 1, -item["delta_value"])
        )
        return positive_moves

    def _resolve_ticker(self, issuer_name: str) -> Optional[str]:
        if not issuer_name:
            return None
        cache_key = issuer_name.upper()
        if cache_key in self._ticker_lookup_cache:
            return self._ticker_lookup_cache[cache_key]

        try:
            search = yf.Search(issuer_name, max_results=5)
            for quote in search.quotes:
                symbol = quote.get("symbol")
                quote_type = (quote.get("quoteType") or "").upper()
                if symbol and quote_type in {"EQUITY", "ETF"}:
                    self._ticker_lookup_cache[cache_key] = symbol
                    return symbol
        except Exception:
            pass

        self._ticker_lookup_cache[cache_key] = None
        return None

    def _form4_action(self, transaction_code: Optional[str], acquired_disposed: Optional[str]) -> str:
        if transaction_code == "P":
            return "buy"
        if transaction_code in {"S", "F"}:
            return "sell"
        if transaction_code is None and acquired_disposed == "A":
            return "buy"
        if transaction_code is None and acquired_disposed == "D":
            return "sell"
        return "other"

    def _normalize_sec_date(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        if "-" in value and len(value) == 10:
            return value
        try:
            month, day, year = value.split("-")
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        except Exception:
            return value

    def _normalize_us_date(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        try:
            return datetime.strptime(value, "%m/%d/%Y").strftime("%Y-%m-%d")
        except Exception:
            return value

    def _delay_days(self, start_date: Optional[str], end_date: Optional[str]) -> Optional[int]:
        if not start_date or not end_date:
            return None
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            return max(0, (end - start).days)
        except Exception:
            return None

    def _days_between(self, date_str: Optional[str]) -> Optional[int]:
        if not date_str:
            return None
        try:
            date_value = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            return max(0, (now - date_value).days)
        except ValueError:
            try:
                date_value = parsedate_to_datetime(date_str)
                now = datetime.now(timezone.utc)
                return max(0, (now - date_value.astimezone(timezone.utc)).days)
            except Exception:
                return None

    def _format_money(self, value: Optional[float]) -> str:
        absolute = abs(value or 0)
        if absolute >= 1_000_000_000:
            return f"${absolute / 1_000_000_000:.2f}B"
        if absolute >= 1_000_000:
            return f"${absolute / 1_000_000:.1f}M"
        if absolute >= 1_000:
            return f"${absolute / 1_000:.0f}K"
        return f"${absolute:.0f}"

    def _safe_int(self, value: Any) -> int:
        try:
            return int(str(value).replace(",", "").strip() or "0")
        except Exception:
            return 0

    def _safe_float(self, value: Any) -> float:
        try:
            return float(str(value).replace(",", "").strip() or "0")
        except Exception:
            return 0.0
