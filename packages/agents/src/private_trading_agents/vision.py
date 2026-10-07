from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from private_trading_core.errors import AppError
from private_trading_market_data.contracts import SUPPORTED_TIMEFRAMES
from private_trading_market_data.providers.binance import DEFAULT_SYMBOLS

VISION_ENGINE_VERSION = "0.1.0"
MAX_IMAGE_BYTES = 8 * 1024 * 1024
RETENTION_DAYS = 30
CONFIDENCE_MIN = 0.75
KNOWN_SYMBOLS = {item.provider_symbol for item in DEFAULT_SYMBOLS}
KNOWN_TIMEFRAMES = set(SUPPORTED_TIMEFRAMES)

_PNG = b"\x89PNG\r\n\x1a\n"
_JPEG = b"\xff\xd8\xff"


@dataclass(slots=True, frozen=True)
class VisionRead:
    readable: bool
    symbol: str | None
    timeframe: str | None
    symbol_confidence: float
    timeframe_confidence: float
    needs_clarification: bool
    reason: str
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "readable": self.readable,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "symbol_confidence": self.symbol_confidence,
            "timeframe_confidence": self.timeframe_confidence,
            "needs_clarification": self.needs_clarification,
            "reason": self.reason,
            "source": self.source,
            "prices": None,
            "engine_version": VISION_ENGINE_VERSION,
        }


@dataclass(slots=True, frozen=True)
class VisionVerdict:
    status: str
    consistent: bool
    needs_clarification: bool
    authorizes_trade: bool
    blocker: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "consistent": self.consistent,
            "needs_clarification": self.needs_clarification,
            "authorizes_trade": False,
            "blocker": self.blocker,
        }


def validate_image(data: bytes, content_type: str | None) -> str:
    if not data:
        raise AppError("INVALID_UPLOAD", "Empty screenshot", retryable=False)
    if len(data) > MAX_IMAGE_BYTES:
        raise AppError("INVALID_UPLOAD", "Screenshot exceeds 8MB", retryable=False)
    if data.startswith(_PNG):
        detected = "image/png"
    elif data.startswith(_JPEG):
        detected = "image/jpeg"
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        detected = "image/webp"
    else:
        raise AppError("INVALID_UPLOAD", "Screenshot must be PNG, JPEG, or WEBP", retryable=False)
    declared = (content_type or "").split(";")[0].strip().lower()
    if declared and declared not in {detected, "application/octet-stream"}:
        raise AppError(
            "INVALID_UPLOAD",
            "Content type does not match the image bytes",
            retryable=False,
        )
    return detected


def _confidence(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0 or number > 1:
        return None
    return number


def parse_vlm_payload(payload: dict[str, Any] | None) -> VisionRead:
    """Structured VLM read. Price fields are dropped and never returned."""
    if not payload:
        return VisionRead(
            readable=False,
            symbol=None,
            timeframe=None,
            symbol_confidence=0.0,
            timeframe_confidence=0.0,
            needs_clarification=True,
            reason="no_vlm_read",
            source="fail_closed",
        )
    readable = bool(payload.get("readable"))
    symbol_confidence = _confidence(payload.get("symbol_confidence"))
    timeframe_confidence = _confidence(payload.get("timeframe_confidence"))
    if not readable or symbol_confidence is None or timeframe_confidence is None:
        return VisionRead(
            readable=False,
            symbol=None,
            timeframe=None,
            symbol_confidence=symbol_confidence or 0.0,
            timeframe_confidence=timeframe_confidence or 0.0,
            needs_clarification=True,
            reason="unreadable_or_bad_confidence",
            source="vlm",
        )
    symbol = payload.get("symbol")
    timeframe = payload.get("timeframe")
    symbol_text = str(symbol).upper() if isinstance(symbol, str) and symbol.strip() else None
    tf_text = str(timeframe).lower() if isinstance(timeframe, str) and timeframe.strip() else None
    low = symbol_confidence < CONFIDENCE_MIN or timeframe_confidence < CONFIDENCE_MIN
    return VisionRead(
        readable=True,
        symbol=None if low else symbol_text,
        timeframe=None if low else tf_text,
        symbol_confidence=symbol_confidence,
        timeframe_confidence=timeframe_confidence,
        needs_clarification=low or symbol_text is None or tf_text is None,
        reason="low_confidence" if low else "extracted",
        source="vlm",
    )


def verify_read(
    read: VisionRead,
    *,
    market_symbol: str | None,
    market_timeframe: str | None,
) -> VisionVerdict:
    if read.needs_clarification or not read.readable:
        return VisionVerdict(
            status="clarification_required",
            consistent=False,
            needs_clarification=True,
            authorizes_trade=False,
            blocker="vision_needs_clarification",
        )
    if read.symbol not in KNOWN_SYMBOLS or read.timeframe not in KNOWN_TIMEFRAMES:
        return VisionVerdict(
            status="not_in_catalog",
            consistent=False,
            needs_clarification=True,
            authorizes_trade=False,
            blocker="vision_not_in_catalog",
        )
    if market_symbol and read.symbol != market_symbol.upper():
        return VisionVerdict(
            status="symbol_mismatch",
            consistent=False,
            needs_clarification=True,
            authorizes_trade=False,
            blocker="vision_symbol_mismatch",
        )
    if market_timeframe and read.timeframe != market_timeframe.lower():
        return VisionVerdict(
            status="timeframe_mismatch",
            consistent=False,
            needs_clarification=True,
            authorizes_trade=False,
            blocker="vision_timeframe_mismatch",
        )
    return VisionVerdict(
        status="consistent",
        consistent=True,
        needs_clarification=False,
        authorizes_trade=False,
        blocker=None,
    )


def benchmark_cases() -> list[dict[str, Any]]:
    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"]
    timeframes = ["15m", "1h", "4h", "1d"]
    cases: list[dict[str, Any]] = []
    for index in range(16):
        symbol = symbols[index % 4]
        timeframe = timeframes[index % 4]
        cases.append(
            {
                "case_id": f"consistent-{index}",
                "kind": "consistent",
                "payload": {
                    "readable": True,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "symbol_confidence": 0.92,
                    "timeframe_confidence": 0.9,
                    "last_price": 99999 + index,
                },
                "market_symbol": symbol,
                "market_timeframe": timeframe,
            }
        )
    for index in range(6):
        cases.append(
            {
                "case_id": f"low-{index}",
                "kind": "low_confidence",
                "payload": {
                    "readable": True,
                    "symbol": "BTCUSDT",
                    "timeframe": "1h",
                    "symbol_confidence": 0.4,
                    "timeframe_confidence": 0.4,
                    "price": 42000,
                },
                "market_symbol": "BTCUSDT",
                "market_timeframe": "1h",
            }
        )
    for index in range(4):
        cases.append(
            {
                "case_id": f"unreadable-{index}",
                "kind": "unreadable",
                "payload": {"readable": False, "last_price": 11111, "symbol": "BTCUSDT"},
                "market_symbol": "BTCUSDT",
                "market_timeframe": "1h",
            }
        )
    mismatches = [
        ("ETHUSDT", "BTCUSDT", "1h", "1h"),
        ("BTCUSDT", "BTCUSDT", "1d", "1h"),
        ("DOGEUSDT", "BTCUSDT", "1h", "1h"),
        ("BTCUSDT", "BTCUSDT", "2h", "1h"),
    ]
    for index, (seen_symbol, market_symbol, seen_tf, market_tf) in enumerate(mismatches):
        cases.append(
            {
                "case_id": f"mismatch-{index}",
                "kind": "mismatch",
                "payload": {
                    "readable": True,
                    "symbol": seen_symbol,
                    "timeframe": seen_tf,
                    "symbol_confidence": 0.95,
                    "timeframe_confidence": 0.95,
                    "close": 100,
                },
                "market_symbol": market_symbol,
                "market_timeframe": market_tf,
            }
        )
    return cases


def evaluate_gate_d(cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = cases if cases is not None else benchmark_cases()
    fabricated = 0
    authorized = 0
    consistent_hits = 0
    consistent_total = 0
    clarification_hits = 0
    clarification_total = 0
    for case in rows:
        read = parse_vlm_payload(case["payload"])
        verdict = verify_read(
            read,
            market_symbol=case.get("market_symbol"),
            market_timeframe=case.get("market_timeframe"),
        )
        if read.to_dict()["prices"] is not None:
            fabricated += 1
        if verdict.authorizes_trade:
            authorized += 1
        if case["kind"] == "consistent":
            consistent_total += 1
            if verdict.consistent and not verdict.needs_clarification:
                consistent_hits += 1
        else:
            clarification_total += 1
            if verdict.needs_clarification and not verdict.consistent:
                clarification_hits += 1
    consistent_accuracy = consistent_hits / consistent_total if consistent_total else 0.0
    clarification_rate = clarification_hits / clarification_total if clarification_total else 0.0
    passed = (
        fabricated == 0
        and authorized == 0
        and consistent_accuracy >= 0.8
        and clarification_rate == 1.0
        and len(rows) >= 30
    )
    return {
        "gate": "D",
        "engine_version": VISION_ENGINE_VERSION,
        "case_count": len(rows),
        "fabricated_price_count": fabricated,
        "authorizes_trade_count": authorized,
        "consistent_accuracy": consistent_accuracy,
        "clarification_rate": clarification_rate,
        "passed": passed,
        "mode": "supporting_evidence" if passed else "advisory_only",
        "note": (
            "Vision never authorizes a trade. Gate D checks that reads stay "
            "non-numeric and that low confidence asks for clarification."
        ),
    }
