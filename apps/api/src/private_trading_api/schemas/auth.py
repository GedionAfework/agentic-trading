from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    device_name: str | None = Field(default=None, max_length=200)


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: uuid.UUID
    roles: list[str]


class SessionOut(BaseModel):
    id: uuid.UUID
    device_name: str | None
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    current: bool = False


class MeResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    display_name: str | None
    roles: list[str]
    status: str
