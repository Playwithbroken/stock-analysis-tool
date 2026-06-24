from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class StrategyDefinition:
    id: str
    label: str
    horizon: str
    asset_classes: List[str]
    setup_types: List[str]
    objective: str
    quality_gates: List[str]
    trigger_template: str
    invalidation_template: str
    risk_notes: List[str]
    real_world_gate: str
    source_basis: str
    min_paper_trades: int = 12
    min_hit_rate: float = 55.0
    max_avg_loss_pct: float = -1.5
    tags: List[str] = field(default_factory=list)


class StrategyLibrary:
    """Single source of truth for strategy gates used by paper learning."""

    STRATEGIES: List[StrategyDefinition] = [
        StrategyDefinition(
            id="core_quality_compounder",
            label="Core Quality Compounder",
            horizon="months-years",
            asset_classes=["equity", "etf"],
            setup_types=["quality_compounder", "dividend_quality", "etf_momentum"],
            objective="Hold strong businesses, dividend engines and broad ETFs when fundamentals and trend agree.",
            quality_gates=[
                "Positive or improving free cash flow",
                "Revenue and margin trend are stable or improving",
                "Valuation is not extreme versus growth quality",
                "Position risk fits long-term account allocation",
            ],
            trigger_template="{ticker} holds trend support while fundamentals and guidance stay intact.",
            invalidation_template="{ticker} loses fundamental quality, breaks the risk level, or guidance deteriorates.",
            risk_notes=[
                "No leverage in the core sleeve.",
                "Use wider stops and smaller sizing than day-trading setups.",
            ],
            real_world_gate="At least 12 paper checks, no unresolved thesis break, and manual portfolio fit review.",
            source_basis="Factor research: quality, value discipline and low-volatility risk control.",
            min_paper_trades=12,
            min_hit_rate=52,
            tags=["long_term", "quality", "dividend"],
        ),
        StrategyDefinition(
            id="momentum_follow_through",
            label="Momentum Follow-Through",
            horizon="days-weeks",
            asset_classes=["equity", "etf", "crypto"],
            setup_types=["etf_momentum", "crypto_flow", "insider_follow", "political_copy_delay"],
            objective="Trade strength only when price, volume and context confirm the signal.",
            quality_gates=[
                "Relative strength is positive",
                "Volume or breadth confirms the move",
                "Signal is fresh enough to still matter",
                "Stop and target are defined before entry",
            ],
            trigger_template="{ticker} confirms directional follow-through with clean price action and volume.",
            invalidation_template="{ticker} fails follow-through, loses the stop zone, or the market regime turns against the setup.",
            risk_notes=[
                "No averaging down after failed confirmation.",
                "Reduce size in mixed or risk-off market regimes.",
            ],
            real_world_gate="At least 20 decisive paper outcomes with >=55% hit rate after costs/slippage assumption.",
            source_basis="Academic momentum evidence plus execution gates for trend confirmation.",
            min_paper_trades=20,
            min_hit_rate=55,
            tags=["swing", "momentum", "trend"],
        ),
        StrategyDefinition(
            id="earnings_guidance_reaction",
            label="Earnings / Guidance Reaction",
            horizon="1-10 days",
            asset_classes=["equity"],
            setup_types=["earnings_reaction", "guidance_revision", "revenue_goal_check"],
            objective="React to revenue, EPS, margin and guidance quality after the market confirms the interpretation.",
            quality_gates=[
                "Revenue and EPS surprise are understood separately",
                "Guidance and margin comments are checked",
                "Analyst revisions or management tone confirm the read",
                "First reaction is not purely gap-chasing",
            ],
            trigger_template="{ticker} confirms the earnings read after guidance, margin and price reaction align.",
            invalidation_template="{ticker} fades the earnings move or the quality of the beat/guide is weaker than headline suggests.",
            risk_notes=[
                "Avoid opening before earnings unless defined-risk only.",
                "Treat huge gaps as higher risk, not automatic confirmation.",
            ],
            real_world_gate="Needs repeated paper evidence around actual earnings events before real-money use.",
            source_basis="Event-driven earnings analysis with revenue/guidance verification.",
            min_paper_trades=16,
            min_hit_rate=56,
            tags=["earnings", "event", "guidance"],
        ),
        StrategyDefinition(
            id="macro_event_edge",
            label="Macro Event Edge",
            horizon="intraday-weeks",
            asset_classes=["equity", "etf", "crypto", "fx_proxy"],
            setup_types=["macro_event", "central_bank_shift", "oil_energy_shock", "policy_reaction"],
            objective="Translate macro shocks, central banks, elections, war and policy into affected assets and risk action.",
            quality_gates=[
                "Event type and country/region are identified",
                "Affected assets or sectors are explicit",
                "Impact score is high enough",
                "Trigger and invalidation are written before any paper trade",
            ],
            trigger_template="{ticker} reacts in line with the macro event while liquidity and cross-asset confirmation agree.",
            invalidation_template="The macro event is walked back, impact is priced out, or affected assets do not confirm.",
            risk_notes=[
                "Do not chase unverified headlines.",
                "Cooldown duplicate alerts; trade only confirmed impact.",
            ],
            real_world_gate="Only after alert quality and paper outcomes prove that the event type has edge.",
            source_basis="Official macro data, central-bank calendar, event classification and cross-asset confirmation.",
            min_paper_trades=18,
            min_hit_rate=55,
            tags=["macro", "telegram", "risk"],
        ),
        StrategyDefinition(
            id="small_cap_future_star",
            label="Small-Cap Future Star",
            horizon="weeks-years",
            asset_classes=["equity"],
            setup_types=["small_cap_discovery", "product_catalyst", "ipo_watch"],
            objective="Find early-stage companies with real growth, liquidity and catalysts while filtering hype.",
            quality_gates=[
                "Revenue growth or product adoption is verifiable",
                "Cash runway and dilution risk are checked",
                "News is source-backed, not rumor-only",
                "Liquidity is sufficient for realistic entry and exit",
            ],
            trigger_template="{ticker} confirms a real catalyst with volume, filings/news quality and no immediate financing red flag.",
            invalidation_template="{ticker} loses catalyst credibility, shows dilution stress, or liquidity disappears.",
            risk_notes=[
                "Use smaller sizing than liquid large-cap setups.",
                "Reject pump-like moves without filings or credible sources.",
            ],
            real_world_gate="Needs manual due diligence plus paper evidence; never auto-real-money.",
            source_basis="Growth/catalyst screening combined with liquidity and fraud-risk filters.",
            min_paper_trades=20,
            min_hit_rate=58,
            tags=["small_cap", "discovery", "ipo"],
        ),
        StrategyDefinition(
            id="defined_risk_options",
            label="Defined-Risk Calls / Puts",
            horizon="1-20 days",
            asset_classes=["option"],
            setup_types=["option_call_learning", "option_put_learning"],
            objective="Use calls and puts only when the underlying setup is strong and max loss is predefined.",
            quality_gates=[
                "Underlying signal is high quality",
                "Strike, expiry, spread and IV are reviewed manually",
                "Premium risk fits the demo account gate",
                "Time horizon matches expected catalyst",
            ],
            trigger_template="The underlying confirms direction before the option is paper-tested.",
            invalidation_template="Underlying momentum fades, IV/spread is unattractive, or time decay invalidates the setup.",
            risk_notes=[
                "Max loss is premium; no naked option selling.",
                "No real-money options until enough paper evidence exists.",
            ],
            real_world_gate="At least 20 decisive paper option checks and >=55% hit rate; still manual review only.",
            source_basis="Cboe/FINRA options education: defined risk, suitability and risk disclosure.",
            min_paper_trades=20,
            min_hit_rate=55,
            tags=["options", "paper_only", "defined_risk"],
        ),
    ]

    @classmethod
    def all(cls) -> List[Dict[str, Any]]:
        return [cls._to_dict(item) for item in cls.STRATEGIES]

    @classmethod
    def find_for_playbook(cls, playbook: Dict[str, Any]) -> Dict[str, Any]:
        setup_type = str(playbook.get("setup_type") or "")
        asset_class = str(playbook.get("asset_class") or "")
        for strategy in cls.STRATEGIES:
            if setup_type in strategy.setup_types:
                return cls._to_dict(strategy)
        for strategy in cls.STRATEGIES:
            if asset_class in strategy.asset_classes:
                return cls._to_dict(strategy)
        return cls._to_dict(cls.STRATEGIES[1])

    @classmethod
    def build_readiness(cls, trades: List[Dict[str, Any]], outcomes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for strategy in cls.STRATEGIES:
            setup_set = set(strategy.setup_types)
            trade_rows = [item for item in trades if str(item.get("setup_type") or "") in setup_set]
            outcome_rows = [item for item in outcomes if str(item.get("setup_type") or "") in setup_set]
            decisive = [item for item in outcome_rows if item.get("result") in {"hit", "miss"}]
            hits = [item for item in decisive if item.get("result") == "hit"]
            misses = [item for item in decisive if item.get("result") == "miss"]
            closed = [
                item
                for item in trade_rows
                if item.get("status") == "closed" and item.get("realized_pnl_pct") is not None
            ]
            avg_pnl = (
                round(sum(float(item.get("realized_pnl_pct") or 0) for item in closed) / len(closed), 2)
                if closed
                else 0
            )
            hit_rate = round((len(hits) / max(1, len(decisive))) * 100, 1) if decisive else 0
            ready = len(decisive) >= strategy.min_paper_trades and hit_rate >= strategy.min_hit_rate and avg_pnl >= strategy.max_avg_loss_pct
            if ready:
                status = "manual_review_ready"
                next_step = "Eligible for manual real-world review, not automatic execution."
            elif decisive:
                status = "learning"
                next_step = f"Need {max(0, strategy.min_paper_trades - len(decisive))} more decisive checks or better hit rate."
            else:
                status = "not_started"
                next_step = "Collect paper outcomes before trusting this strategy."
            rows.append(
                {
                    **cls._to_dict(strategy),
                    "paper_trades": len(trade_rows),
                    "decisive_checks": len(decisive),
                    "hits": len(hits),
                    "misses": len(misses),
                    "hit_rate": hit_rate,
                    "avg_closed_pnl_pct": avg_pnl,
                    "status": status,
                    "real_world_ready": ready,
                    "next_step": next_step,
                }
            )
        return rows

    @staticmethod
    def _to_dict(strategy: StrategyDefinition) -> Dict[str, Any]:
        return {
            "id": strategy.id,
            "label": strategy.label,
            "horizon": strategy.horizon,
            "asset_classes": list(strategy.asset_classes),
            "setup_types": list(strategy.setup_types),
            "objective": strategy.objective,
            "quality_gates": list(strategy.quality_gates),
            "trigger_template": strategy.trigger_template,
            "invalidation_template": strategy.invalidation_template,
            "risk_notes": list(strategy.risk_notes),
            "real_world_gate": strategy.real_world_gate,
            "source_basis": strategy.source_basis,
            "min_paper_trades": strategy.min_paper_trades,
            "min_hit_rate": strategy.min_hit_rate,
            "max_avg_loss_pct": strategy.max_avg_loss_pct,
            "tags": list(strategy.tags),
        }

