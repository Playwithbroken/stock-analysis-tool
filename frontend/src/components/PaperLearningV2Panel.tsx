import React from "react";

const pct = (value: unknown) => {
  const number = Number(value);
  return Number.isFinite(number) ? `${number.toFixed(1)}%` : "noch offen";
};

const label = (value: unknown) => String(value || "unclassified").replaceAll("_", " ").replaceAll(".", " · ");

export default function PaperLearningV2Panel({
  data,
  onEvaluate,
  onRefresh,
  evaluating = false,
}: {
  data: any;
  onEvaluate?: () => void;
  onRefresh?: () => Promise<void>;
  evaluating?: boolean;
}) {
  const summary = data?.summary || {};
  const policy = data?.policy || {};
  const hypotheses = data?.hypotheses || [];
  const segments = data?.segments || [];
  const errors = data?.top_errors || [];
  const operations = data?.operations || {};
  const nextAction = operations?.next_action || {};
  const attributions = data?.recent_attributions || [];
  const tradeReviews = data?.recent_trade_reviews || [];
  const recentRuns = data?.recent_runs || [];
  const rules = data?.rules || [];
  const ruleHistory = data?.rule_history || [];
  const [reviewReason, setReviewReason] = React.useState("");
  const [ruleBusy, setRuleBusy] = React.useState("");
  const [ruleMessage, setRuleMessage] = React.useState("");
  const [rollbackPreview, setRollbackPreview] = React.useState<any>(null);
  const hypothesisById = React.useMemo(
    () => Object.fromEntries(hypotheses.map((item: any) => [String(item.id), item])),
    [hypotheses],
  );

  const reviewRule = async (ruleId: string, action: string) => {
    if (reviewReason.trim().length < 8) {
      setRuleMessage("Bitte eine nachvollziehbare Begründung mit mindestens 8 Zeichen eingeben.");
      return;
    }
    setRuleBusy(`${ruleId}:${action}`);
    setRuleMessage("");
    try {
      const response = await fetch(`/api/trading/paper-learning-v2/rules/${ruleId}/action`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, reason: reviewReason.trim() }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Regelaktion wurde abgelehnt.");
      setRuleMessage(`Regelstatus gespeichert: ${label(payload.rule?.status || action)}. Audit wurde angelegt.`);
      setReviewReason("");
      setRollbackPreview(null);
      await onRefresh?.();
    } catch (error: any) {
      setRuleMessage(error?.message || "Regelaktion konnte nicht gespeichert werden.");
    } finally {
      setRuleBusy("");
    }
  };

  const previewRollback = async (ruleId: string) => {
    setRuleBusy(`${ruleId}:rollback-preview`);
    setRuleMessage("");
    try {
      const response = await fetch(`/api/trading/paper-learning-v2/rules/${ruleId}/rollback-preview`);
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Keine Rollback-Vorschau verfügbar.");
      setRollbackPreview(payload);
    } catch (error: any) {
      setRollbackPreview(null);
      setRuleMessage(error?.message || "Rollback-Vorschau konnte nicht geladen werden.");
    } finally {
      setRuleBusy("");
    }
  };

  return (
    <div data-testid="paper-learning-v2" className="mt-5 rounded-[1.7rem] border border-violet-200 bg-violet-50/75 p-5 text-violet-950">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[10px] font-extrabold uppercase tracking-[0.2em] text-violet-700">Learning Engine v2</div>
          <h3 className="mt-1 text-xl font-black">Entscheidung und Ergebnis werden getrennt gelernt.</h3>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-violet-900/80">
            Entry-Merkmale bleiben unveränderlich. Neue Regeln laufen zuerst als Shadow-Test und dürfen harte Risikolimits niemals lockern.
          </p>
        </div>
        <span className="rounded-full border border-violet-200 bg-white px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.14em] text-violet-700">
          nur Paper · {policy.version || "v2"}
        </span>
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-3 xl:grid-cols-6">
        {[
          ["Geschlossen", summary.closed_trades || 0],
          ["Entscheidende Outcomes", `${summary.decisive_outcomes || 0}/${summary.global_outcome_target || 100}`],
          ["Attribuiert", summary.attributed_trades || 0],
          ["Guter Prozess", pct(summary.good_process_rate)],
          ["Shadow-Regeln", summary.shadow_rules || 0],
          ["Fehlende Snapshots", summary.missing_feature_snapshots || 0],
          ["Asset-Daten fehlen", summary.missing_asset_features || 0],
          ["Marktregime fehlen", summary.missing_market_regime || 0],
        ].map(([name, value]) => (
          <div key={String(name)} className="rounded-xl border border-violet-200 bg-white/85 p-3">
            <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-violet-500">{name}</div>
            <div className="mt-1 text-lg font-black">{value}</div>
          </div>
        ))}
      </div>

      <div data-testid="paper-learning-operations" className="mt-4 rounded-xl border border-violet-300 bg-white/90 p-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-2xl">
            <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-violet-600">Heute als Nächstes</div>
            <div className="mt-1 text-base font-black">{nextAction.title || "Weitere Paper-Evidenz sammeln"}</div>
            <div className="mt-1 text-sm leading-5 text-violet-800">{nextAction.detail || "Nur qualifizierte Setups verwenden und Ergebnisse planmäßig auswerten."}</div>
          </div>
          <button
            type="button"
            onClick={onEvaluate}
            disabled={!onEvaluate || evaluating}
            className="rounded-xl bg-violet-700 px-4 py-2 text-[10px] font-extrabold uppercase tracking-[0.14em] text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {evaluating ? "Prüfung läuft …" : `Fällige Outcomes prüfen (${operations.due_outcomes || 0})`}
          </button>
        </div>
        <div className="mt-3 grid gap-2 text-xs sm:grid-cols-2 xl:grid-cols-5">
          <div>Offene Trades <b>{operations.open_trades || 0}</b></div>
          <div>Fällige Outcomes <b>{operations.due_outcomes || 0}</b></div>
          <div>Weitere ausstehend <b>{operations.pending_outcomes || 0}</b></div>
          <div>Journale fehlen <b>{operations.missing_journals || 0}</b></div>
          <div>
            Letzter Lauf <b>{operations.last_run?.age_minutes == null ? "noch nie" : `vor ${operations.last_run.age_minutes} Min.`}</b>
            <span className="block text-[10px] text-violet-600">
              {label(operations.last_run?.status || "not_started")}
              {operations.last_run?.duration_ms == null ? "" : ` · ${operations.last_run.duration_ms} ms`}
            </span>
          </div>
        </div>
        {!!operations.blockers?.length && (
          <div className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs font-bold text-amber-900">
            Offene Lernblocker: {operations.blockers.join(" · ")}
          </div>
        )}
        {operations.last_run?.error && (
          <div className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-xs font-bold text-red-800">
            Letzter Lernlauf fehlgeschlagen: {operations.last_run.error} · sicher wiederholbar
          </div>
        )}
        {!!recentRuns.length && (
          <div className="mt-3 border-t border-violet-100 pt-3">
            <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-violet-600">Letzte Lernläufe</div>
            <div className="mt-2 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
              {recentRuns.slice(0, 4).map((run: any) => (
                <div key={run.run_id} className="rounded-lg bg-violet-50 px-3 py-2 text-[10px]">
                  <div className="flex justify-between gap-2 font-black"><span>{label(run.status)}</span><span>{run.duration_ms == null ? "–" : `${run.duration_ms} ms`}</span></div>
                  <div className="mt-1 truncate text-violet-600" title={run.run_id}>{run.run_id}</div>
                  {run.error && <div className="mt-1 text-red-700">{run.error}</div>}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-3">
        <div className="rounded-xl border border-violet-200 bg-white/80 p-4">
          <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-violet-600">Aktuelle Hypothesen</div>
          <div className="mt-2 space-y-2 text-sm leading-5">
            {hypotheses.length ? hypotheses.slice(0, 3).map((item: any) => (
              <div key={item.id} className="rounded-lg bg-violet-50 px-3 py-2">
                <div className="font-bold">{item.statement}</div>
                <div className="mt-1 text-xs text-violet-700">
                  {item.status} · Unsicherheit {item.uncertainty} · n={item.evidence?.sample_size || 0} Trades
                </div>
                {item.alternative_explanation && <div className="mt-1 text-[11px] text-violet-700">Alternative: {item.alternative_explanation}</div>}
              </div>
            )) : <div className="text-violet-700">Noch keine belastbare Hypothese. Erst Daten sammeln.</div>}
          </div>
        </div>
        <div className="rounded-xl border border-violet-200 bg-white/80 p-4">
          <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-violet-600">Stärkste Segmente</div>
          <div className="mt-2 space-y-2 text-sm">
            {segments.length ? segments.slice(0, 4).map((item: any, index: number) => (
              <div key={`${item.segment?.setup_type}-${item.segment?.asset_class}-${item.segment?.regime_trend}-${item.segment?.regime_volatility}-${index}`} className="rounded-lg bg-violet-50 px-3 py-2">
                <div className="flex justify-between gap-3">
                  <span className="font-bold">{label(item.segment?.setup_type)} · {item.segment?.asset_class} · {label(item.segment?.direction)}</span>
                  <span>{item.hit_rate == null ? "offen" : pct(item.hit_rate)} / n={item.decisive || 0}</span>
                </div>
                <div className={`mt-1 text-[10px] font-extrabold uppercase tracking-[0.08em] ${item.regime_complete ? "text-emerald-700" : "text-red-700"}`}>
                  Regime: Trend {label(item.segment?.regime_trend)} · Volatilität {label(item.segment?.regime_volatility)}
                </div>
                <div className="mt-1 text-xs text-violet-700">
                  Erwartung {pct(item.expectancy_pct)} · PF {item.profit_factor ?? "offen"} · Prozess {pct(item.good_process_rate)}
                  {item.hit_rate_interval?.lower == null ? "" : ` · 95%-Intervall ${item.hit_rate_interval.lower}–${item.hit_rate_interval.upper}%`}
                </div>
                <div className="mt-1 text-[10px] font-bold text-violet-600">
                  Relativ zum Benchmark {pct(item.avg_active_return_pct)} · Abdeckung {pct(item.benchmark_coverage_pct)}
                </div>
              </div>
            )) : <div className="text-violet-700">Noch keine ausgewerteten Segmente.</div>}
          </div>
        </div>
        <div className="rounded-xl border border-violet-200 bg-white/80 p-4">
          <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-violet-600">Wiederkehrende Fehler</div>
          <div className="mt-2 space-y-2 text-sm">
            {errors.length ? errors.slice(0, 4).map((item: any) => (
              <div key={item.error} className="flex justify-between gap-3 rounded-lg bg-violet-50 px-3 py-2">
                <span className="font-bold">{label(item.error)}</span><span>{item.count}×</span>
              </div>
            )) : <div className="text-violet-700">Noch keine geschlossenen Trades für Fehler-Attribution.</div>}
          </div>
        </div>
      </div>

      {!!attributions.length && (
        <div className="mt-4 rounded-xl border border-violet-200 bg-white/80 p-4">
          <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-violet-600">Letzte Trade-Attributionen</div>
          <div className="mt-2 grid gap-2 lg:grid-cols-2">
            {attributions.slice(0, 4).map((item: any) => (
              <div key={item.trade_id} className="rounded-lg bg-violet-50 px-3 py-2 text-xs">
                <div className="flex flex-wrap justify-between gap-2 font-bold">
                  <span>{item.ticker || item.trade_id}</span>
                  <span>{label(item.process_quality)} · {label(item.outcome_quality)}</span>
                </div>
                <div className="mt-1 text-violet-700">
                  Netto {pct(item.metrics?.net_pnl_pct)} · Brutto {pct(item.metrics?.gross_pnl_pct)} · R {item.metrics?.r_multiple ?? "offen"}
                </div>
                <div className="mt-1 text-violet-700">
                  Benchmark {item.evidence?.benchmark_symbol || "nicht verfügbar"} {pct(item.metrics?.benchmark_return_pct)} · aktive Rendite {pct(item.metrics?.active_return_pct)}
                  {item.metrics?.benchmark_horizon_hours ? ` · ${item.metrics.benchmark_horizon_hours}h-Messpunkt` : ""}
                </div>
                <div className="mt-1 text-violet-700">
                  MFE {pct(item.metrics?.mfe_pct)} · MAE {pct(item.metrics?.mae_pct)} · Kosten {item.metrics?.execution_cost_value == null ? "nicht verfügbar" : item.metrics.execution_cost_value}
                  {item.metrics?.holding_hours == null ? "" : ` · Haltedauer ${item.metrics.holding_hours} Std.`}
                  {item.primary_error ? ` · ${label(item.primary_error)}` : ""}
                </div>
                <div className="mt-1 text-[10px] font-bold uppercase tracking-[0.08em] text-violet-600">
                  Asset-Daten {label(item.evidence?.asset_features?.availability?.status || "nicht verfügbar")}
                  {!!item.evidence?.asset_features?.availability?.required_missing?.length && ` · fehlt: ${item.evidence.asset_features.availability.required_missing.join(", ")}`}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {!!tradeReviews.length && (
        <div data-testid="paper-learning-trade-reviews" className="mt-4 rounded-xl border border-violet-200 bg-white/80 p-4">
          <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-violet-600">Prüfbare Trade-Reviews</div>
          <div className="mt-2 space-y-2">
            {tradeReviews.slice(0, 6).map((review: any) => (
              <details key={review.trade_id} className="rounded-xl border border-violet-200 bg-violet-50/70 px-3 py-2 text-xs">
                <summary className="cursor-pointer list-none font-black">
                  <span className="flex flex-wrap justify-between gap-2">
                    <span>{review.ticker} · {label(review.setup_type)} · {label(review.direction)}</span>
                    <span className={review.snapshot_integrity?.status === "valid" ? "text-emerald-700" : "text-red-700"}>
                      Snapshot {label(review.snapshot_integrity?.status)}
                    </span>
                  </span>
                </summary>
                <div className="mt-3 grid gap-3 lg:grid-cols-3">
                  <div>
                    <div className="font-extrabold uppercase tracking-[0.08em] text-violet-600">Ursprünglicher Plan</div>
                    <div className="mt-1">Entry {review.original_plan?.entry_price ?? "offen"} · Stop {review.original_plan?.stop_price ?? "offen"} · Ziel {review.original_plan?.target_2 ?? "offen"}</div>
                    <div className="mt-1 text-violet-700">{review.original_plan?.thesis || "These fehlt"}</div>
                  </div>
                  <div>
                    <div className="font-extrabold uppercase tracking-[0.08em] text-violet-600">Tatsächlicher Verlauf</div>
                    <div className="mt-1">Fill {review.actual?.entry_price ?? "offen"} → {review.actual?.closed_price ?? "noch offen"}</div>
                    <div className="mt-1 text-violet-700">{review.actual?.exit_reason || "Exit-Grund fehlt"} · {review.outcomes?.length || 0} Outcomes</div>
                  </div>
                  <div>
                    <div className="font-extrabold uppercase tracking-[0.08em] text-violet-600">Lernurteil</div>
                    <div className="mt-1">{label(review.attribution?.process_quality)} · {label(review.attribution?.outcome_quality)}</div>
                    <div className="mt-1 text-violet-700">Regeln: {review.applied_learning_rule_ids?.length ? review.applied_learning_rule_ids.join(", ") : "keine"}</div>
                  </div>
                </div>
              </details>
            ))}
          </div>
        </div>
      )}

      <div data-testid="paper-learning-rule-lab" className="mt-4 rounded-xl border border-violet-300 bg-white/90 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-violet-600">Paper-Regellabor</div>
            <div className="mt-1 text-base font-black">Champion und Challenger manuell kontrollieren</div>
            <div className="mt-1 text-xs text-violet-700">Aktivierung ist nur bei vollständig grünen Promotion-Gates möglich. Jede Aktion wird auditiert.</div>
          </div>
          <span className="rounded-full bg-red-50 px-3 py-1 text-[10px] font-extrabold uppercase tracking-[0.12em] text-red-700">keine Echtgeldfreigabe</span>
        </div>

        {rules.length ? (
          <>
            <label className="mt-4 block text-[10px] font-extrabold uppercase tracking-[0.14em] text-violet-600" htmlFor="paper-rule-reason">
              Pflichtbegründung für eine Regelaktion
            </label>
            <input
              id="paper-rule-reason"
              value={reviewReason}
              onChange={(event) => setReviewReason(event.target.value)}
              placeholder="Zum Beispiel: Shadow-Daten geprüft, Konzentration weiterhin beobachten."
              maxLength={1000}
              className="mt-1 w-full rounded-xl border border-violet-200 bg-white px-3 py-2 text-sm outline-none focus:border-violet-500"
            />
            {ruleMessage && <div className="mt-2 rounded-lg bg-violet-50 px-3 py-2 text-xs font-bold text-violet-800">{ruleMessage}</div>}
            {rollbackPreview && (
              <div data-testid="paper-learning-rollback-preview" className="mt-3 rounded-xl border border-amber-300 bg-amber-50 p-3 text-xs text-amber-950">
                <div className="font-black">Rollback-Vorschau · noch nicht ausgeführt</div>
                <div className="mt-1">
                  {label(rollbackPreview.current?.status)} → <b>{label(rollbackPreview.restore?.status)}</b>
                  {rollbackPreview.source_action ? ` · macht ${label(rollbackPreview.source_action)} rückgängig` : ""}
                </div>
                <div className="mt-1 text-[10px] text-amber-800">Quelle {rollbackPreview.source_history_id} · ausschließlich Paper-Regel</div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => reviewRule(rollbackPreview.rule_id, "rollback")}
                    disabled={!!ruleBusy || reviewReason.trim().length < 8}
                    className="rounded-lg bg-amber-700 px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.1em] text-white disabled:opacity-40"
                  >
                    {ruleBusy === `${rollbackPreview.rule_id}:rollback` ? "Stellt wieder her …" : "Rollback bestätigen"}
                  </button>
                  <button type="button" onClick={() => setRollbackPreview(null)} className="rounded-lg border border-amber-400 bg-white px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.1em]">
                    Abbrechen
                  </button>
                </div>
              </div>
            )}
            <div className="mt-3 space-y-3">
              {rules.slice(0, 8).map((rule: any) => {
                const evaluation = rule.evaluation || {};
                const checks = evaluation.promotion_checks || {};
                const liveMonitor = evaluation.live_monitor || {};
                const hypothesis = hypothesisById[String(rule.hypothesis_id)] || {};
                const canActivate = rule.status === "eligible_for_paper_review";
                const safetyPaused = liveMonitor.status === "auto_paused";
                const hasHistory = ruleHistory.some((item: any) => String(item.rule_id) === String(rule.id));
                const baseActions = rule.status === "active_paper"
                  ? [["pause", "Pausieren"]]
                  : rule.status === "eligible_for_paper_review"
                    ? [["activate_paper", "Nur Paper aktivieren"], ["pause", "Pausieren"], ["reject", "Ablehnen"]]
                    : rule.status === "shadow"
                      ? [["pause", "Pausieren"], ["reject", "Ablehnen"]]
                      : rule.status === "paused" && safetyPaused
                        ? [["restart_shadow", "Neue Shadow-Version"]]
                      : [];
                const actions = hasHistory && !safetyPaused ? [...baseActions, ["rollback", "Rollback-Vorschau"]] : baseActions;
                return (
                  <div key={rule.id} className="rounded-xl border border-violet-200 bg-violet-50/70 p-3 text-xs">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <div className="font-black">{hypothesis.statement || `Lernregel ${rule.id}`}</div>
                        <div className="mt-1 text-violet-700">Version {rule.version || 1} · {label(rule.status)} · Zukunftsstichprobe n={evaluation.future_closed_trades || 0}</div>
                      </div>
                      <span className={`rounded-full px-2 py-1 text-[9px] font-extrabold uppercase ${canActivate ? "bg-emerald-100 text-emerald-800" : "bg-white text-violet-700"}`}>
                        {canActivate ? "reviewfähig" : "nicht freigabefähig"}
                      </span>
                    </div>
                    <div className="mt-2 grid gap-1 sm:grid-cols-2 xl:grid-cols-5">
                      {[
                        ["100 Outcomes", checks.global_outcomes],
                        ["30 Future Trades", checks.future_closed_trades],
                        ["PF ≥ 1,20", checks.profit_factor],
                        ["Prozess ≥ 80%", checks.process_quality],
                        ["Daten & Konzentration", checks.data_integrity === true && checks.instrument_concentration === true],
                        ["Purge & Embargo", checks.purge_embargo],
                        ["Challenger ≥ Champion", checks.champion_challenger],
                      ].map(([name, passed]) => (
                        <div key={String(name)} className={`rounded-lg px-2 py-1 font-bold ${passed === true ? "bg-emerald-100 text-emerald-800" : "bg-amber-50 text-amber-900"}`}>
                          {passed === true ? "✓" : "○"} {name}
                        </div>
                      ))}
                    </div>
                    {!!evaluation.promotion_blockers?.length && (
                      <div className="mt-2 text-amber-900">Offen: {evaluation.promotion_blockers.map(label).join(" · ")}</div>
                    )}
                    {evaluation.purge_embargo?.embargo_until && (
                      <div className="mt-2 rounded-lg bg-white px-2 py-1.5 text-violet-700">
                        Holdout-Grenze: Embargo bis {evaluation.purge_embargo.embargo_until} · vor Start entfernt {evaluation.purge_embargo.purged_trade_ids?.length || 0} · zusätzlich ausgeschlossen {evaluation.excluded_trade_count_by_embargo || 0}
                      </div>
                    )}
                    {evaluation.champion_challenger && (
                      <div className="mt-2 grid gap-2 rounded-lg bg-white p-2 sm:grid-cols-2">
                        <div>
                          <div className="font-extrabold uppercase tracking-[0.08em] text-violet-600">Champion</div>
                          <div className="mt-1">Erwartung {pct(evaluation.champion_challenger.champion?.expectancy_pct)} · PF {evaluation.champion_challenger.champion?.profit_factor ?? "offen"} · DD {pct(evaluation.champion_challenger.champion?.max_drawdown_pct_points)}</div>
                        </div>
                        <div>
                          <div className="font-extrabold uppercase tracking-[0.08em] text-violet-600">Challenger</div>
                          <div className="mt-1">Erwartung {pct(evaluation.champion_challenger.challenger?.expectancy_pct)} · PF {evaluation.champion_challenger.challenger?.profit_factor ?? "offen"} · DD {pct(evaluation.champion_challenger.challenger?.max_drawdown_pct_points)}</div>
                          <div className="mt-1 text-violet-700">Ausgewählt {evaluation.champion_challenger.challenger?.selected_trades || 0} · abgelehnt {evaluation.champion_challenger.challenger?.rejected_trades || 0} · Δ Erwartung {pct(evaluation.champion_challenger.expectancy_delta_pct)}</div>
                        </div>
                      </div>
                    )}
                    {liveMonitor.status && (
                      <div className={`mt-2 rounded-lg p-2 ${safetyPaused ? "bg-red-100 text-red-900" : liveMonitor.status === "warning" ? "bg-amber-100 text-amber-900" : "bg-white text-violet-700"}`}>
                        <div className="font-extrabold uppercase tracking-[0.08em]">Live-Monitor · {label(liveMonitor.status)}</div>
                        <div className="mt-1">
                          n={liveMonitor.observations || 0}/{liveMonitor.minimum_observations || policy.active_min_monitor_trades || 10}
                          {liveMonitor.metrics?.expectancy_pct == null ? "" : ` · Erwartung ${pct(liveMonitor.metrics.expectancy_pct)}`}
                          {liveMonitor.metrics?.profit_factor == null ? "" : ` · PF ${liveMonitor.metrics.profit_factor}`}
                          {` · Verlustserie ${liveMonitor.trailing_loss_streak || 0}`}
                        </div>
                        {!!liveMonitor.pause_reasons?.length && <div className="mt-1 font-bold">Kill-Switch: {liveMonitor.pause_reasons.map(label).join(" · ")}</div>}
                        {!!liveMonitor.warning_reasons?.length && <div className="mt-1 font-bold">Warnung: {liveMonitor.warning_reasons.map(label).join(" · ")}</div>}
                      </div>
                    )}
                    {!!actions.length && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {actions.map(([action, name]: string[]) => (
                          <button
                            key={action}
                            type="button"
                            onClick={() => action === "rollback" ? previewRollback(rule.id) : reviewRule(rule.id, action)}
                            disabled={!!ruleBusy || (action !== "rollback" && reviewReason.trim().length < 8)}
                            className="rounded-lg border border-violet-300 bg-white px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-[0.1em] text-violet-800 disabled:opacity-40"
                          >
                            {ruleBusy === `${rule.id}:${action}` ? "Speichert …" : name}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </>
        ) : (
          <div className="mt-3 rounded-lg bg-violet-50 px-3 py-3 text-sm text-violet-700">Noch keine Lernregel. Hypothesen werden erst ab ausreichender negativer Evidenz als Shadow-Regel angelegt.</div>
        )}
        {!!ruleHistory.length && (
          <div data-testid="paper-learning-rule-history" className="mt-4 border-t border-violet-200 pt-3">
            <div className="text-[9px] font-extrabold uppercase tracking-[0.14em] text-violet-600">Letzte Regeländerungen</div>
            <div className="mt-2 grid gap-2 lg:grid-cols-2">
              {ruleHistory.slice(0, 6).map((item: any) => (
                <div key={item.id} className="rounded-lg bg-violet-50 px-3 py-2 text-[10px]">
                  <div className="flex flex-wrap justify-between gap-2 font-black">
                    <span>{label(item.action)} · {label(item.from_status)} → {label(item.to_status)}</span>
                    <span>{item.created_at ? new Date(item.created_at).toLocaleString("de-DE") : ""}</span>
                  </div>
                  <div className="mt-1 text-violet-700">{item.reason}</div>
                  <div className="mt-1 truncate text-violet-500" title={item.audit_event_id || item.id}>Audit {item.audit_event_id || item.id}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
