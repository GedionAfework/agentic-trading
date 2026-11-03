import ast
import inspect
from datetime import UTC, datetime, timedelta

from private_trading_paper_trade import supervisor as supervisor_mod
from private_trading_paper_trade.soak_metrics import ClosedSoakTrade
from private_trading_paper_trade.supervisor import plan_actions
from private_trading_paper_trade.supervisor_rules import (
    ModelSample,
    SupervisorSnapshot,
    alert_text,
    evaluate_supervisor,
    should_pause,
)

T0 = datetime(2026, 10, 12, tzinfo=UTC)


def _sample(code: str, rs: list[float], extra: float | None = 0.5) -> ModelSample:
    return ModelSample(
        code=code,
        trades=[
            ClosedSoakTrade(
                realized_r=r,
                closed_at=T0 + timedelta(hours=i),
                extra_cost_bps_vs_research=extra,
            )
            for i, r in enumerate(rs)
        ],
    )


def _codes(snap: SupervisorSnapshot) -> set[str]:
    return {f.code for f in evaluate_supervisor(snap)}


def test_healthy_soak_has_no_findings() -> None:
    snap = SupervisorSnapshot(samples=[_sample("sol-v1", [3.0, -1.0, -1.0, 3.0] * 6)])
    assert evaluate_supervisor(snap) == []


def test_empty_soak_is_not_alarming() -> None:
    assert evaluate_supervisor(SupervisorSnapshot(samples=[_sample("sol-v1", [])])) == []


def test_drawdown_over_kill_rule_pauses() -> None:
    snap = SupervisorSnapshot(samples=[_sample("sol-v1", [3.0] + [-1.0] * 21)])
    findings = evaluate_supervisor(snap)
    assert "drawdown_breach" in {f.code for f in findings}
    assert should_pause(findings)


def test_drawdown_warning_does_not_pause() -> None:
    findings = evaluate_supervisor(
        SupervisorSnapshot(samples=[_sample("sol-v1", [3.0, 3.0] + [-1.0] * 16)])
    )
    assert {f.code for f in findings} == {"drawdown_warning"}
    assert not should_pause(findings)


def test_negative_expectancy_needs_twenty_trades() -> None:
    nineteen = SupervisorSnapshot(samples=[_sample("sol-v1", [-0.1] * 19)])
    twenty = SupervisorSnapshot(samples=[_sample("sol-v1", [-0.1] * 20)])
    assert "negative_expectancy" not in _codes(nineteen)
    assert "negative_expectancy" in _codes(twenty)


def test_fill_gap_warns_early_and_pauses_at_twenty() -> None:
    wins = [3.0, -1.0]
    early = SupervisorSnapshot(samples=[_sample("sol-v1", wins * 3, extra=2.5)])
    late = SupervisorSnapshot(samples=[_sample("sol-v1", wins * 10, extra=2.5)])
    assert _codes(early) == {"fill_gap_warning"}
    assert "fill_gap_breach" in _codes(late)


def test_models_are_judged_separately() -> None:
    snap = SupervisorSnapshot(
        samples=[
            _sample("sol-v1", [3.0, -1.0] * 10),
            _sample("doge-v1", [-1.0] * 22),
        ]
    )
    findings = evaluate_supervisor(snap)
    assert {f.subject for f in findings} == {"doge-v1"}


def test_ops_findings() -> None:
    snap = SupervisorSnapshot(
        stale_symbols=["BTC/USDT"],
        integrity_defects=["x:open_without_entry"],
        failed_scan_runs=3,
        daily_loss_stop_hit=True,
        auto_open_enabled=False,
    )
    findings = {f.code: f for f in evaluate_supervisor(snap)}
    assert findings["integrity_defects"].pauses_auto_open
    assert not findings["stale_feed"].pauses_auto_open
    assert findings["scanner_failures"].severity == "warn"
    assert findings["daily_loss_stop"].severity == "info"
    assert findings["auto_open_paused"].severity == "info"


def test_plan_alerts_only_on_new_findings() -> None:
    findings = evaluate_supervisor(SupervisorSnapshot(stale_symbols=["ETH/USDT"]))
    first = plan_actions(findings, previous_keys=set(), auto_open_enabled=True)
    assert first["send_alert"] and not first["pause"]
    again = plan_actions(
        findings, previous_keys=set(first["current_keys"]), auto_open_enabled=True
    )
    assert not again["send_alert"]


def test_plan_sends_all_clear_once() -> None:
    cleared = plan_actions([], previous_keys={"stale_feed:ETH/USDT"}, auto_open_enabled=True)
    assert cleared["send_alert"]
    assert cleared["cleared"] == ["stale_feed:ETH/USDT"]
    quiet = plan_actions([], previous_keys=set(), auto_open_enabled=True)
    assert not quiet["send_alert"]


def test_plan_never_resumes_and_does_not_re_pause() -> None:
    breach = evaluate_supervisor(
        SupervisorSnapshot(samples=[_sample("sol-v1", [-1.0] * 22)])
    )
    first = plan_actions(breach, previous_keys=set(), auto_open_enabled=True)
    assert first["pause"]
    # Already paused: nothing more to do, and healthy state does not resume.
    assert not plan_actions(breach, previous_keys=set(), auto_open_enabled=False)["pause"]
    healthy = plan_actions([], previous_keys=set(first["current_keys"]), auto_open_enabled=False)
    assert "resume" not in healthy and not healthy["pause"]


def test_supervisor_source_never_enables_auto_open() -> None:
    """Static guard: the module only ever writes enabled=False."""
    tree = ast.parse(inspect.getsource(supervisor_mod))
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and key.value == "enabled":
                    assert isinstance(value, ast.Constant) and value.value is False
    source = inspect.getsource(supervisor_mod)
    for forbidden in ("accept_decision", "cancel_trade", "_close_trade", "set_kill_switch"):
        assert forbidden not in source


def test_alert_text_is_grounded_and_not_an_instruction() -> None:
    findings = evaluate_supervisor(
        SupervisorSnapshot(samples=[_sample("sol-v1", [-1.0] * 22)])
    )
    text = alert_text(findings, paused_now=True)
    assert "paused" in text and "/settings paper on" in text
    assert "Nothing here is a trade instruction" in text
