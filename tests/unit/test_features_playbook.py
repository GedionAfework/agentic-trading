from private_trading_backtest.fixtures import (
    FIXTURE_BOS_INDEX,
    FIXTURE_RETEST_INDEX,
    frozen_bos_long_fixture,
)
from private_trading_features.engine import compute_feature
from private_trading_features.types import TriState


def test_ema50_known_after_pad() -> None:
    bars = frozen_bos_long_fixture()
    ema = compute_feature("ema_50", bars, FIXTURE_RETEST_INDEX)
    assert ema.status == TriState.TRUE
    assert ema.value is not None
    bias = compute_feature("ema_htf_bias", bars, FIXTURE_RETEST_INDEX)
    assert bias.status == TriState.TRUE
    assert bias.value == "long"


def test_impulse_bos_is_not_the_entry() -> None:
    bars = frozen_bos_long_fixture()
    bos = compute_feature("bos_bullish", bars, FIXTURE_BOS_INDEX)
    retest = compute_feature("retest_long", bars, FIXTURE_BOS_INDEX)
    assert bos.status == TriState.TRUE
    assert bos.value is True
    assert retest.value is not True


def test_retest_fires_on_low_volume_return_to_broken_level() -> None:
    bars = frozen_bos_long_fixture()
    retest = compute_feature("retest_long", bars, FIXTURE_RETEST_INDEX)
    assert retest.status == TriState.TRUE
    assert retest.value is True
