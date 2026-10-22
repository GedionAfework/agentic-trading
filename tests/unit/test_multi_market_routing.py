from datetime import UTC, datetime, timedelta
from decimal import Decimal

from private_trading_agents.scanner import (
    evaluate_multi_market_closed_candle,
    evaluate_specialist_closed_candle,
)
from private_trading_agents.workflow import DecisionAction, run_specialist_decision
from private_trading_features.types import CandleBar
from private_trading_risk.portfolio import OpenExposure
from private_trading_strategies.multi_market import (
    MarketRegime,
    TradingObjective,
    ValidationStats,
    classify_market_regime,
    resolve_market_model,
)
from private_trading_strategies.specialist_registry import (
    ValidatedSpecialistModel,
    resolve_specialist_model,
)
from private_trading_strategies.specialists import (
    TREND_REGIMES,
    SpecialistAction,
    SpecialistConfig,
    SpecialistSignal,
    StrategyFamily,
)


def _bars(count: int, *, timeframe_hours: int = 1) -> list[CandleBar]:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    rows: list[CandleBar] = []
    for index in range(count):
        close = Decimal("100") + Decimal(index) / Decimal("10")
        rows.append(
            CandleBar(
                open_time=start + timedelta(hours=index * timeframe_hours),
                open=close - Decimal("0.1"),
                high=close + Decimal("0.5"),
                low=close - Decimal("0.5"),
                close=close,
                volume=Decimal("100"),
                is_final=True,
            )
        )
    return rows


def test_regime_uses_completed_higher_timeframe_and_routes_only_sol() -> None:
    regime = classify_market_regime(_bars(120), _bars(60, timeframe_hours=4))
    assert regime == MarketRegime.TREND_HIGH_VOL
    assert (
        resolve_market_model(
            symbol="SOL/USDT",
            regime=regime,
            objective=TradingObjective.WIN_RATE,
        )
        is not None
    )
    assert (
        resolve_market_model(
            symbol="BTC/USDT",
            regime=regime,
            objective=TradingObjective.PROFIT,
        )
        is None
    )


def test_unvalidated_market_fails_closed_to_wait() -> None:
    outcome = evaluate_multi_market_closed_candle(
        _bars(120),
        _bars(60, timeframe_hours=4),
        symbol="BTC/USDT",
        asset_class="crypto",
        objective=TradingObjective.PROFIT,
        fresh=True,
        actionable=True,
    )
    assert outcome.status == "no_validated_model"
    assert outcome.action == "WAIT"
    assert outcome.publishable is False
    assert outcome.paper_eligible is False


def test_doge_profit_model_is_paper_eligible_only() -> None:
    outcome = evaluate_specialist_closed_candle(
        _bars(120),
        _bars(60, timeframe_hours=4),
        symbol="DOGE/USDT",
        asset_class="crypto",
        objective=TradingObjective.PROFIT,
        fresh=True,
        actionable=True,
    )
    assert outcome.publishable is False
    assert outcome.paper_eligible is False or outcome.action == "NO_SETUP"
    assert "paper_model=doge-mtf-bos-volume-profit:v1" in outcome.notes
    assert "objective=profit" in outcome.notes


def test_specialist_router_fails_closed_when_registry_is_empty() -> None:
    assert (
        resolve_specialist_model(
            symbol="BTC/USDT",
            regime=MarketRegime.TREND_HIGH_VOL,
            objective=TradingObjective.PROFIT,
        )
        is None
    )
    outcome = evaluate_specialist_closed_candle(
        _bars(120),
        _bars(60, timeframe_hours=4),
        symbol="BTC/USDT",
        asset_class="crypto",
        objective=TradingObjective.PROFIT,
        fresh=True,
        actionable=True,
    )
    assert outcome.action == "WAIT"
    assert outcome.publishable is False
    assert outcome.paper_eligible is False


def test_empty_specialist_registry_falls_back_to_sol_paper_incumbents() -> None:
    outcome = evaluate_specialist_closed_candle(
        _bars(120),
        _bars(60, timeframe_hours=4),
        symbol="SOL/USDT",
        asset_class="crypto",
        objective=TradingObjective.WIN_RATE,
        fresh=True,
        actionable=True,
    )
    assert outcome.status != "no_validated_model"
    assert outcome.publishable is False
    assert "paper_model=sol-mtf-bos-volume-scale-out:v2" in outcome.notes


def _paper_specialist_model(**overrides: object) -> ValidatedSpecialistModel:
    values: dict[str, object] = {
        "config": SpecialistConfig(
            code="btc-breakout-paper",
            family=StrategyFamily.TREND_BREAKOUT,
            symbol="BTC/USDT",
            asset_class="crypto",
            allowed_regimes=TREND_REGIMES,
            rr=Decimal("2"),
            max_bars=40,
        ),
        "objective": TradingObjective.PROFIT,
        "regimes": TREND_REGIMES,
        "validation": ValidationStats(
            trades=120,
            win_rate=0.55,
            mean_r=0.2,
            profit_factor=1.4,
            max_drawdown_r=8.0,
        ),
        "paper_only": True,
        "live_alerts_allowed": False,
    }
    values.update(overrides)
    return ValidatedSpecialistModel(**values)  # type: ignore[arg-type]


def _enter_signal() -> SpecialistSignal:
    return SpecialistSignal(
        action=SpecialistAction.ENTER,
        family=StrategyFamily.TREND_BREAKOUT,
        config_code="btc-breakout-paper",
        direction="long",
        entry_reference=Decimal("100"),
        stop_price=Decimal("99"),
        target_price=Decimal("102"),
    )


def test_specialist_decision_blocks_live_alerts_and_duplicate_symbol_risk() -> None:
    bars = _bars(80)
    live = run_specialist_decision(
        bars,
        symbol="BTC/USDT",
        timeframe="1h",
        asset_class="crypto",
        model=_paper_specialist_model(live_alerts_allowed=True),
        signal=_enter_signal(),
    )
    assert live.action == DecisionAction.WAIT
    assert "specialist_not_paper_only" in live.hard_blockers

    duplicate = run_specialist_decision(
        bars,
        symbol="BTC/USDT",
        timeframe="1h",
        asset_class="crypto",
        model=_paper_specialist_model(),
        signal=_enter_signal(),
        open_exposures=(
            OpenExposure("BTC/USDT", "crypto", "long", Decimal("0.4")),
        ),
    )
    assert duplicate.action == DecisionAction.WAIT
    assert "symbol_already_open" in duplicate.hard_blockers
