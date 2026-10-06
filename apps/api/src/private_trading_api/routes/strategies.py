from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from private_trading_core.errors import NotFoundError
from private_trading_db.services.audit import record_audit
from private_trading_strategies.service import (
    ensure_wyckoff_hdm,
    evaluate_version,
    get_strategy_by_code,
    get_version,
    list_strategies,
    publish_version,
    run_test_cases,
)
from sqlalchemy.ext.asyncio import AsyncSession

from private_trading_api.deps import CurrentUser, get_correlation_id, get_current_user, get_db
from private_trading_api.schemas.strategies import (
    AssessmentOut,
    EnsureStrategyResponse,
    EvaluateRequest,
    RuleEvalOut,
    RuleOut,
    StrategyOut,
    StrategyVersionOut,
    TestCaseRunOut,
)

router = APIRouter(prefix="/strategies", tags=["strategies"])


def _strategy_out(s) -> StrategyOut:
    return StrategyOut(
        id=s.id,
        code=s.code,
        name=s.name,
        description=s.description,
        status=s.status,
        created_at=s.created_at,
    )


def _version_out(v) -> StrategyVersionOut:
    return StrategyVersionOut(
        id=v.id,
        strategy_id=v.strategy_id,
        version_no=v.version_no,
        status=v.status,
        direction_mode=v.direction_mode,
        engine_version=v.engine_version,
        published_at=v.published_at,
        config=dict(v.config or {}),
    )


@router.get("", response_model=list[StrategyOut])
async def get_strategies(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[StrategyOut]:
    user.require_roles("owner", "admin", "viewer")
    rows = await list_strategies(session)
    return [_strategy_out(s) for s in rows]


@router.post("/ensure-default", response_model=EnsureStrategyResponse)
async def post_ensure_default(
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> EnsureStrategyResponse:
    """Seed Spec v1 wyckoff-hdm draft (fail-closed unlocked definitions)."""
    user.require_roles("owner", "admin")
    version = await ensure_wyckoff_hdm(session, owner_user_id=user.id, advisory_unlocked=False)
    strategy = (await get_strategy_by_code(session, "wyckoff-hdm"))
    assert strategy is not None
    await record_audit(
        session,
        action="strategy.ensure_default",
        actor_type="user",
        actor_id=user.id,
        resource_type="strategy_version",
        resource_id=version.id,
        correlation_id=get_correlation_id(request),
    )
    await session.commit()
    return EnsureStrategyResponse(
        strategy=_strategy_out(strategy),
        version=_version_out(version),
        rules=[
            RuleOut(
                code=r.code,
                name=r.name,
                rule_type=r.rule_type,
                required=r.required,
                gate_group=r.gate_group,
                sort_order=r.sort_order,
                expression=dict(r.expression),
            )
            for r in sorted(version.rules, key=lambda x: x.sort_order)
        ],
    )


@router.get("/versions/{version_id}", response_model=StrategyVersionOut)
async def get_strategy_version(
    version_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> StrategyVersionOut:
    user.require_roles("owner", "admin", "viewer")
    loaded = await get_version(session, version_id)
    if loaded is None:
        raise NotFoundError("Strategy version not found")
    return _version_out(loaded[1])


@router.get("/versions/{version_id}/rules", response_model=list[RuleOut])
async def get_version_rules(
    version_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[RuleOut]:
    user.require_roles("owner", "admin", "viewer")
    loaded = await get_version(session, version_id)
    if loaded is None:
        raise NotFoundError("Strategy version not found")
    version = loaded[1]
    return [
        RuleOut(
            code=r.code,
            name=r.name,
            rule_type=r.rule_type,
            required=r.required,
            gate_group=r.gate_group,
            sort_order=r.sort_order,
            expression=dict(r.expression),
        )
        for r in sorted(version.rules, key=lambda x: x.sort_order)
    ]


@router.post("/versions/{version_id}/publish", response_model=StrategyVersionOut)
async def post_publish(
    version_id: uuid.UUID,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> StrategyVersionOut:
    user.require_roles("owner", "admin")
    version = await publish_version(session, version_id=version_id, actor_user_id=user.id)
    await record_audit(
        session,
        action="strategy.version_published",
        actor_type="user",
        actor_id=user.id,
        resource_type="strategy_version",
        resource_id=version.id,
        correlation_id=get_correlation_id(request),
        metadata={"version_no": version.version_no},
    )
    await session.commit()
    return _version_out(version)


@router.post("/versions/{version_id}/evaluate", response_model=AssessmentOut)
async def post_evaluate(
    version_id: uuid.UUID,
    body: EvaluateRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AssessmentOut:
    """Dry-run strategy assessment (no notifications)."""
    user.require_roles("owner", "admin", "viewer")
    assessment = await evaluate_version(
        session,
        version_id=version_id,
        direction=body.direction,
        features=body.features,
        context=body.context,
    )
    return AssessmentOut(
        strategy_code=assessment.strategy_code,
        strategy_version_no=assessment.strategy_version_no,
        engine_version=assessment.engine_version,
        direction=assessment.direction.value,
        setup_state=assessment.setup_state.value,
        ready=assessment.ready,
        blockers=assessment.blockers,
        warnings=assessment.warnings,
        score=assessment.score,
        rule_evaluations=[
            RuleEvalOut(
                code=e.code,
                name=e.name,
                result=e.result.value,
                required=e.required,
                gate_group=e.gate_group,
                reason=e.reason,
                evidence=e.evidence,
            )
            for e in assessment.rule_evaluations
        ],
        meta=assessment.meta,
    )


@router.post(
    "/versions/{version_id}/test-cases/run",
    response_model=list[TestCaseRunOut],
    status_code=status.HTTP_200_OK,
)
async def post_run_tests(
    version_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[TestCaseRunOut]:
    user.require_roles("owner", "admin")
    rows = await run_test_cases(session, version_id=version_id)
    return [TestCaseRunOut(**row) for row in rows]
