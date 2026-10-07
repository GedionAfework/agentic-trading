import pytest
from private_trading_agents.vision import (
    evaluate_gate_d,
    parse_vlm_payload,
    validate_image,
    verify_read,
)
from private_trading_agents.workflow import DecisionAction, run_decision_workflow
from private_trading_backtest.fixtures import (
    FIXTURE_SYMBOL,
    FIXTURE_TIMEFRAME,
    frozen_bos_long_fixture,
)
from private_trading_core.errors import AppError


def test_rejects_non_image() -> None:
    with pytest.raises(AppError) as exc:
        validate_image(b"not an image", "text/plain")
    assert exc.value.code == "INVALID_UPLOAD"


def test_rejects_oversized_png() -> None:
    blob = b"\x89PNG\r\n\x1a\n" + b"\x00" * (8 * 1024 * 1024)
    with pytest.raises(AppError):
        validate_image(blob, "image/png")


def test_vlm_prices_are_dropped_and_low_confidence_clarifies() -> None:
    read = parse_vlm_payload(
        {
            "readable": True,
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "symbol_confidence": 0.2,
            "timeframe_confidence": 0.2,
            "last_price": 99999,
        }
    )
    assert read.to_dict()["prices"] is None
    assert read.needs_clarification is True
    assert read.symbol is None
    verdict = verify_read(read, market_symbol="BTCUSDT", market_timeframe="1h")
    assert verdict.needs_clarification is True
    assert verdict.authorizes_trade is False


def test_consistent_read_still_cannot_authorize() -> None:
    read = parse_vlm_payload(
        {
            "readable": True,
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "symbol_confidence": 0.95,
            "timeframe_confidence": 0.95,
            "close": 100,
        }
    )
    verdict = verify_read(read, market_symbol="BTCUSDT", market_timeframe="1h")
    assert verdict.consistent is True
    assert verdict.authorizes_trade is False
    assert verdict.blocker is None


def test_gate_d_passes_without_fabricated_prices() -> None:
    report = evaluate_gate_d()
    assert report["case_count"] >= 30
    assert report["fabricated_price_count"] == 0
    assert report["authorizes_trade_count"] == 0
    assert report["clarification_rate"] == 1.0
    assert report["passed"] is True
    assert report["mode"] == "supporting_evidence"


def test_unclear_vision_downgrades_enter_to_wait() -> None:
    bars = frozen_bos_long_fixture()
    clear = run_decision_workflow(
        bars, symbol=FIXTURE_SYMBOL, timeframe=FIXTURE_TIMEFRAME, bar_index=35
    )
    assert clear.action == DecisionAction.ENTER
    read = parse_vlm_payload({"readable": False, "last_price": 123})
    verdict = verify_read(read, market_symbol="BTCUSDT", market_timeframe="1h")
    blocked = run_decision_workflow(
        bars,
        symbol=FIXTURE_SYMBOL,
        timeframe=FIXTURE_TIMEFRAME,
        bar_index=35,
        vision=verdict,
    )
    assert blocked.action == DecisionAction.WAIT
    assert "vision_needs_clarification" in blocked.hard_blockers
    assert "vision_needs_clarification" in blocked.explanation
