"""Telegram message templates.

Every number shown here is copied from stored engine output (SignalCandidate payload /
DecisionRecord). Templates never compute or estimate values. All text is HTML parse mode.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from html import escape
from typing import Any

FOOTER = (
    "<i>Decision support only — PAPER context. Numbers come from the deterministic "
    "strategy/risk engines; nothing in this message authorizes a trade.</i>"
)
UNLINKED_TEXT = (
    "This is a private copilot. Link your Telegram from the web app "
    "(Settings → Telegram) and send <code>/start CODE</code> here."
)
LINK_FAILED_TEXT = (
    "Link code is invalid, expired or already used. Generate a new one in the web app."
)
NOT_AVAILABLE = {
    "performance": "Performance analytics arrive with Phase 17 soak / analytics.",
}


def journal_list(items: list[dict[str, Any]]) -> str:
    if not items:
        return (
            "No PAPER journal entries yet. Accept an ENTER setup via "
            "<code>POST /v1/paper/trades</code> and let it close."
        )
    lines = ["<b>PAPER journal</b> (cohort=paper — never mixed with backtest)"]
    for item in items:
        r = item.get("realized_r")
        r_text = "n/a" if r is None else f"{r}R"
        lines.append(
            f"• {escape(str(item.get('instrument_symbol')))} {escape(str(item.get('timeframe')))} "
            f"{escape(str(item.get('direction')))} · {escape(str(item.get('outcome')))} · {r_text}"
        )
    lines.extend(["", FOOTER])
    return "\n".join(lines)


def _num(value: Any) -> str:
    """Render exactly what is stored. DecisionRecord prices are Numeric(20,8), so display is
    capped at 8 decimals (half-even) to match the persisted value, never widened."""
    if value is None or value == "":
        return "n/a"
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return escape(str(value))
    exponent = number.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -8:
        number = number.quantize(Decimal("1e-8"), rounding=ROUND_HALF_EVEN)
    return f"{number.normalize():f}"


def _ts(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M UTC")
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M UTC")
        except ValueError:
            return escape(value)
    return "n/a"


def alert_keyboard(candidate_id: uuid.UUID | str) -> dict[str, Any]:
    cid = str(candidate_id)
    return {
        "inline_keyboard": [
            [
                {"text": "View", "callback_data": f"view:{cid}"},
                {"text": "Why?", "callback_data": f"why:{cid}"},
            ],
            [
                {"text": "Dismiss", "callback_data": f"dismiss:{cid}"},
                {"text": "Record decision", "callback_data": f"record:{cid}"},
            ],
        ]
    }


def record_decision_keyboard(candidate_id: uuid.UUID | str) -> dict[str, Any]:
    cid = str(candidate_id)
    return {
        "inline_keyboard": [
            [
                {"text": "I took it", "callback_data": f"record:{cid}:taken"},
                {"text": "I skipped it", "callback_data": f"record:{cid}:skipped"},
            ]
        ]
    }


def alert_message(candidate: dict[str, Any], record: dict[str, Any] | None) -> str:
    payload = dict(candidate.get("payload") or {})
    blockers = list(payload.get("hard_blockers") or (record or {}).get("hard_blockers") or [])
    risk = (record or {}).get("risk_approved")
    risk_text = "approved" if risk else ("vetoed" if risk is False else "n/a")
    lines = [
        f"🔔 <b>SETUP ALERT</b> — <b>{escape(str(candidate['instrument_symbol']))}</b> · "
        f"{escape(str(candidate['timeframe']))}",
        f"Strategy: {escape(str(candidate.get('strategy_code')))} "
        f"v{escape(str(candidate.get('strategy_version_no')))}",
        f"Action: <b>{escape(str(candidate.get('action')))}</b> "
        f"({escape(str(payload.get('direction') or 'n/a'))}) · "
        f"Setup: {escape(str(payload.get('setup_state') or 'n/a'))} · "
        f"Confidence: {escape(str(payload.get('confidence_band') or 'n/a'))}",
        f"Entry: {_num(payload.get('entry_price'))} · Stop: {_num(payload.get('stop_price'))} · "
        f"Target: {_num(payload.get('target_price'))} · R:R {_num(payload.get('rr_ratio'))}",
        f"Candle: {_ts(candidate.get('candle_open_time'))}",
        f"Risk gate: {risk_text}",
        "Blockers: " + (escape(", ".join(str(b) for b in blockers)) if blockers else "none"),
        "",
        FOOTER,
    ]
    return "\n".join(lines)


def why_message(record: dict[str, Any] | None) -> str:
    if record is None:
        return "No stored decision record for this alert."
    blockers = list(record.get("hard_blockers") or [])
    workflow = list(record.get("workflow") or [])
    steps = []
    for step in workflow[:9]:
        if isinstance(step, dict):
            steps.append(
                f"• {escape(str(step.get('agent') or step.get('step') or '?'))}: "
                f"{escape(str(step.get('status') or step.get('outcome') or ''))}"
            )
    lines = [
        "<b>Why this alert</b>",
        escape(str(record.get("explanation") or "")),
        "",
        f"Explanation source: {escape(str(record.get('explanation_source') or 'n/a'))}",
        "Blockers: " + (escape(", ".join(str(b) for b in blockers)) if blockers else "none"),
    ]
    if steps:
        lines.append("")
        lines.append("<b>Workflow</b>")
        lines.extend(steps)
    lines.extend(["", FOOTER])
    return "\n".join(lines)


def setups_list(items: list[dict[str, Any]]) -> str:
    if not items:
        return (
            "No setup candidates yet. The scanner only publishes on confirmed "
            "closed-candle setups."
        )
    lines = ["<b>Recent setups</b>"]
    for item in items:
        payload = dict(item.get("payload") or {})
        band = escape(str(payload.get("confidence_band") or "n/a"))
        lines.append(
            f"• <b>{escape(str(item['instrument_symbol']))}</b> {escape(str(item['timeframe']))} · "
            f"{escape(str(item.get('action')))} · {band}"
            f" · {escape(str(item.get('publish_state')))} · seen {item.get('seen_count', 1)}× · "
            f"{_ts(item.get('candle_open_time'))}"
        )
    lines.extend(["", FOOTER])
    return "\n".join(lines)


def markets_list(snapshots: list[dict[str, Any]]) -> str:
    if not snapshots:
        return "No market data synced yet."
    lines = ["<b>Markets</b>"]
    for snap in snapshots:
        flags = ", ".join(str(f) for f in snap.get("quality_flags") or []) or "ok"
        lines.append(
            f"• {escape(str(snap['instrument_symbol']))} {escape(str(snap['timeframe']))} · "
            f"last {_ts(snap.get('last_open_time'))} · "
            f"{'fresh' if snap.get('fresh') else 'STALE'} · "
            f"{'actionable' if snap.get('actionable') else 'not actionable'} · {escape(flags)}"
        )
    return "\n".join(lines)


def strategies_list(items: list[dict[str, Any]]) -> str:
    if not items:
        return "No strategies registered."
    lines = ["<b>Strategies</b>"]
    for item in items:
        published = item.get("published_version_no")
        lines.append(
            f"• <b>{escape(str(item['code']))}</b> — {escape(str(item.get('name') or ''))} · "
            f"{escape(str(item.get('status') or ''))} · "
            + (f"published v{published}" if published else "no published version")
        )
    return "\n".join(lines)


def settings_view(switches: dict[str, bool], *, can_edit: bool) -> str:
    lines = ["<b>Settings</b>"]
    for key, value in switches.items():
        lines.append(f"• {escape(key)}: {'ON' if value else 'OFF'}")
    if can_edit:
        lines.append("")
        lines.append("Change: <code>/settings scanner on|off</code>, "
                     "<code>/settings notifications on|off</code>")
    return "\n".join(lines)


def help_text(*, linked: bool) -> str:
    if not linked:
        return UNLINKED_TEXT
    return "\n".join(
        [
            "<b>Commands</b>",
            "/setups — recent setup candidates",
            "/markets — data freshness per market",
            "/strategies — registered strategies",
            "/settings — kill switches",
            "/journal — PAPER closed-trade journal",
            "/performance — arrives with Phase 17 analytics",
            "",
            "Send free text to ask the knowledge base (answers cite approved documents).",
            "Send a chart screenshot (optionally caption <code>SYMBOL TIMEFRAME</code>) for a "
            "read-back check. Vision never authorizes a trade.",
        ]
    )


def link_success(display_name: str | None) -> str:
    who = escape(display_name) if display_name else "your account"
    return f"Linked to {who}. Send /help to see what this bot can do."


def ask_answer(result: dict[str, Any]) -> str:
    citations = list(result.get("citations") or [])
    lines = [escape(str(result.get("answer") or ""))]
    if not result.get("sufficient_evidence", True):
        lines.append("")
        lines.append("<i>Evidence was insufficient; treat this answer as incomplete.</i>")
    lines.append("")
    lines.append(f"Confidence: {escape(str(result.get('confidence') or 'n/a'))}")
    if citations:
        lines.append("Sources:")
        for cite in citations[:5]:
            title = cite.get("title") or str(cite.get("document_id") or "document")
            page = cite.get("page")
            lines.append(f"• {escape(str(title))}" + (f", p.{page}" if page else ""))
    conflicts = list(result.get("conflicts") or [])
    if conflicts:
        lines.append("Conflicts noted: " + escape("; ".join(str(c) for c in conflicts[:3])))
    return "\n".join(lines)


def vision_result(job: dict[str, Any]) -> str:
    extraction = dict(job.get("extraction") or {})
    verification = dict(job.get("verification") or {})
    lines = [
        "<b>Screenshot check</b>",
        f"Status: {escape(str(job.get('status')))}",
        f"Read: {escape(str(extraction.get('symbol') or 'unclear'))} "
        f"{escape(str(extraction.get('timeframe') or ''))}".rstrip(),
        f"Matches catalog/market: {'yes' if verification.get('consistent') else 'no / unclear'}",
    ]
    blocker = verification.get("blocker")
    if blocker:
        lines.append(f"Blocker: {escape(str(blocker))}")
    if verification.get("needs_clarification"):
        lines.append(
            "Please confirm the symbol and timeframe in the web app (screenshot → correct)."
        )
    lines.extend(["", "<i>Vision never authorizes a trade.</i>"])
    return "\n".join(lines)
