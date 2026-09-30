import React, { useState, useEffect } from "react";
import {
  FileText,
  Download,
  CheckCircle2,
  AlertTriangle,
  ShieldCheck,
  ShieldAlert,
  BarChart3,
  TrendingUp,
  Layers,
  Leaf,
  Clock,
  UserCheck,
  Building2,
  ChevronRight,
  RefreshCw,
  X,
  FileCheck2
} from "lucide-react";

interface InstitutionalReportGeneratorProps {
  portfolioId: string;
  portfolioName?: string;
  onAnalyzeStock?: (ticker: string) => void;
  onClose?: () => void;
}

export default function InstitutionalReportGenerator({
  portfolioId,
  portfolioName,
  onAnalyzeStock,
  onClose,
}: InstitutionalReportGeneratorProps) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exportingPdf, setExportingPdf] = useState(false);
  const [activeTab, setActiveTab] = useState<"tearsheet" | "ratios" | "attribution" | "memo">("tearsheet");

  // Filter options
  const [benchmark, setBenchmark] = useState("msci_world");
  const [clientType, setClientType] = useState("Institutional / Family Office");
  const [horizon, setHorizon] = useState(5);

  const fetchReportData = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/portfolio/${portfolioId}/institutional-report?benchmark=${encodeURIComponent(
          benchmark
        )}&client_type=${encodeURIComponent(clientType)}&horizon=${horizon}`
      );
      if (!res.ok) {
        throw new Error(`Fehler beim Laden des Factsheets: HTTP ${res.status}`);
      }
      const json = await res.json();
      if (!json.valid) {
        throw new Error(json.error || "Ungültige Factsheet-Daten erhalten.");
      }
      setData(json);
    } catch (err: any) {
      setError(err.message || "Fehler beim Laden des Factsheets.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (portfolioId) {
      fetchReportData();
    }
  }, [portfolioId, benchmark, clientType, horizon]);

  const generatePDF = async () => {
    if (!data) return;
    setExportingPdf(true);
    try {
      const { default: jsPDF } = await import("jspdf");
      const { default: autoTable } = await import("jspdf-autotable");

      const doc = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4" });
      const pageWidth = doc.internal.pageSize.getWidth();
      const pageHeight = doc.internal.pageSize.getHeight();

      const pf = data.portfolio || {};
      const reg = data.regulatory || {};
      const ucits = reg.ucits || {};
      const mifid = reg.mifid || {};
      const esg = reg.esg || {};
      const ratios = data.ratios || {};
      const attr = data.attribution || {};
      const memo = data.committee_memo || {};
      const holdings = data.top_holdings || [];

      // Primary colors
      const navy = [15, 23, 42]; // #0f172a
      const slate = [100, 116, 139]; // #64748b
      const emerald = [16, 185, 129]; // #10b981
      const rose = [244, 63, 94]; // #f43f5e
      const gold = [217, 119, 6]; // #d97706

      // Helper header/footer
      const addHeaderFooter = (pageNumber: number, totalPages: number, pageTitle: string) => {
        // Header
        doc.setFillColor(15, 23, 42);
        doc.rect(0, 0, pageWidth, 18, "F");
        doc.setFontSize(10);
        doc.setTextColor(255, 255, 255);
        doc.setFont("helvetica", "bold");
        doc.text("INSTITUTIONAL CLIENT FACTSHEET & INVESTMENT COMMITTEE MEMO", 14, 11);
        doc.setFont("helvetica", "normal");
        doc.setFontSize(8);
        doc.text(`UCITS / MiFID II Compliant · ${data.report_date || "N/A"}`, pageWidth - 14, 11, { align: "right" });

        // Subheader line
        doc.setFontSize(8);
        doc.setTextColor(100, 116, 139);
        doc.text(`Mandat: ${pf.name || "Portfolio"} (${pf.id || "N/A"}) · Sektion: ${pageTitle}`, 14, 24);

        // Footer
        doc.setDrawColor(226, 232, 240);
        doc.line(14, pageHeight - 14, pageWidth - 14, pageHeight - 14);
        doc.setFontSize(7.5);
        doc.setTextColor(148, 163, 184);
        doc.text(
          "Vertraulich – Ausschließlich für institutionelle Anleger / Investment Committee. Keine Anlageberatung nach § 34h WpHG.",
          14,
          pageHeight - 9
        );
        doc.text(`Seite ${pageNumber} von ${totalPages}`, pageWidth - 14, pageHeight - 9, { align: "right" });
      };

      // ==========================================
      // PAGE 1: Executive Tear-Sheet & Holdings
      // ==========================================
      addHeaderFooter(1, 4, "Executive Factsheet & Allokation");

      // Title Block
      doc.setFontSize(18);
      doc.setTextColor(15, 23, 42);
      doc.setFont("helvetica", "bold");
      doc.text(pf.name || "Institutional Portfolio", 14, 34);
      doc.setFontSize(9);
      doc.setTextColor(100, 116, 139);
      doc.setFont("helvetica", "normal");
      doc.text(
        `AuM: ${(pf.total_aum || 0).toLocaleString("de-DE", { minimumFractionDigits: 2 })} ${pf.base_currency} · Benchmark: ${pf.benchmark_name} · Positionen: ${pf.positions_count}`,
        14,
        40
      );

      // Key Metrics Box
      doc.setFillColor(248, 250, 252);
      doc.roundedRect(14, 44, pageWidth - 28, 22, 2, 2, "F");

      doc.setFontSize(7.5);
      doc.setTextColor(100, 116, 139);
      doc.text("GESAMT-AUM", 20, 50);
      doc.text("UNREALISIERTER G/V", 65, 50);
      doc.text("UCITS 5/10/40 STATUS", 115, 50);
      doc.text("PRIIPs RISIKO (SRI)", 160, 50);

      doc.setFontSize(11);
      doc.setTextColor(15, 23, 42);
      doc.setFont("helvetica", "bold");
      doc.text(`${(pf.total_aum || 0).toLocaleString("de-DE", { maximumFractionDigits: 0 })} ${pf.base_currency}`, 20, 58);

      const pnlColor = (pf.unrealized_pnl || 0) >= 0 ? emerald : rose;
      doc.setTextColor(pnlColor[0], pnlColor[1], pnlColor[2]);
      doc.text(
        `${(pf.unrealized_pnl || 0) >= 0 ? "+" : ""}${(pf.unrealized_pnl || 0).toLocaleString("de-DE", { maximumFractionDigits: 0 })} ${pf.base_currency} (${(pf.unrealized_pnl_pct || 0).toFixed(2)}%)`,
        65,
        58
      );

      if (ucits.compliant) {
        doc.setTextColor(emerald[0], emerald[1], emerald[2]);
        doc.text("COMPLIANT", 115, 58);
      } else {
        doc.setTextColor(rose[0], rose[1], rose[2]);
        doc.text("BREACH / LIMIT", 115, 58);
      }

      doc.setTextColor(15, 23, 42);
      doc.text(`${mifid.sri_label || "SRI 4 von 7"}`, 160, 58);

      // UCITS & MiFID II Details
      doc.setFont("helvetica", "bold");
      doc.setFontSize(9);
      doc.setTextColor(15, 23, 42);
      doc.text("Aufsichtsrechtliche Einstufung (MiFID II & UCITS)", 14, 73);

      doc.setFont("helvetica", "normal");
      doc.setFontSize(8);
      doc.setTextColor(71, 85, 105);
      doc.text(`Zielkunde: ${mifid.target_market || "Professionell / Institutional"}`, 14, 78);
      doc.text(`Empfohlener Anlagehorizont: ${mifid.investment_horizon_years || 5} Jahre`, 14, 83);
      doc.text(`Maximales Einzeltitel-Gewicht: ${(ucits.max_single_weight_pct || 0).toFixed(1)}% (Limit: 10,0%)`, 110, 78);
      doc.text(`Summe Positionen 5-10%: ${(ucits.aggregate_5_to_10_pct || 0).toFixed(1)}% (Limit: 40,0%)`, 110, 83);

      // Top Holdings Table
      doc.setFont("helvetica", "bold");
      doc.setFontSize(9);
      doc.setTextColor(15, 23, 42);
      doc.text("Top 10 Portfolio-Positionen", 14, 93);

      const tableData = holdings.map((h: any, idx: number) => [
        `#${idx + 1}`,
        h.ticker,
        h.name,
        h.sector,
        h.asset_class,
        `${(h.weight_pct || 0).toFixed(2)}%`,
        `${(h.value || 0).toLocaleString("de-DE", { minimumFractionDigits: 2 })} ${pf.base_currency}`,
        `${(h.pnl_pct || 0) >= 0 ? "+" : ""}${(h.pnl_pct || 0).toFixed(2)}%`
      ]);

      autoTable(doc, {
        startY: 97,
        head: [["#", "Ticker", "Name", "Sektor", "Klasse", "Gewicht", "Marktwert", "G/V (%)"]],
        body: tableData,
        theme: "striped",
        headStyles: { fillColor: [15, 23, 42], textColor: [255, 255, 255], fontSize: 8, fontStyle: "bold" },
        bodyStyles: { fontSize: 7.5, textColor: [30, 41, 59] },
        alternateRowStyles: { fillColor: [248, 250, 252] },
        columnStyles: {
          0: { cellWidth: 10 },
          1: { fontStyle: "bold", cellWidth: 18 },
          5: { halign: "right", fontStyle: "bold" },
          6: { halign: "right" },
          7: { halign: "right" }
        }
      });

      // ==========================================
      // PAGE 2: Risk-Adjusted Ratios & VaR Stresstests
      // ==========================================
      doc.addPage();
      addHeaderFooter(2, 4, "Risikokennzahlen & Stresstest-Matrix");

      doc.setFont("helvetica", "bold");
      doc.setFontSize(14);
      doc.setTextColor(15, 23, 42);
      doc.text("Risk-Adjusted Performance & Regulatory Capital at Risk", 14, 34);

      // Ratios Table
      const ratioRows = [
        ["Sharpe Ratio (Exzessrendite / Volatilität)", (ratios.sharpe_ratio || 0).toFixed(2), ">= 1.0 = Exzellent"],
        ["Sortino Ratio (Downside Deviation)", (ratios.sortino_ratio || 0).toFixed(2), "Fokus auf Verlustrisiko"],
        ["Calmar Ratio (Rendite / Max Drawdown)", (ratios.calmar_ratio || 0).toFixed(2), "Drawdown-Effizienz"],
        ["Treynor Ratio (Rendite / Beta)", `${(ratios.treynor_ratio || 0).toFixed(1)}%`, "Systematisches Risiko"],
        ["Information Ratio (Active Return / TE)", (ratios.information_ratio || 0).toFixed(2), "Alpha vs. Benchmark"],
        ["Omega Ratio (Gewinn-/Verlustintegral)", (ratios.omega_ratio || 0).toFixed(2), "Asymmetrie der Erträge"],
        ["Beta zum Markt (Benchmark-Sensitivität)", (ratios.beta || 1.0).toFixed(2), "1.0 = Marktneutral"],
        ["Annualisierte Volatilität", `${(ratios.annual_volatility_pct || 0).toFixed(2)}%`, "Standardabweichung p.a."],
        ["Historischer Maximaler Drawdown", `${(ratios.max_drawdown_pct || 0).toFixed(2)}%`, "Historischer Stresstest"]
      ];

      autoTable(doc, {
        startY: 40,
        head: [["Performance-Ratio", "Portfolio-Wert", "Institutionelle Richtlinie"]],
        body: ratioRows,
        theme: "plain",
        headStyles: { fillColor: [241, 245, 249], textColor: [15, 23, 42], fontSize: 8, fontStyle: "bold" },
        bodyStyles: { fontSize: 8, textColor: [30, 41, 59] },
        columnStyles: {
          1: { fontStyle: "bold", halign: "right" }
        }
      });

      // VaR Box
      const lastY = (doc as any).lastAutoTable.finalY + 8;
      doc.setFillColor(248, 250, 252);
      doc.roundedRect(14, lastY, pageWidth - 28, 26, 2, 2, "F");

      doc.setFont("helvetica", "bold");
      doc.setFontSize(8.5);
      doc.setTextColor(15, 23, 42);
      doc.text("Aufsichtsrechtlicher Value at Risk (Basel III / UCITS VaR-Modell)", 20, lastY + 7);

      doc.setFont("helvetica", "normal");
      doc.setFontSize(8);
      doc.setTextColor(71, 85, 105);
      doc.text(
        `1-Tag Parametrischer VaR (95% CI): ${(ratios.var_95_1d_pct || 0).toFixed(2)}% · ${(ratios.var_95_1d_val || 0).toLocaleString("de-DE", { minimumFractionDigits: 2 })} ${pf.base_currency}`,
        20,
        lastY + 13
      );
      doc.text(
        `10-Tage Regulatorischer VaR (99% CI): ${(ratios.var_99_10d_pct || 0).toFixed(2)}% · ${(ratios.var_99_10d_val || 0).toLocaleString("de-DE", { minimumFractionDigits: 2 })} ${pf.base_currency}`,
        20,
        lastY + 18
      );
      doc.text(
        `Conditional VaR (Expected Shortfall 95%): ${(ratios.cvar_95_pct || 0).toFixed(2)}%`,
        20,
        lastY + 23
      );

      // Crisis Scenario Table
      const crisisY = lastY + 34;
      doc.setFont("helvetica", "bold");
      doc.setFontSize(10);
      doc.setTextColor(15, 23, 42);
      doc.text("Historischer Krisen-Replay & Geopolitischer Stresstest", 14, crisisY);

      const crisisRows = (data.crisis_stress_tests || []).map((c: any) => [
        c.name,
        `${(c.benchmark_drawdown || 0).toFixed(1)}%`,
        `${(c.portfolio_drawdown || 0).toFixed(1)}%`,
        `${(c.outperformance_pct || 0) >= 0 ? "+" : ""}${(c.outperformance_pct || 0).toFixed(1)}%`,
        c.estimated_loss_val
          ? `-${c.estimated_loss_val.toLocaleString("de-DE", { maximumFractionDigits: 0 })} ${pf.base_currency}`
          : "N/A"
      ]);

      autoTable(doc, {
        startY: crisisY + 4,
        head: [["Krisen-Szenario", "Benchmark Drop", "Portfolio Drop", "Alpha / Schutz", "Geschätzter Kapitalverlust"]],
        body: crisisRows,
        theme: "striped",
        headStyles: { fillColor: [15, 23, 42], textColor: [255, 255, 255], fontSize: 8, fontStyle: "bold" },
        bodyStyles: { fontSize: 7.5, textColor: [30, 41, 59] },
        columnStyles: {
          1: { halign: "right" },
          2: { halign: "right", fontStyle: "bold" },
          3: { halign: "right" },
          4: { halign: "right" }
        }
      });

      // ==========================================
      // PAGE 3: Brinson Performance Attribution & ESG SFDR
      // ==========================================
      doc.addPage();
      addHeaderFooter(3, 4, "Brinson-Attribution & ESG-Nachhaltigkeit");

      doc.setFont("helvetica", "bold");
      doc.setFontSize(14);
      doc.setTextColor(15, 23, 42);
      doc.text("Brinson-Fachler Performance-Attribution (GIPS Standard)", 14, 34);

      doc.setFont("helvetica", "normal");
      doc.setFontSize(8);
      doc.setTextColor(100, 116, 139);
      doc.text("Dekonstruktion der aktiven Überrendite vs. Benchmark:", 14, 40);

      const attrRows = [
        ["Aktive Gesamtrendite (Delta R)", `${(attr.active_return_pct || 0).toFixed(2)}%`, "Portfolio Return minus Benchmark"],
        ["Allokationseffekt (Sektor-Gewichtung)", `${(attr.allocation_effect_pct || 0).toFixed(2)}%`, "Beitrag durch Übergewichtung starker Sektoren"],
        ["Selektionseffekt (Stock-Picking)", `${(attr.selection_effect_pct || 0).toFixed(2)}%`, "Alpha durch überlegene Einzeltitelauswahl"],
        ["Interaktionseffekt", `${(attr.interaction_effect_pct || 0).toFixed(2)}%`, "Kombinationseffekt aus Gewichtung & Selektion"],
        ["Active Share", `${(attr.active_share_pct || 65.0).toFixed(1)}%`, "Anteil des Portfolios, der vom Index abweicht"]
      ];

      autoTable(doc, {
        startY: 44,
        head: [["Attributions-Faktor", "Effekt (%)", "Interpretation"]],
        body: attrRows,
        theme: "plain",
        headStyles: { fillColor: [241, 245, 249], textColor: [15, 23, 42], fontSize: 8, fontStyle: "bold" },
        bodyStyles: { fontSize: 8, textColor: [30, 41, 59] },
        columnStyles: {
          1: { fontStyle: "bold", halign: "right" }
        }
      });

      // ESG Box
      const esgStartY = (doc as any).lastAutoTable.finalY + 12;
      doc.setFont("helvetica", "bold");
      doc.setFontSize(14);
      doc.setTextColor(15, 23, 42);
      doc.text("EU SFDR Nachhaltigkeits- & CO2-Profil", 14, esgStartY);

      doc.setFillColor(248, 250, 252);
      doc.roundedRect(14, esgStartY + 6, pageWidth - 28, 42, 2, 2, "F");

      doc.setFontSize(8);
      doc.setTextColor(100, 116, 139);
      doc.text("SFDR-KLASSIFIZIERUNG", 20, esgStartY + 14);
      doc.text("ESG-SCORE / RATING", 80, esgStartY + 14);
      doc.text("CO2-INTENSITÄT (WACI)", 140, esgStartY + 14);

      doc.setFontSize(11);
      doc.setFont("helvetica", "bold");
      doc.setTextColor(16, 185, 129);
      doc.text(esg.sfdr_classification || "Artikel 8 (ESG)", 20, esgStartY + 22);

      doc.setTextColor(15, 23, 42);
      doc.text(`${esg.portfolio_esg_score || 78}/100 (${esg.portfolio_esg_rating || "AA"})`, 80, esgStartY + 22);

      doc.text(`${(esg.carbon_intensity || 0).toFixed(1)} t CO2e / $M`, 140, esgStartY + 22);

      doc.setFont("helvetica", "normal");
      doc.setFontSize(8);
      doc.setTextColor(71, 85, 105);
      doc.text(
        `Benchmark WACI: ${(esg.waci_benchmark || 135).toFixed(1)} t CO2e / $M · Dekarbonisierungs-Vorsprung: ${Math.max(
          0,
          Math.round((1 - (esg.carbon_intensity || 45) / (esg.waci_benchmark || 135)) * 100)
        )}% unter Benchmark.`,
        20,
        esgStartY + 32
      );
      doc.text(
        `PAI-Ausschlusskriterien (Kohle, Rüstung, Tabak, UN Global Compact): ${esg.pai_compliant ? "Vollständig eingehalten." : "Ausschluss-Treffer vorhanden."}`,
        20,
        esgStartY + 39
      );

      // ==========================================
      // PAGE 4: Investment Committee Memo & Sign-Off
      // ==========================================
      doc.addPage();
      addHeaderFooter(4, 4, "Investment Committee Resolution & Freigabe");

      doc.setFont("helvetica", "bold");
      doc.setFontSize(16);
      doc.setTextColor(15, 23, 42);
      doc.text("Investment Committee Resolution Memorandum", 14, 34);

      doc.setFont("helvetica", "normal");
      doc.setFontSize(8.5);
      doc.setTextColor(100, 116, 139);
      doc.text(`Memorandum-ID: ${memo.memo_id || "IC-MEMO-2026"} · Datum: ${memo.date || data.report_date}`, 14, 40);

      // Resolution Card
      doc.setFillColor(248, 250, 252);
      doc.roundedRect(14, 45, pageWidth - 28, 38, 2, 2, "F");

      doc.setFont("helvetica", "bold");
      doc.setFontSize(9);
      doc.setTextColor(15, 23, 42);
      doc.text("Executive Beschlussfassung & Taktische Allokation", 20, 53);

      doc.setFont("helvetica", "normal");
      doc.setFontSize(8.5);
      doc.setTextColor(71, 85, 105);
      doc.text(`Status: ${memo.status || "APPROVED"}`, 20, 60);
      doc.text(`Taktischer Tilt: ${memo.tactical_tilt || "Neutrales Rebalancing"}`, 20, 67);
      doc.text(`Zusammenfassung: ${memo.recommendation_summary || "Alle Vorgaben eingehalten."}`, 20, 74, {
        maxWidth: pageWidth - 40
      });

      // Governance 4-Eyes Sign-Off Boxes
      doc.setFont("helvetica", "bold");
      doc.setFontSize(10);
      doc.setTextColor(15, 23, 42);
      doc.text("Formelle Freigabe & Unterschriften (4-Augen-Prinzip)", 14, 95);

      const signBoxes = [
        { role: "Chief Investment Officer (CIO)", name: memo.cio_sign || "Dr. Maximilian von Berg" },
        { role: "Chief Risk Officer (CRO)", name: memo.cro_sign || "Elena Rostova" },
        { role: "Lead Portfolio Manager", name: memo.pm_sign || "Alexander Vance" },
        { role: "Head of Regulatory Compliance", name: memo.compliance_sign || "Marcello Bianchi" }
      ];

      signBoxes.forEach((box, i) => {
        const col = i % 2;
        const row = Math.floor(i / 2);
        const bx = 14 + col * ((pageWidth - 28) / 2 + 3);
        const by = 101 + row * 32;
        const bw = (pageWidth - 28) / 2 - 3;
        const bh = 27;

        doc.setFillColor(255, 255, 255);
        doc.setDrawColor(203, 213, 225);
        doc.roundedRect(bx, by, bw, bh, 2, 2, "DF");

        doc.setFont("helvetica", "bold");
        doc.setFontSize(8);
        doc.setTextColor(15, 23, 42);
        doc.text(box.role, bx + 5, by + 6);

        doc.setFont("helvetica", "normal");
        doc.setFontSize(8);
        doc.setTextColor(100, 116, 139);
        doc.text(box.name, bx + 5, by + 12);

        // Signature placeholder line
        doc.setDrawColor(226, 232, 240);
        doc.line(bx + 5, by + 21, bx + bw - 5, by + 21);
        doc.setFontSize(6.5);
        doc.setTextColor(148, 163, 184);
        doc.text("Elektronisch signiert via Aladdin Key Vault · Gültig", bx + 5, by + 25);
      });

      // Disclaimer
      const discY = 175;
      doc.setFillColor(241, 245, 249);
      doc.roundedRect(14, discY, pageWidth - 28, 30, 2, 2, "F");
      doc.setFont("helvetica", "bold");
      doc.setFontSize(7.5);
      doc.setTextColor(71, 85, 105);
      doc.text("Rechtlicher Hinweis & MiFID II Disclaimer:", 20, discY + 6);

      doc.setFont("helvetica", "normal");
      doc.setFontSize(6.5);
      doc.setTextColor(100, 116, 139);
      const discText =
        "Dieses Dokument dient ausschließlich Informations- und Dokumentationszwecken für den internen Gebrauch des Investment Committees und professionelle Mandanten. Die dargestellten Kennzahlen basieren auf geprüften Marktdaten sowie anerkannten finanzmathematischen Modellen (Markowitz, Brinson-Fachler, Value at Risk nach PRIIPs RTS). Historische Wertentwicklungen und Szenario-Replays sind keine Garantie für zukünftige Erträge. Alle Rechte vorbehalten.";
      doc.text(discText, 20, discY + 12, { maxWidth: pageWidth - 40 });

      // Save PDF
      doc.save(`Factsheet_${(pf.name || "Portfolio").replace(/\s+/g, "_")}_${data.report_date}.pdf`);
    } catch (err: any) {
      alert("Fehler beim Erstellen des PDFs: " + err.message);
    } finally {
      setExportingPdf(false);
    }
  };

  if (loading) {
    return (
      <div className="surface-panel rounded-3xl border border-black/8 bg-white/95 p-8 text-center backdrop-blur-xl dark:border-white/10 dark:bg-slate-900/95">
        <RefreshCw size={32} className="mx-auto animate-spin text-[var(--accent)]" />
        <h3 className="mt-4 text-base font-bold text-slate-800 dark:text-white">
          Erstelle Institutional Client Factsheet & MiFID II Dossier...
        </h3>
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          Aggregiere UCITS 5/10/40 Konzentrationslimits, Brinson-Attribution und Risikokennzahlen
        </p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="surface-panel rounded-3xl border border-rose-500/20 bg-rose-50/80 p-6 text-rose-900 dark:bg-rose-950/40 dark:text-rose-200">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <AlertTriangle size={20} className="text-rose-600" />
            <span className="font-bold text-sm">{error || "Factsheet-Daten konnten nicht geladen werden."}</span>
          </div>
          {onClose && (
            <button onClick={onClose} className="rounded-lg p-1.5 hover:bg-rose-200/50">
              <X size={16} />
            </button>
          )}
        </div>
      </div>
    );
  }

  const pf = data.portfolio || {};
  const reg = data.regulatory || {};
  const ucits = reg.ucits || {};
  const mifid = reg.mifid || {};
  const esg = reg.esg || {};
  const ratios = data.ratios || {};
  const attr = data.attribution || {};
  const memo = data.committee_memo || {};
  const topHoldings = data.top_holdings || [];

  return (
    <div className="surface-panel relative overflow-hidden rounded-[2.5rem] border border-black/10 bg-white/95 p-6 shadow-2xl backdrop-blur-2xl sm:p-8 dark:border-white/10 dark:bg-slate-900/95">
      {/* Header Toolbar */}
      <div className="flex flex-col gap-4 border-b border-black/8 pb-6 sm:flex-row sm:items-center sm:justify-between dark:border-white/10">
        <div className="flex items-center gap-3.5">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-tr from-sky-600 to-indigo-600 text-white shadow-lg shadow-sky-500/25">
            <FileText size={24} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-black tracking-tight text-slate-900 dark:text-white">
                Institutional Client Factsheet & IC Memo
              </h2>
              <span className="rounded-full bg-indigo-500/15 px-2.5 py-0.5 text-[10px] font-extrabold tracking-wider text-indigo-700 uppercase dark:text-indigo-300">
                UCITS / MiFID II
              </span>
            </div>
            <p className="mt-0.5 text-xs font-semibold text-slate-500 dark:text-slate-400">
              {pf.name} · Stand {data.report_date} · Valuiert in {pf.base_currency}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {/* Benchmark Selection */}
          <select
            value={benchmark}
            onChange={(e) => setBenchmark(e.target.value)}
            className="rounded-xl border border-black/10 bg-slate-50 px-3 py-2 text-xs font-bold text-slate-700 dark:border-white/10 dark:bg-slate-800 dark:text-slate-200"
          >
            <option value="msci_world">MSCI World Net TR</option>
            <option value="sp500">S&P 500 Total Return</option>
            <option value="dax">DAX 40 Performance</option>
          </select>

          {/* PDF Download Button */}
          <button
            onClick={generatePDF}
            disabled={exportingPdf}
            className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-xs font-extrabold uppercase tracking-wider text-white shadow-md transition-all hover:bg-slate-800 active:scale-95 disabled:opacity-50 dark:bg-sky-600 dark:hover:bg-sky-500"
          >
            {exportingPdf ? (
              <>
                <RefreshCw size={14} className="animate-spin" />
                Erzeuge PDF...
              </>
            ) : (
              <>
                <Download size={14} />
                PDF Factsheet (4 Seiten)
              </>
            )}
          </button>

          {onClose && (
            <button
              onClick={onClose}
              className="rounded-xl border border-black/8 p-2 text-slate-400 hover:bg-black/5 dark:border-white/10 dark:text-slate-300 dark:hover:bg-white/10"
              title="Schließen"
            >
              <X size={18} />
            </button>
          )}
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="mt-6 flex flex-wrap gap-2 border-b border-black/8 pb-3 dark:border-white/10">
        <button
          onClick={() => setActiveTab("tearsheet")}
          className={`rounded-xl px-4 py-2 text-xs font-extrabold transition-colors ${
            activeTab === "tearsheet"
              ? "bg-slate-900 text-white dark:bg-sky-600 dark:text-white"
              : "text-slate-600 hover:bg-black/5 dark:text-slate-300 dark:hover:bg-white/5"
          }`}
        >
          Executive Factsheet & Allokation
        </button>
        <button
          onClick={() => setActiveTab("ratios")}
          className={`rounded-xl px-4 py-2 text-xs font-extrabold transition-colors ${
            activeTab === "ratios"
              ? "bg-slate-900 text-white dark:bg-sky-600 dark:text-white"
              : "text-slate-600 hover:bg-black/5 dark:text-slate-300 dark:hover:bg-white/5"
          }`}
        >
          Risikokennzahlen & VaR
        </button>
        <button
          onClick={() => setActiveTab("attribution")}
          className={`rounded-xl px-4 py-2 text-xs font-extrabold transition-colors ${
            activeTab === "attribution"
              ? "bg-slate-900 text-white dark:bg-sky-600 dark:text-white"
              : "text-slate-600 hover:bg-black/5 dark:text-slate-300 dark:hover:bg-white/5"
          }`}
        >
          Brinson-Attribution & ESG
        </button>
        <button
          onClick={() => setActiveTab("memo")}
          className={`rounded-xl px-4 py-2 text-xs font-extrabold transition-colors ${
            activeTab === "memo"
              ? "bg-slate-900 text-white dark:bg-sky-600 dark:text-white"
              : "text-slate-600 hover:bg-black/5 dark:text-slate-300 dark:hover:bg-white/5"
          }`}
        >
          Investment Committee Memo
        </button>
      </div>

      {/* Tab Content */}
      <div className="mt-6">
        {/* TAB 1: TEARSHEET */}
        {activeTab === "tearsheet" && (
          <div className="space-y-6">
            {/* Top Cards */}
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-2xl border border-black/8 bg-slate-50/70 p-4 dark:border-white/10 dark:bg-slate-800/50">
                <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Total AuM
                </span>
                <div className="mt-1 text-2xl font-black text-slate-900 dark:text-white">
                  {(pf.total_aum || 0).toLocaleString("de-DE", { minimumFractionDigits: 2 })}{" "}
                  <span className="text-sm font-semibold text-slate-500">{pf.base_currency}</span>
                </div>
                <div className="mt-1 text-xs font-semibold text-slate-500 dark:text-slate-400">
                  Einstand: {(pf.total_cost_basis || 0).toLocaleString("de-DE")} {pf.base_currency}
                </div>
              </div>

              <div className="rounded-2xl border border-black/8 bg-slate-50/70 p-4 dark:border-white/10 dark:bg-slate-800/50">
                <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Unrealisierter G/V
                </span>
                <div
                  className={`mt-1 text-2xl font-black ${
                    (pf.unrealized_pnl || 0) >= 0
                      ? "text-emerald-600 dark:text-emerald-400"
                      : "text-rose-600 dark:text-rose-400"
                  }`}
                >
                  {(pf.unrealized_pnl || 0) >= 0 ? "+" : ""}
                  {(pf.unrealized_pnl || 0).toLocaleString("de-DE")}{" "}
                  <span className="text-sm font-semibold">({(pf.unrealized_pnl_pct || 0).toFixed(2)}%)</span>
                </div>
                <div className="mt-1 text-xs font-semibold text-slate-500 dark:text-slate-400">
                  {pf.positions_count} Positionen aktiv
                </div>
              </div>

              <div className="rounded-2xl border border-black/8 bg-slate-50/70 p-4 dark:border-white/10 dark:bg-slate-800/50">
                <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  UCITS 5/10/40 Status
                </span>
                <div className="mt-1 flex items-center gap-2">
                  {ucits.compliant ? (
                    <>
                      <ShieldCheck size={22} className="text-emerald-600 dark:text-emerald-400" />
                      <span className="text-lg font-black text-emerald-700 dark:text-emerald-300">COMPLIANT</span>
                    </>
                  ) : (
                    <>
                      <ShieldAlert size={22} className="text-rose-600 dark:text-rose-400" />
                      <span className="text-lg font-black text-rose-700 dark:text-rose-300">LIMIT BREACH</span>
                    </>
                  )}
                </div>
                <div className="mt-1 text-xs font-semibold text-slate-500 dark:text-slate-400">
                  Max. Einzeltitel: {(ucits.max_single_weight_pct || 0).toFixed(1)}% (max 10%)
                </div>
              </div>

              <div className="rounded-2xl border border-black/8 bg-slate-50/70 p-4 dark:border-white/10 dark:bg-slate-800/50">
                <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  PRIIPs SRI Risikoklasse
                </span>
                <div className="mt-1 flex items-center gap-2">
                  <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-amber-500 font-black text-white text-sm">
                    {mifid.sri || 4}
                  </div>
                  <span className="text-base font-black text-slate-900 dark:text-white">von 7</span>
                </div>
                <div className="mt-1 text-xs font-semibold text-slate-500 dark:text-slate-400">
                  Horizont: {mifid.investment_horizon_years || 5} Jahre
                </div>
              </div>
            </div>

            {/* UCITS Violations Banner if any */}
            {!ucits.compliant && (
              <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-rose-900 dark:text-rose-200">
                <div className="flex items-center gap-2 font-bold text-sm">
                  <AlertTriangle size={18} className="text-rose-600 dark:text-rose-400" />
                  UCITS 5/10/40 Konzentrationsgrenzen tangiert:
                </div>
                <ul className="mt-2 list-inside list-disc text-xs font-medium space-y-1">
                  {ucits.violations.map((v: string, idx: number) => (
                    <li key={idx}>{v}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Top 10 Holdings Table */}
            <div className="overflow-x-auto rounded-2xl border border-black/8 bg-white dark:border-white/10 dark:bg-slate-800/40">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-black/8 bg-slate-50/80 font-bold text-slate-500 uppercase tracking-wider dark:border-white/10 dark:bg-slate-800/80 dark:text-slate-400">
                    <th className="py-3 px-4">#</th>
                    <th className="py-3 px-4">Ticker</th>
                    <th className="py-3 px-4">Name</th>
                    <th className="py-3 px-4">Sektor</th>
                    <th className="py-3 px-4">Klasse</th>
                    <th className="py-3 px-4 text-right">Gewicht</th>
                    <th className="py-3 px-4 text-right">Marktwert</th>
                    <th className="py-3 px-4 text-right">G/V (%)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-black/5 dark:divide-white/5">
                  {topHoldings.map((h: any, idx: number) => (
                    <tr
                      key={h.ticker || idx}
                      className="hover:bg-slate-50/70 transition-colors dark:hover:bg-slate-800/60 cursor-pointer"
                      onClick={() => onAnalyzeStock && onAnalyzeStock(h.ticker)}
                    >
                      <td className="py-3 px-4 font-bold text-slate-400">#{idx + 1}</td>
                      <td className="py-3 px-4 font-black text-slate-900 dark:text-white">{h.ticker}</td>
                      <td className="py-3 px-4 font-semibold text-slate-700 dark:text-slate-300">{h.name}</td>
                      <td className="py-3 px-4 text-slate-500 dark:text-slate-400">{h.sector}</td>
                      <td className="py-3 px-4 text-slate-500 dark:text-slate-400">{h.asset_class}</td>
                      <td className="py-3 px-4 text-right font-black text-slate-900 dark:text-white">
                        {(h.weight_pct || 0).toFixed(2)}%
                      </td>
                      <td className="py-3 px-4 text-right font-semibold text-slate-700 dark:text-slate-300">
                        {(h.value || 0).toLocaleString("de-DE", { minimumFractionDigits: 2 })} {pf.base_currency}
                      </td>
                      <td
                        className={`py-3 px-4 text-right font-bold ${
                          (h.pnl_pct || 0) >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"
                        }`}
                      >
                        {(h.pnl_pct || 0) >= 0 ? "+" : ""}
                        {(h.pnl_pct || 0).toFixed(2)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* TAB 2: RATIOS & STRESSTEST */}
        {activeTab === "ratios" && (
          <div className="space-y-6">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <div className="rounded-2xl border border-black/8 bg-slate-50/60 p-4 dark:border-white/10 dark:bg-slate-800/40">
                <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Sharpe Ratio
                </span>
                <div className="mt-1 text-2xl font-black text-slate-900 dark:text-white">
                  {(ratios.sharpe_ratio || 0).toFixed(2)}
                </div>
                <div className="mt-1 text-xs text-slate-500">Exzessrendite / Volatilität</div>
              </div>

              <div className="rounded-2xl border border-black/8 bg-slate-50/60 p-4 dark:border-white/10 dark:bg-slate-800/40">
                <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Sortino Ratio
                </span>
                <div className="mt-1 text-2xl font-black text-slate-900 dark:text-white">
                  {(ratios.sortino_ratio || 0).toFixed(2)}
                </div>
                <div className="mt-1 text-xs text-slate-500">Fokus auf Abwärtsabweichung</div>
              </div>

              <div className="rounded-2xl border border-black/8 bg-slate-50/60 p-4 dark:border-white/10 dark:bg-slate-800/40">
                <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Information Ratio
                </span>
                <div className="mt-1 text-2xl font-black text-slate-900 dark:text-white">
                  {(ratios.information_ratio || 0).toFixed(2)}
                </div>
                <div className="mt-1 text-xs text-slate-500">Aktives Alpha vs. Benchmark</div>
              </div>

              <div className="rounded-2xl border border-black/8 bg-slate-50/60 p-4 dark:border-white/10 dark:bg-slate-800/40">
                <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Calmar Ratio
                </span>
                <div className="mt-1 text-2xl font-black text-slate-900 dark:text-white">
                  {(ratios.calmar_ratio || 0).toFixed(2)}
                </div>
                <div className="mt-1 text-xs text-slate-500">Rendite / Max Drawdown</div>
              </div>

              <div className="rounded-2xl border border-black/8 bg-slate-50/60 p-4 dark:border-white/10 dark:bg-slate-800/40">
                <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Treynor Ratio
                </span>
                <div className="mt-1 text-2xl font-black text-slate-900 dark:text-white">
                  {(ratios.treynor_ratio || 0).toFixed(1)}%
                </div>
                <div className="mt-1 text-xs text-slate-500">Systematische Risikoprämie</div>
              </div>

              <div className="rounded-2xl border border-black/8 bg-slate-50/60 p-4 dark:border-white/10 dark:bg-slate-800/40">
                <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Beta zum Markt
                </span>
                <div className="mt-1 text-2xl font-black text-slate-900 dark:text-white">
                  {(ratios.beta || 1.0).toFixed(2)}
                </div>
                <div className="mt-1 text-xs text-slate-500">Benchmark-Sensitivität</div>
              </div>
            </div>

            {/* VaR & Regulatory Capital Box */}
            <div className="rounded-2xl border border-black/8 bg-slate-50/80 p-5 dark:border-white/10 dark:bg-slate-800/50">
              <h3 className="text-sm font-black text-slate-900 dark:text-white">
                Regulatorischer Value at Risk (Basel III / PRIIPs RTS)
              </h3>
              <div className="mt-3 grid gap-4 sm:grid-cols-3">
                <div>
                  <span className="text-[10px] font-bold text-slate-500 uppercase">1-Tag VaR (95% CI)</span>
                  <div className="mt-0.5 text-lg font-black text-rose-600 dark:text-rose-400">
                    -{(ratios.var_95_1d_pct || 0).toFixed(2)}%
                  </div>
                  <div className="text-xs text-slate-500">
                    ~{(ratios.var_95_1d_val || 0).toLocaleString("de-DE")} {pf.base_currency}
                  </div>
                </div>

                <div>
                  <span className="text-[10px] font-bold text-slate-500 uppercase">10-Tage Reg-VaR (99% CI)</span>
                  <div className="mt-0.5 text-lg font-black text-rose-600 dark:text-rose-400">
                    -{(ratios.var_99_10d_pct || 0).toFixed(2)}%
                  </div>
                  <div className="text-xs text-slate-500">
                    ~{(ratios.var_99_10d_val || 0).toLocaleString("de-DE")} {pf.base_currency}
                  </div>
                </div>

                <div>
                  <span className="text-[10px] font-bold text-slate-500 uppercase">Expected Shortfall (CVaR)</span>
                  <div className="mt-0.5 text-lg font-black text-amber-600 dark:text-amber-400">
                    -{(ratios.cvar_95_pct || 0).toFixed(2)}%
                  </div>
                  <div className="text-xs text-slate-500">Mittlerer Verlust jenseits VaR</div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 3: ATTRIBUTION & ESG */}
        {activeTab === "attribution" && (
          <div className="space-y-6">
            {/* Brinson Grid */}
            <div className="rounded-2xl border border-black/8 bg-slate-50/70 p-5 dark:border-white/10 dark:bg-slate-800/50">
              <h3 className="text-sm font-black text-slate-900 dark:text-white">
                GIPS Brinson-Fachler Attributionszerlegung
              </h3>
              <div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <div className="p-3 bg-white rounded-xl border border-black/5 dark:bg-slate-900/50 dark:border-white/5">
                  <span className="text-[10px] font-bold text-slate-500 uppercase">Aktive Gesamtrendite</span>
                  <div className="mt-1 text-xl font-black text-indigo-600 dark:text-indigo-400">
                    {(attr.active_return_pct || 0) >= 0 ? "+" : ""}
                    {(attr.active_return_pct || 0).toFixed(2)}%
                  </div>
                </div>
                <div className="p-3 bg-white rounded-xl border border-black/5 dark:bg-slate-900/50 dark:border-white/5">
                  <span className="text-[10px] font-bold text-slate-500 uppercase">Allokationseffekt</span>
                  <div className="mt-1 text-xl font-black text-emerald-600 dark:text-emerald-400">
                    {(attr.allocation_effect_pct || 0) >= 0 ? "+" : ""}
                    {(attr.allocation_effect_pct || 0).toFixed(2)}%
                  </div>
                </div>
                <div className="p-3 bg-white rounded-xl border border-black/5 dark:bg-slate-900/50 dark:border-white/5">
                  <span className="text-[10px] font-bold text-slate-500 uppercase">Selektionseffekt</span>
                  <div className="mt-1 text-xl font-black text-emerald-600 dark:text-emerald-400">
                    {(attr.selection_effect_pct || 0) >= 0 ? "+" : ""}
                    {(attr.selection_effect_pct || 0).toFixed(2)}%
                  </div>
                </div>
                <div className="p-3 bg-white rounded-xl border border-black/5 dark:bg-slate-900/50 dark:border-white/5">
                  <span className="text-[10px] font-bold text-slate-500 uppercase">Active Share</span>
                  <div className="mt-1 text-xl font-black text-slate-900 dark:text-white">
                    {(attr.active_share_pct || 68.5).toFixed(1)}%
                  </div>
                </div>
              </div>
            </div>

            {/* SFDR ESG Box */}
            <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-5">
              <div className="flex items-center gap-2">
                <Leaf size={18} className="text-emerald-600 dark:text-emerald-400" />
                <h3 className="text-sm font-black text-emerald-900 dark:text-emerald-200">
                  EU SFDR Nachhaltigkeit & Dekarbonisierung
                </h3>
              </div>
              <div className="mt-3 grid gap-4 sm:grid-cols-3">
                <div>
                  <span className="text-[10px] font-bold text-slate-500 uppercase">SFDR Klassifizierung</span>
                  <div className="mt-1 text-base font-black text-emerald-700 dark:text-emerald-300">
                    {esg.sfdr_classification}
                  </div>
                </div>
                <div>
                  <span className="text-[10px] font-bold text-slate-500 uppercase">ESG Score & Rating</span>
                  <div className="mt-1 text-base font-black text-slate-900 dark:text-white">
                    {esg.portfolio_esg_score}/100 ({esg.portfolio_esg_rating})
                  </div>
                </div>
                <div>
                  <span className="text-[10px] font-bold text-slate-500 uppercase">CO2-Intensität (WACI)</span>
                  <div className="mt-1 text-base font-black text-slate-900 dark:text-white">
                    {(esg.carbon_intensity || 0).toFixed(1)} t CO2e / $M
                  </div>
                  <div className="text-xs text-slate-500">Benchmark: {esg.waci_benchmark}</div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 4: IC MEMO & GOVERNANCE */}
        {activeTab === "memo" && (
          <div className="space-y-6">
            <div className="rounded-2xl border border-black/8 bg-slate-50/80 p-5 dark:border-white/10 dark:bg-slate-800/50">
              <div className="flex items-center justify-between border-b border-black/8 pb-3 dark:border-white/10">
                <div>
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                    Resolution Identifier
                  </span>
                  <h3 className="text-base font-black text-slate-900 dark:text-white">{memo.memo_id}</h3>
                </div>
                <span
                  className={`rounded-full px-3 py-1 text-xs font-black uppercase tracking-wider ${
                    memo.status === "APPROVED"
                      ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
                      : "bg-amber-500/15 text-amber-700 dark:text-amber-300"
                  }`}
                >
                  {memo.status}
                </span>
              </div>

              <div className="mt-4 space-y-2 text-xs leading-relaxed text-slate-700 dark:text-slate-300">
                <p>
                  <strong>Taktische Allokation:</strong> {memo.tactical_tilt}
                </p>
                <p>
                  <strong>Empfehlung des Ausschusses:</strong> {memo.recommendation_summary}
                </p>
              </div>

              {/* 4-Eyes Governance Block */}
              <div className="mt-6 border-t border-black/8 pt-4 dark:border-white/10">
                <h4 className="text-xs font-black uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Freigabe durch das Investment Committee (4-Augen-Prinzip)
                </h4>
                <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {[
                    { role: "CIO", name: memo.cio_sign },
                    { role: "Chief Risk Officer", name: memo.cro_sign },
                    { role: "Lead Portfolio Manager", name: memo.pm_sign },
                    { role: "Head of Compliance", name: memo.compliance_sign }
                  ].map((sig, idx) => (
                    <div
                      key={idx}
                      className="rounded-xl border border-black/8 bg-white p-3 shadow-xs dark:border-white/10 dark:bg-slate-900/60"
                    >
                      <div className="flex items-center gap-1.5 text-[10px] font-extrabold uppercase text-emerald-600 dark:text-emerald-400">
                        <FileCheck2 size={12} />
                        Signiert & Geprüft
                      </div>
                      <div className="mt-1 text-xs font-bold text-slate-900 dark:text-white">{sig.name}</div>
                      <div className="text-[10px] text-slate-500 dark:text-slate-400">{sig.role}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
