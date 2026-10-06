from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from private_trading_api.main import create_app
from private_trading_core.config import get_settings
from private_trading_db.models.ops import AuditEvent
from private_trading_db.services.auth import create_user, get_user_by_email
from private_trading_db.session import dispose_engine, get_session_factory
from sqlalchemy import select


def _seed_owner() -> dict[str, str]:
    email = f"owner-{uuid.uuid4().hex[:8]}@example.com"
    password = "test-password-123"

    async def _run() -> None:
        factory = get_session_factory()
        async with factory() as session:
            existing = await get_user_by_email(session, email)
            if existing is None:
                await create_user(
                    session,
                    email=email,
                    password=password,
                    display_name="Test Owner",
                    roles=["owner", "admin"],
                )
                await session.commit()

    asyncio.run(_run())
    return {"email": email, "password": password}


@pytest.fixture
def auth_client() -> tuple[TestClient, dict[str, str]]:
    get_settings.cache_clear()
    asyncio.run(dispose_engine())
    creds = _seed_owner()
    asyncio.run(dispose_engine())
    with TestClient(create_app()) as client:
        yield client, creds
    asyncio.run(dispose_engine())


def test_login_success_and_me(auth_client: tuple[TestClient, dict[str, str]]) -> None:
    client, owner_creds = auth_client
    login = client.post("/v1/auth/login", json={**owner_creds, "device_name": "pytest"})
    assert login.status_code == 200, login.text
    body = login.json()
    assert "access_token" in body
    assert "refresh_token" in body

    me = client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == owner_creds["email"]
    assert "owner" in me.json()["roles"]


def test_login_invalid_password_generic(auth_client: tuple[TestClient, dict[str, str]]) -> None:
    client, owner_creds = auth_client
    response = client.post(
        "/v1/auth/login",
        json={"email": owner_creds["email"], "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid email or password"

    unknown = client.post(
        "/v1/auth/login",
        json={"email": "missing@example.com", "password": "wrong-password"},
    )
    assert unknown.status_code == 401
    assert unknown.json()["error"]["message"] == "Invalid email or password"


def test_refresh_rotation_rejects_old_token(auth_client: tuple[TestClient, dict[str, str]]) -> None:
    client, owner_creds = auth_client
    login = client.post("/v1/auth/login", json=owner_creds)
    assert login.status_code == 200
    refresh_token = login.json()["refresh_token"]

    refreshed = client.post("/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refreshed.status_code == 200

    reused = client.post("/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert reused.status_code == 401


def test_revoke_session_blocks_refresh(auth_client: tuple[TestClient, dict[str, str]]) -> None:
    client, owner_creds = auth_client
    login = client.post("/v1/auth/login", json={**owner_creds, "device_name": "to-revoke"})
    assert login.status_code == 200
    access = login.json()["access_token"]
    refresh_token = login.json()["refresh_token"]

    sessions = client.get("/v1/auth/sessions", headers={"Authorization": f"Bearer {access}"})
    assert sessions.status_code == 200
    active = [s for s in sessions.json() if s["revoked_at"] is None]
    assert len(active) >= 1

    revoke = client.post(
        f"/v1/auth/sessions/{active[0]['id']}/revoke",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert revoke.status_code == 204

    after = client.post("/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert after.status_code == 401


def test_login_failure_audited() -> None:
    get_settings.cache_clear()
    asyncio.run(dispose_engine())
    email = f"ghost-{uuid.uuid4().hex[:8]}@example.com"
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/auth/login",
            json={"email": email, "password": "not-the-password"},
        )
        assert response.status_code == 401

    async def _check() -> None:
        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(
                select(AuditEvent)
                .where(AuditEvent.action == "auth.login_failed")
                .order_by(AuditEvent.occurred_at.desc())
                .limit(10)
            )
            events = list(result.scalars().all())
        assert any(e.metadata_.get("email") == email for e in events)

    asyncio.run(_check())
    asyncio.run(dispose_engine())
