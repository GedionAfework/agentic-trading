"""Portfolio-level paper risk gates for correlated specialist signals."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(slots=True, frozen=True)
class OpenExposure:
    symbol: str
    asset_class: str
    direction: str
    risk_pct: Decimal


@dataclass(slots=True, frozen=True)
class PortfolioRiskPolicy:
    max_total_open_risk_pct: Decimal = Decimal("2")
    max_crypto_open_risk_pct: Decimal = Decimal("1")
    max_usd_cluster_risk_pct: Decimal = Decimal("1")
    max_daily_loss_pct: Decimal = Decimal("1.5")
    one_position_per_symbol: bool = True


@dataclass(slots=True, frozen=True)
class PortfolioRiskInput:
    proposed_symbol: str
    proposed_asset_class: str
    proposed_direction: str
    proposed_risk_pct: Decimal
    open_exposures: tuple[OpenExposure, ...] = ()
    daily_realized_pnl_pct: Decimal = Decimal("0")


@dataclass(slots=True)
class PortfolioRiskResult:
    approved: bool
    blockers: list[str] = field(default_factory=list)
    total_open_risk_pct: Decimal = Decimal("0")
    correlated_risk_pct: Decimal = Decimal("0")


def _has_usd_cluster(symbol: str) -> bool:
    base, _, quote = symbol.partition("/")
    return base in {"USD", "USDT"} or quote in {"USD", "USDT"}


def assess_portfolio_risk(
    risk_input: PortfolioRiskInput,
    policy: PortfolioRiskPolicy | None = None,
) -> PortfolioRiskResult:
    cfg = policy or PortfolioRiskPolicy()
    blockers: list[str] = []
    if risk_input.proposed_risk_pct <= 0:
        blockers.append("non_positive_proposed_risk")
    if (
        cfg.one_position_per_symbol
        and any(
            item.symbol == risk_input.proposed_symbol
            for item in risk_input.open_exposures
        )
    ):
        blockers.append("symbol_already_open")
    if risk_input.daily_realized_pnl_pct <= -cfg.max_daily_loss_pct:
        blockers.append("daily_loss_stop")

    total = sum(
        (item.risk_pct for item in risk_input.open_exposures),
        Decimal("0"),
    ) + risk_input.proposed_risk_pct
    if total > cfg.max_total_open_risk_pct:
        blockers.append("total_open_risk_exceeded")

    if risk_input.proposed_asset_class == "crypto":
        correlated = sum(
            (
                item.risk_pct
                for item in risk_input.open_exposures
                if item.asset_class == "crypto"
            ),
            Decimal("0"),
        ) + risk_input.proposed_risk_pct
        if correlated > cfg.max_crypto_open_risk_pct:
            blockers.append("crypto_cluster_risk_exceeded")
    elif _has_usd_cluster(risk_input.proposed_symbol):
        correlated = sum(
            (
                item.risk_pct
                for item in risk_input.open_exposures
                if item.asset_class == "forex" and _has_usd_cluster(item.symbol)
            ),
            Decimal("0"),
        ) + risk_input.proposed_risk_pct
        if correlated > cfg.max_usd_cluster_risk_pct:
            blockers.append("usd_cluster_risk_exceeded")
    else:
        correlated = risk_input.proposed_risk_pct

    return PortfolioRiskResult(
        approved=not blockers,
        blockers=blockers,
        total_open_risk_pct=total,
        correlated_risk_pct=correlated,
    )


def specialist_risk_pct(
    *,
    objective: str,
    mean_r: float,
    max_drawdown_r: float | None,
) -> Decimal:
    """Conservative paper sizing; stronger backtests never exceed 0.5% risk."""
    if mean_r <= 0:
        return Decimal("0")
    risk = Decimal("0.25") if objective == "win_rate" else Decimal("0.35")
    if mean_r >= 0.15:
        risk += Decimal("0.10")
    if max_drawdown_r is not None and max_drawdown_r > 15:
        risk -= Decimal("0.10")
    return min(Decimal("0.5"), max(Decimal("0.1"), risk))
