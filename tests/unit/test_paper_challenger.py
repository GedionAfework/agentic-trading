from datetime import UTC, datetime, timedelta

from private_trading_agents.coin_desk import narrate_coin
from private_trading_backtest import naoldesk as nd
from private_trading_paper_trade.challenger import (
    CHALLENGER,
    daily_from_hourly,
    summarize,
)
from private_trading_paper_trade.soak_metrics import ClosedSoakTrade
from private_trading_paper_trade.supervisor_rules import (
    ModelSample,
    SupervisorSnapshot,
    evaluate_supervisor,
    should_pause,
)

T0 = datetime(2026, 11, 5, tzinfo=UTC)


def _hourly(hours: int) -> nd.Bars:
    t = [T0 + timedelta(hours=i) for i in range(hours)]
    return nd.Bars(t, [float(i) for i in range(hours)], [i + 2.0 for i in range(hours)],
                   [i - 1.0 for i in range(hours)], [i + 1.0 for i in range(hours)],
                   [1.0] * hours)


def test_challenger_is_paper_only_and_forward_dated() -> None:
    assert CHALLENGER["paper_only"] is True
    assert CHALLENGER["live_alerts_allowed"] is False
    assert CHALLENGER["forward_start"] == datetime(2026, 11, 5, tzinfo=UTC)
    assert CHALLENGER["setup"] == "A" and CHALLENGER["exit_tf"] == "4h"


def test_daily_candles_use_complete_utc_days_only() -> None:
    days = daily_from_hourly(_hourly(24 * 2 + 5))  # 2 full days + 5 hours
    assert len(days.t) == 2
    assert days.o[0] == 0.0 and days.c[0] == 24.0
    assert days.h[0] == 25.0 and days.l[0] == -1.0
    assert days.v[0] == 24.0


def test_summary_of_empty_ledger() -> None:
    s = summarize([])
    assert s["closed_trades"] == 0 and s["win_rate"] is None and s["mean_r"] is None


def test_challenger_breach_alerts_but_never_pauses_real_paper() -> None:
    losing = ModelSample(
        code="doge-naoldesk-breakout-v2 (challenger)",
        trades=[ClosedSoakTrade(-1.0, T0 + timedelta(hours=i), None) for i in range(25)],
        alert_only=True,
    )
    findings = evaluate_supervisor(SupervisorSnapshot(samples=[losing]))
    assert {f.code for f in findings} >= {"drawdown_breach", "negative_expectancy"}
    assert not should_pause(findings)


def test_integrity_defects_still_pause() -> None:
    findings = evaluate_supervisor(SupervisorSnapshot(integrity_defects=["x"]))
    assert should_pause(findings)


def test_desk_shows_challenger_vs_incumbent() -> None:
    coin = {
        "symbol": "DOGE/USDT", "headline": "WAIT", "role": "paper", "context": "",
        "reasons": [], "levels": None, "research": None, "model_code": "doge-v1",
        "challenger": {
            "label": CHALLENGER["label"],
            "forward_start": "2026-11-05T00:00:00+00:00",
            "challenger": {"closed_trades": 4, "win_rate": 0.5, "mean_r": 0.31},
            "incumbent": {"closed_trades": 2, "mean_r": -0.2},
        },
    }
    text = narrate_coin(coin)
    assert "4 forward trades, 50.0% wins, +0.310R vs incumbent 2 trades, -0.200R" in text
    assert "paper only, since 2026-11-05" in text
