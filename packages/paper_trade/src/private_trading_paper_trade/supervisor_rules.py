"""Paper supervisor rules — pure, deterministic, no I/O.

The supervisor may only make the system safer: alert, and pause new paper
auto-opens. It never resumes, opens, closes, or resizes trades. Resuming is an
owner action (audited kill switch). Thresholds come from PAPER_SOAK_ROADMAP
kill rules; they are not tuned here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from private_trading_paper_trade.soak_metrics import ClosedSoakTrade, max_drawdown_r

Severity = Literal["info", "warn", "critical"]

# Kill rules (PAPER_SOAK_ROADMAP Steps 1–2).
DRAWDOWN_PAUSE_R = 20.0  # Step 2 max drawdown gate
DRAWDOWN_WARN_R = 15.0
MEAN_R_PAUSE_MIN_TRADES = 20  # Step 1: pause if mean R <= 0 after 20 trades
FILL_GAP_BPS = 2.0  # Step 2: avg extra cost beyond the model
FILL_GAP_PAUSE_MIN_TRADES = 20
FILL_GAP_WARN_MIN_TRADES = 5
SCANNER_FAILURE_WARN = 3  # failed scan runs in the lookback window


@dataclass(slots=True, frozen=True)
class Finding:
    code: str
    severity: Severity
    subject: str
    message: str
    pauses_auto_open: bool = False

    @property
    def key(self) -> str:
        return f"{self.code}:{self.subject}"

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity,
            "subject": self.subject,
            "message": self.message,
            "pauses_auto_open": self.pauses_auto_open,
        }


@dataclass(slots=True)
class ModelSample:
    code: str
    trades: list[ClosedSoakTrade]  # ordered by close time

    @property
    def n(self) -> int:
        return len(self.trades)

    @property
    def mean_r(self) -> float:
        return sum(t.realized_r for t in self.trades) / self.n if self.n else 0.0

    @property
    def drawdown_r(self) -> float:
        return max_drawdown_r([t.realized_r for t in self.trades])

    @property
    def avg_extra_cost_bps(self) -> float | None:
        extras = [
            t.extra_cost_bps_vs_research
            for t in self.trades
            if t.extra_cost_bps_vs_research is not None
        ]
        return sum(extras) / len(extras) if extras else None


@dataclass(slots=True)
class SupervisorSnapshot:
    samples: list[ModelSample] = field(default_factory=list)
    stale_symbols: list[str] = field(default_factory=list)
    integrity_defects: list[str] = field(default_factory=list)
    failed_scan_runs: int = 0
    scan_lookback_hours: int = 6
    daily_loss_stop_hit: bool = False
    auto_open_enabled: bool = True


def evaluate_supervisor(snap: SupervisorSnapshot) -> list[Finding]:
    findings: list[Finding] = []
    for sample in snap.samples:
        if sample.n == 0:
            continue
        dd = sample.drawdown_r
        if dd > DRAWDOWN_PAUSE_R:
            findings.append(
                Finding(
                    "drawdown_breach",
                    "critical",
                    sample.code,
                    f"Paper drawdown {dd:.2f}R exceeds the {DRAWDOWN_PAUSE_R:.0f}R kill rule "
                    f"over {sample.n} trades.",
                    pauses_auto_open=True,
                )
            )
        elif dd >= DRAWDOWN_WARN_R:
            findings.append(
                Finding(
                    "drawdown_warning",
                    "warn",
                    sample.code,
                    f"Paper drawdown {dd:.2f}R is approaching the {DRAWDOWN_PAUSE_R:.0f}R "
                    "kill rule.",
                )
            )
        if sample.n >= MEAN_R_PAUSE_MIN_TRADES and sample.mean_r <= 0:
            findings.append(
                Finding(
                    "negative_expectancy",
                    "critical",
                    sample.code,
                    f"Mean {sample.mean_r:+.3f}R after {sample.n} paper trades "
                    "(roadmap: pause and inspect if mean R <= 0).",
                    pauses_auto_open=True,
                )
            )
        gap = sample.avg_extra_cost_bps
        if gap is not None and gap >= FILL_GAP_BPS:
            if sample.n >= FILL_GAP_PAUSE_MIN_TRADES:
                findings.append(
                    Finding(
                        "fill_gap_breach",
                        "critical",
                        sample.code,
                        f"Fills average {gap:.2f} bps worse than the cost model over "
                        f"{sample.n} trades (limit {FILL_GAP_BPS:.0f} bps).",
                        pauses_auto_open=True,
                    )
                )
            elif sample.n >= FILL_GAP_WARN_MIN_TRADES:
                findings.append(
                    Finding(
                        "fill_gap_warning",
                        "warn",
                        sample.code,
                        f"Fills average {gap:.2f} bps worse than the cost model "
                        f"(only {sample.n} trades so far).",
                    )
                )
    if snap.integrity_defects:
        shown = ", ".join(snap.integrity_defects[:3])
        findings.append(
            Finding(
                "integrity_defects",
                "critical",
                "paper_account",
                f"{len(snap.integrity_defects)} paper state defect(s): {shown}.",
                pauses_auto_open=True,
            )
        )
    for symbol in snap.stale_symbols:
        findings.append(
            Finding(
                "stale_feed",
                "warn",
                symbol,
                f"No fresh closed 1h candle for {symbol}; scans skip it until data recovers.",
            )
        )
    if snap.failed_scan_runs >= SCANNER_FAILURE_WARN:
        findings.append(
            Finding(
                "scanner_failures",
                "warn",
                "scanner",
                f"{snap.failed_scan_runs} failed scan runs in the last "
                f"{snap.scan_lookback_hours}h.",
            )
        )
    if snap.daily_loss_stop_hit:
        findings.append(
            Finding(
                "daily_loss_stop",
                "info",
                "portfolio",
                "Daily loss stop hit; the portfolio gate refuses new opens until the next "
                "UTC day.",
            )
        )
    if not snap.auto_open_enabled:
        findings.append(
            Finding(
                "auto_open_paused",
                "info",
                "paper_account",
                "Paper auto-open is paused. Only the owner can resume it.",
            )
        )
    return findings


def alertable_keys(findings: list[Finding]) -> set[str]:
    return {f.key for f in findings if f.severity in ("warn", "critical")}


def should_pause(findings: list[Finding]) -> bool:
    return any(f.pauses_auto_open for f in findings)


def alert_text(
    new: list[Finding], *, paused_now: bool, cleared: list[str] | None = None
) -> str:
    """Telegram/plain text built only from computed findings."""
    lines = ["<b>Paper supervisor</b>"]
    for f in new:
        mark = "🛑" if f.severity == "critical" else "⚠️"
        lines.append(f"{mark} [{f.subject}] {f.message}")
    if paused_now:
        lines.append("")
        lines.append(
            "New paper auto-opens are <b>paused</b>. Open trades are still managed to exit. "
            "Resume with <code>/settings paper on</code> after you inspect."
        )
    if cleared:
        lines.append("✅ Cleared: " + ", ".join(cleared))
    lines.append("Paper only. Nothing here is a trade instruction.")
    return "\n".join(lines)
