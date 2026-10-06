from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SmokeStructuredOut(BaseModel):
    ok: bool
    echo: str
    notes: str = ""


class AIHealthResponse(BaseModel):
    status: str
    circuit: str
    endpoint: str
    models: list[str] = Field(default_factory=list)
    main_model: str | None = None
    embedding_model: str | None = None
    error: str | None = None


class SmokeGenerateRequest(BaseModel):
    echo: str = Field(default="phase-3-smoke", max_length=200)


class SmokeGenerateResponse(BaseModel):
    result: SmokeStructuredOut
    meta: dict[str, Any]


class SmokeEmbedRequest(BaseModel):
    text: str = Field(default="private trading copilot embedding smoke", max_length=2000)


class SmokeEmbedResponse(BaseModel):
    dimensions: int
    preview: list[float]
    model: str
