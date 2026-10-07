from private_trading_agents.explain import explanation_invents_numbers, grounded_explanation
from private_trading_agents.workflow import CitationRef, DecisionAction, run_decision_workflow
from private_trading_backtest.fixtures import (
    FIXTURE_SYMBOL,
    FIXTURE_TIMEFRAME,
    frozen_bos_long_fixture,
)
from private_trading_decision.matrix import VECTOR_NAMES
from private_trading_decision.predict import LoadedModel


def _bars():
    return frozen_bos_long_fixture()


def _run(**kwargs):
    return run_decision_workflow(
        _bars(),
        symbol=FIXTURE_SYMBOL,
        timeframe=FIXTURE_TIMEFRAME,
        **kwargs,
    )


def test_no_setup_is_first_class() -> None:
    snapshot = _run(bar_index=19)
    assert snapshot.action == DecisionAction.NO_SETUP
    assert snapshot.setup_state == "no_setup"
    assert "NO_SETUP" in snapshot.explanation
    assert "Knowledge citations: none" in snapshot.explanation
    assert snapshot.explanation_source == "deterministic"


def test_stale_data_waits_and_cites_blocker() -> None:
    snapshot = _run(bar_index=35, data_fresh=False)
    assert snapshot.action == DecisionAction.WAIT
    assert "stale_market_data" in snapshot.hard_blockers
    assert "stale_market_data" in snapshot.explanation
    assert snapshot.risk_approved is False


def test_open_position_without_setup_exits() -> None:
    snapshot = _run(bar_index=19, position_state="open")
    assert snapshot.action == DecisionAction.EXIT
    assert snapshot.confidence_band == "none"


def test_ranker_cannot_override_closed_gates() -> None:
    artifact = {
        "kind": "logistic_ranker",
        "weights": [5.0] * len(VECTOR_NAMES),
        "bias": 5.0,
        "feature_names": list(VECTOR_NAMES),
        "abstention_threshold": 0.1,
    }
    snapshot = _run(bar_index=19, model=LoadedModel(artifact), model_mode="champion")
    assert snapshot.action == DecisionAction.NO_SETUP
    assert snapshot.model_score is None
    agents = [step["agent"] for step in snapshot.workflow]
    assert agents[:3] == ["AG-01", "AG-04", "AG-03"]
    assert {"AG-05", "AG-06", "AG-07", "AG-09", "AG-02"} <= set(agents)


def test_citation_is_named_and_invented_numbers_are_rejected() -> None:
    snapshot = _run(
        bar_index=19,
        citations=[CitationRef(citation_id="cite-wyk-1", excerpt="BOS plus volume.")],
    )
    assert "cite-wyk-1" in snapshot.explanation
    facts = {
        "strategy_version_no": snapshot.strategy_version_no,
        "entry_price": snapshot.entry_price,
        "stop_price": snapshot.stop_price,
        "target_price": snapshot.target_price,
        "rr_ratio": snapshot.rr_ratio,
        "model_score": snapshot.model_score,
        "extra_numbers": ["2.0"],
    }
    assert explanation_invents_numbers(snapshot.explanation, facts) == []
    assert explanation_invents_numbers("Target is 99999.", facts) == ["99999"]


def test_ready_bar_enters_and_open_position_holds() -> None:
    bars = _bars()
    entered = run_decision_workflow(
        bars, symbol=FIXTURE_SYMBOL, timeframe=FIXTURE_TIMEFRAME, bar_index=35
    )
    assert entered.action == DecisionAction.ENTER
    assert entered.risk_approved is True
    assert entered.rr_ratio is not None
    rendered = format(entered.rr_ratio, "f")
    assert str(entered.rr_ratio) in entered.explanation or rendered in entered.explanation
    held = run_decision_workflow(
        bars,
        symbol=FIXTURE_SYMBOL,
        timeframe=FIXTURE_TIMEFRAME,
        bar_index=35,
        position_state="open",
    )
    assert held.action == DecisionAction.HOLD


def test_grounded_explanation_refuses_extra_prices() -> None:
    text = grounded_explanation(
        {
            "action": "WAIT",
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "strategy_code": "wyckoff-hdm",
            "strategy_version_no": 1,
            "setup_state": "wait",
            "hard_blockers": ["stale_market_data"],
            "risk_approved": False,
            "entry_price": None,
            "stop_price": None,
            "target_price": None,
            "rr_ratio": None,
            "features": {"bos_bullish": {"status": "false"}},
            "citations": [],
            "model_score": None,
            "model_band": None,
            "model_invoked": False,
            "confidence_band": "low",
            "extra_numbers": [],
        }
    )
    assert "stale_market_data" in text
    assert "999" not in text
