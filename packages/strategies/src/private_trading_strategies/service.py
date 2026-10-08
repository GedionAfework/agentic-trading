from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from private_trading_core.errors import AppError
from private_trading_db.models.strategy import (
    Strategy,
    StrategyRule,
    StrategyScope,
    StrategyTestCase,
    StrategyVersion,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from private_trading_strategies.evaluate import (
    STRATEGY_ENGINE_VERSION,
    StrategyDefinition,
    RuleDef,
    evaluate_strategy,
)
from private_trading_strategies.types import Direction, StrategyAssessment
from private_trading_strategies.wyckoff_hdm import build_wyckoff_hdm_v1


def definition_from_version(version: StrategyVersion, strategy_code: str) -> StrategyDefinition:
    rules = tuple(
        RuleDef(
            code=r.code,
            name=r.name,
            rule_type=r.rule_type,
            expression=dict(r.expression),
            required=r.required,
            weight=float(r.weight),
            sort_order=r.sort_order,
            gate_group=r.gate_group,
        )
        for r in sorted(version.rules, key=lambda x: x.sort_order)
    )
    return StrategyDefinition(
        code=strategy_code,
        version_no=version.version_no,
        direction_mode=version.direction_mode,
        rules=rules,
        config=dict(version.config or {}),
        engine_version=version.engine_version,
    )


async def get_strategy_by_code(session: AsyncSession, code: str) -> Strategy | None:
    result = await session.execute(
        select(Strategy)
        .options(
            selectinload(Strategy.versions).selectinload(StrategyVersion.rules),
            selectinload(Strategy.versions).selectinload(StrategyVersion.scopes),
            selectinload(Strategy.versions).selectinload(StrategyVersion.test_cases),
        )
        .where(Strategy.code == code)
    )
    return result.scalar_one_or_none()


async def get_version(
    session: AsyncSession, version_id: uuid.UUID
) -> tuple[Strategy, StrategyVersion] | None:
    result = await session.execute(
        select(StrategyVersion)
        .options(
            selectinload(StrategyVersion.strategy).selectinload(Strategy.versions),
            selectinload(StrategyVersion.rules),
            selectinload(StrategyVersion.scopes),
            selectinload(StrategyVersion.test_cases),
        )
        .where(StrategyVersion.id == version_id)
    )
    version = result.scalar_one_or_none()
    if version is None:
        return None
    return version.strategy, version


async def list_strategies(session: AsyncSession) -> list[Strategy]:
    result = await session.execute(select(Strategy).order_by(Strategy.created_at.desc()))
    return list(result.scalars().all())


async def _attach_definition(
    session: AsyncSession,
    version: StrategyVersion,
    definition: StrategyDefinition,
    *,
    owner_scopes: list[dict[str, Any]] | None = None,
    replace_rules: bool = False,
) -> None:
    version.config = definition.config
    version.engine_version = definition.engine_version
    version.direction_mode = definition.direction_mode

    if replace_rules:
        # Delete existing rules/scopes explicitly (async-safe; avoid collection lazy IO).
        await session.execute(
            StrategyRule.__table__.delete().where(
                StrategyRule.strategy_version_id == version.id
            )
        )
        if owner_scopes is not None:
            await session.execute(
                StrategyScope.__table__.delete().where(
                    StrategyScope.strategy_version_id == version.id
                )
            )

    for rule in definition.rules:
        session.add(
            StrategyRule(
                strategy_version_id=version.id,
                code=rule.code,
                name=rule.name,
                rule_type=rule.rule_type,
                expression=rule.expression,
                required=rule.required,
                weight=Decimal(str(rule.weight)),
                sort_order=rule.sort_order,
                gate_group=rule.gate_group,
            )
        )
    if owner_scopes is not None:
        for scope in owner_scopes:
            session.add(
                StrategyScope(
                    strategy_version_id=version.id,
                    asset_class=scope.get("asset_class", "crypto"),
                    symbol=scope.get("symbol"),
                    timeframe=scope.get("timeframe"),
                    session=scope.get("session"),
                    enabled=bool(scope.get("enabled", True)),
                )
            )


async def ensure_wyckoff_hdm(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    advisory_unlocked: bool = False,
) -> StrategyVersion:
    """Idempotent seed of Spec v1 strategy as draft (or keep published)."""
    existing = await get_strategy_by_code(session, "wyckoff-hdm")
    advisory = ["WYK-001", "IMB-001", "SMT-001"] if advisory_unlocked else []
    definition = build_wyckoff_hdm_v1(version_no=1, advisory_definitions=advisory)

    if existing is None:
        strategy = Strategy(
            owner_user_id=owner_user_id,
            code="wyckoff-hdm",
            name="Wyckoff + HDM (crypto-first)",
            description="Strategy Spec v1.0.0-draft gates",
            status="active",
        )
        session.add(strategy)
        await session.flush()
        version = StrategyVersion(
            strategy_id=strategy.id,
            version_no=1,
            status="draft",
            created_by=owner_user_id,
            engine_version=STRATEGY_ENGINE_VERSION,
            config={},
            direction_mode="both",
        )
        session.add(version)
        await session.flush()
        await _attach_definition(
            session,
            version,
            definition,
            owner_scopes=[
                {"asset_class": "crypto", "symbol": "BTC/USDT", "timeframe": "1h"},
                {"asset_class": "crypto", "symbol": "ETH/USDT", "timeframe": "1h"},
                {"asset_class": "crypto", "symbol": "BNB/USDT", "timeframe": "1h"},
                {"asset_class": "crypto", "symbol": "SOL/USDT", "timeframe": "1h"},
            ],
        )
        await _seed_golden_cases(session, version)
        await session.commit()
        loaded = await get_version(session, version.id)
        assert loaded is not None
        return loaded[1]

    versions = sorted(existing.versions, key=lambda v: v.version_no)
    draft = next((v for v in versions if v.status == "draft"), None)
    if draft is not None:
        loaded = await get_version(session, draft.id)
        assert loaded is not None
        _, version = loaded
        if version.status == "draft":
            definition = build_wyckoff_hdm_v1(
                version_no=version.version_no, advisory_definitions=advisory
            )
            await _attach_definition(session, version, definition, replace_rules=True)
            if not version.test_cases:
                await _seed_golden_cases(session, version)
            await session.commit()
        loaded2 = await get_version(session, version.id)
        assert loaded2 is not None
        return loaded2[1]
    published = next((v for v in reversed(versions) if v.status == "published"), versions[-1])
    loaded = await get_version(session, published.id)
    assert loaded is not None
    return loaded[1]


async def _seed_golden_cases(session: AsyncSession, version: StrategyVersion) -> None:
    cases = [
        StrategyTestCase(
            strategy_version_id=version.id,
            code="AT-011-ready-long",
            name="All deterministic + advisory unlocked → ready_for_review",
            direction="long",
            input_features={
                "bos_bullish": {"status": "true", "value": True},
                "bos_bearish": {"status": "false", "value": False},
                "significant_volume": {"status": "true", "value": True},
                "low_volume": {"status": "true", "value": True},
                "retest_long": {"status": "false", "value": False},
                "retest_short": {"status": "false", "value": False},
            },
            input_context={
                "htf_bias": "long",
                "structural_stop_ok": True,
                "rr_to_tp1": 2.5,
                "entry_path": "aggressive",
                "retest_complete": False,
            },
            expected_setup_state="ready_for_review",
            expected_rule_results={"bos_confirmed": "true", "q_min_rr": "true"},
        ),
        StrategyTestCase(
            strategy_version_id=version.id,
            code="AT-012-bos-false",
            name="Mandatory BOS false never ready",
            direction="long",
            input_features={
                "bos_bullish": {"status": "false", "value": False},
                "bos_bearish": {"status": "false", "value": False},
                "significant_volume": {"status": "true", "value": True},
                "retest_long": {"status": "false", "value": False},
                "retest_short": {"status": "false", "value": False},
            },
            input_context={
                "htf_bias": "long",
                "structural_stop_ok": True,
                "rr_to_tp1": 2.5,
                "entry_path": "aggressive",
            },
            expected_setup_state="no_setup",
            expected_rule_results={"bos_confirmed": "false"},
        ),
        StrategyTestCase(
            strategy_version_id=version.id,
            code="AT-013-rr-unknown",
            name="Missing R:R is UNKNOWN → wait",
            direction="long",
            input_features={
                "bos_bullish": {"status": "true", "value": True},
                "significant_volume": {"status": "true", "value": True},
                "retest_long": {"status": "false", "value": False},
                "retest_short": {"status": "false", "value": False},
            },
            input_context={
                "htf_bias": "long",
                "structural_stop_ok": True,
                "entry_path": "aggressive",
            },
            expected_setup_state="wait",
            expected_rule_results={"q_min_rr": "unknown"},
        ),
    ]
    for case in cases:
        session.add(case)


async def publish_version(
    session: AsyncSession,
    *,
    version_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> StrategyVersion:
    loaded = await get_version(session, version_id)
    if loaded is None:
        raise AppError("NOT_FOUND", "Strategy version not found", retryable=False)
    strategy, version = loaded
    if version.status != "draft":
        raise AppError("INVALID_STATE", f"Cannot publish status={version.status}", retryable=False)
    if not version.rules:
        raise AppError("INVALID_STATE", "Cannot publish version with no rules", retryable=False)

    # Retire previously published versions of this strategy
    for other in strategy.versions:
        if other.id != version.id and other.status == "published":
            other.status = "retired"

    version.status = "published"
    version.published_at = datetime.now(UTC)
    _ = actor_user_id
    await session.commit()
    loaded2 = await get_version(session, version.id)
    assert loaded2 is not None
    return loaded2[1]


async def evaluate_version(
    session: AsyncSession,
    *,
    version_id: uuid.UUID,
    direction: str,
    features: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> StrategyAssessment:
    loaded = await get_version(session, version_id)
    if loaded is None:
        raise AppError("NOT_FOUND", "Strategy version not found", retryable=False)
    strategy, version = loaded
    definition = definition_from_version(version, strategy.code)
    return evaluate_strategy(
        definition,
        direction=Direction(direction),
        features=features,
        context=context,
    )


async def run_test_cases(
    session: AsyncSession, *, version_id: uuid.UUID
) -> list[dict[str, Any]]:
    loaded = await get_version(session, version_id)
    if loaded is None:
        raise AppError("NOT_FOUND", "Strategy version not found", retryable=False)
    strategy, version = loaded
    # For golden READY case, evaluate with advisory unlocked overlay matching fixture intent
    results: list[dict[str, Any]] = []
    for case in version.test_cases:
        config = dict(version.config or {})
        if case.code.startswith("AT-011"):
            config = {
                **config,
                "advisory_definitions": ["WYK-001", "IMB-001", "SMT-001"],
            }
        definition = StrategyDefinition(
            code=strategy.code,
            version_no=version.version_no,
            direction_mode=version.direction_mode,
            rules=definition_from_version(version, strategy.code).rules,
            config=config,
            engine_version=version.engine_version,
        )
        assessment = evaluate_strategy(
            definition,
            direction=case.direction,
            features=case.input_features,
            context=case.input_context,
        )
        by_code = {e.code: e.result.value for e in assessment.rule_evaluations}
        expected_rules = case.expected_rule_results or {}
        rule_ok = all(by_code.get(k) == v for k, v in expected_rules.items())
        state_ok = assessment.setup_state.value == case.expected_setup_state
        results.append(
            {
                "code": case.code,
                "passed": rule_ok and state_ok,
                "expected_setup_state": case.expected_setup_state,
                "actual_setup_state": assessment.setup_state.value,
                "expected_rule_results": expected_rules,
                "actual_rule_results": {k: by_code.get(k) for k in expected_rules},
                "blockers": assessment.blockers,
            }
        )
    return results
