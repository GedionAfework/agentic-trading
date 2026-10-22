"""I/O for AG-01 routing tools (no raw engine access)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RoutingEmptyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RoutingStepOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    status: str
    note: str = ""


class WorkflowFinishOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finished: bool = True
    action: str
    required_complete: bool = True
    completed_tools: list[str] = Field(default_factory=list)
