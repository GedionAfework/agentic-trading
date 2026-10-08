from __future__ import annotations

from collections import defaultdict
from typing import Any

from private_trading_analytics.metrics import sample_status_for


def calibrate_bands(
    observations: list[dict[str, Any]],
    *,
    band_field: str = "confidence_band",
) -> dict[str, Any]:
    """Compute realized win-rate / mean R by band. Drift flags are informational only."""
    by_band: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for obs in observations:
        band = str(obs.get(band_field) or "unknown")
        by_band[band].append(obs)

    bands: dict[str, Any] = {}
    total = 0
    for band, items in sorted(by_band.items()):
        total += len(items)
        rs = [float(i["realized_r"]) for i in items if i.get("realized_r") is not None]
        wins = sum(1 for i in items if i.get("won") is True)
        n = len(items)
        status, warns = sample_status_for(n)
        bands[band] = {
            "sample_size": n,
            "sample_status": status,
            "win_count": wins,
            "win_rate": (wins / n) if n else None,
            "mean_r": (sum(rs) / len(rs)) if rs else None,
            "warnings": warns,
        }

    status, warnings = sample_status_for(total)
    drift_flags: list[str] = []

    # Ordering expectation: high should not have clearly worse mean_r than low when both ok.
    high = bands.get("high")
    low = bands.get("low")
    if (
        high
        and low
        and high["sample_status"] == "ok"
        and low["sample_status"] == "ok"
        and high.get("mean_r") is not None
        and low.get("mean_r") is not None
        and high["mean_r"] + 0.15 < low["mean_r"]
    ):
        drift_flags.append(
            "high_band_mean_r_below_low_band; "
            "review ranker calibration before promoting challengers."
        )

    medium = bands.get("medium")
    if (
        high
        and medium
        and high["sample_status"] != "insufficient_sample"
        and medium["sample_status"] != "insufficient_sample"
        and high.get("win_rate") is not None
        and medium.get("win_rate") is not None
        and high["win_rate"] + 0.05 < medium["win_rate"]
    ):
        drift_flags.append(
            "high_band_win_rate_below_medium; flag for human review — do not auto-retrain."
        )

    if drift_flags:
        warnings.append("drift_flags_present; retrain requires explicit evaluation and approval.")

    return {
        "band_field": band_field,
        "sample_size": total,
        "sample_status": status,
        "bands": bands,
        "drift_flags": drift_flags,
        "warnings": warnings,
    }
