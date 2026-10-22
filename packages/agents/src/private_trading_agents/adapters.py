"""Adapters between domain dataclasses and Pydantic agent contracts."""

from __future__ import annotations

from private_trading_features.types import CandleBar

from private_trading_agents.contracts import CandleBarModel, FeatureFactModel


def candle_to_model(bar: CandleBar) -> CandleBarModel:
    return CandleBarModel(
        open_time=bar.open_time,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        volume=bar.volume,
        is_final=bar.is_final,
    )


def candles_to_models(bars: list[CandleBar]) -> list[CandleBarModel]:
    return [candle_to_model(bar) for bar in bars]


def models_to_candles(bars: list[CandleBarModel]) -> list[CandleBar]:
    return [
        CandleBar(
            open_time=bar.open_time,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
            is_final=bar.is_final,
        )
        for bar in bars
    ]


def feature_payload_to_models(payload: dict) -> dict[str, FeatureFactModel]:
    out: dict[str, FeatureFactModel] = {}
    for name, raw in payload.items():
        if isinstance(raw, FeatureFactModel):
            out[name] = raw
            continue
        if isinstance(raw, dict):
            out[name] = FeatureFactModel.model_validate(raw)
            continue
        status = getattr(raw, "status", None)
        status_value = status.value if hasattr(status, "value") else str(status)
        out[name] = FeatureFactModel(
            status=status_value,
            value=getattr(raw, "value", None),
            reason=getattr(raw, "reason", None),
        )
    return out


def feature_models_to_payload(
    features: dict[str, FeatureFactModel],
) -> dict[str, dict]:
    return {
        name: {
            "status": fact.status,
            "value": fact.value,
            "reason": fact.reason,
        }
        for name, fact in features.items()
    }
