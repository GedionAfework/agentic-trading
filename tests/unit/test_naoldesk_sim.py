"""Locks the frozen NaolDesk simulator. Golden values were produced by the
original research script (parity-checked trade-for-trade before the move)."""

import math
import random
from datetime import UTC, datetime, timedelta

import pytest
from private_trading_backtest import naoldesk as nd


def _synth(seed: int):
    rnd = random.Random(seed)
    t0 = datetime(2021, 9, 1, tzinfo=UTC)
    n = 24 * 400
    t, o, h, lo_, c, v = [], [], [], [], [], []
    px = 100.0
    for i in range(n):
        drift = 0.0004 * math.sin(i / 700)
        op = px
        px = max(1.0, px * (1 + drift + rnd.gauss(0, 0.008)))
        hi = max(op, px) * (1 + abs(rnd.gauss(0, 0.003)))
        low = min(op, px) * (1 - abs(rnd.gauss(0, 0.003)))
        vol = rnd.lognormvariate(0, 0.6) * (3 if rnd.random() < 0.05 else 1)
        t.append(t0 + timedelta(hours=i))
        o.append(op)
        h.append(hi)
        lo_.append(low)
        c.append(px)
        v.append(vol)

    def agg(hours: int) -> nd.Bars:
        cols: list[list] = [[], [], [], [], [], []]
        for s in range(0, n - hours + 1, hours):
            for col, val in zip(
                cols,
                (t[s], o[s], max(h[s:s + hours]), min(lo_[s:s + hours]),
                 c[s + hours - 1], sum(v[s:s + hours])),
                strict=True,
            ):
                col.append(val)
        return nd.Bars(*cols)

    return nd.Bars(t, o, h, lo_, c, v), agg(4), agg(24)


@pytest.fixture(scope="module")
def prepared() -> nd.Prepared:
    one, four, day = _synth(1)
    return nd.prepare(one, four, day)


@pytest.mark.parametrize(
    ("setup", "exit_tf", "count", "sum_r"),
    [
        ("A", "1h", 13, 8.552456),
        ("A", "4h", 12, 8.435866),
        ("B", "1h", 7, -1.657272),
        ("B", "4h", 7, 0.588305),
    ],
)
def test_golden_results_unchanged(prepared, setup, exit_tf, count, sum_r) -> None:
    trades = nd.simulate("X", prepared, setup, exit_tf=exit_tf)
    assert len(trades) == count
    assert sum(t.r for t in trades) == pytest.approx(sum_r, abs=1e-6)


def test_frozen_constants() -> None:
    assert (nd.PIVOT, nd.VOL_MA, nd.BOS_VOL_MULT, nd.STOP_ATR_BUFFER) == (3, 20, 2.0, 0.5)
    assert (nd.TP1_R, nd.TP1_FRACTION, nd.MAX_BARS, nd.FEE) == (1.0, 1 / 3, 720, 0.001)
    assert (nd.CLIMAX_VOL_MULT, nd.CLIMAX_RANGE_ATR) == (2.0, 0.6)


def test_forward_start_only_scores_new_candles(prepared) -> None:
    cutoff = prepared.b.t[len(prepared.b.t) // 2]
    trades = nd.simulate("X", prepared, "A", exit_tf="4h", score_start=cutoff)
    assert all(t.entry_time >= cutoff for t in trades)


def test_open_position_is_reported_not_force_closed(prepared) -> None:
    full = nd.simulate("X", prepared, "A", exit_tf="4h")
    last_entry = full[-1].entry_time
    # Truncate history right after the last entry so that trade is still open.
    k = prepared.b.t.index(last_entry) + 1
    one = nd.Bars(*(getattr(prepared.b, f)[:k] for f in ("t", "o", "h", "l", "c", "v")))
    cut = nd.prepare(one, prepared.b4, nd.Bars([], [], [], [], [], []))
    opened: list = []
    trades = nd.simulate("X", cut, "A", exit_tf="4h", close_at_end=False, open_out=opened)
    assert not any(t.reason == "end_of_data" for t in trades)
    assert opened and opened[0]["entry_time"] == last_entry.isoformat()


def test_pivot_is_not_known_early() -> None:
    t0 = datetime(2022, 1, 3, tzinfo=UTC)
    rows = [(100.0, 101.0, 99.0, 100.0, 10.0)] * 20
    rows[10] = (100.0, 120.0, 99.0, 100.0, 10.0)
    b = nd.Bars([t0 + timedelta(hours=i) for i in range(20)], *map(list, zip(*rows, strict=True)))
    p = nd.prepare(b, nd.Bars([], [], [], [], [], []), nd.Bars([], [], [], [], [], []))
    assert p.swing_high[12] is None
    assert p.swing_high[13] == (120.0, 10)
