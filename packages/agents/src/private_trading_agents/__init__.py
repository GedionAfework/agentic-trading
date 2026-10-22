"""Decision orchestrator — recommendation contract (Phase 12)."""

from private_trading_agents.contracts import (
    AgentId,
    CitationModel,
    MarketDataAgentIn,
    MarketDataAgentOut,
    OrchestratorAgentIn,
    OrchestratorAgentOut,
)
from private_trading_agents.roles import (
    run_decision_ml_agent,
    run_journal_agent,
    run_knowledge_agent,
    run_market_data_agent,
    run_risk_agent,
    run_signal_agent,
    run_strategy_agent,
    run_vision_agent,
)
from private_trading_agents.tools import (
    AGENT_TOOL_ALLOWLIST,
    ToolId,
    ToolPermissionError,
    UnknownToolError,
    allowed_tools,
    catalog_summary,
    has_permission,
    invoke_tool,
    permissions_matrix,
)
from private_trading_agents.workflow import (
    WORKFLOW_VERSION,
    CitationRef,
    DecisionAction,
    DecisionSnapshot,
    run_decision_workflow,
)

__all__ = [
    "AGENT_TOOL_ALLOWLIST",
    "WORKFLOW_VERSION",
    "AgentId",
    "CitationModel",
    "CitationRef",
    "DecisionAction",
    "DecisionSnapshot",
    "MarketDataAgentIn",
    "MarketDataAgentOut",
    "OrchestratorAgentIn",
    "OrchestratorAgentOut",
    "ToolId",
    "ToolPermissionError",
    "UnknownToolError",
    "allowed_tools",
    "catalog_summary",
    "has_permission",
    "invoke_tool",
    "permissions_matrix",
    "run_decision_ml_agent",
    "run_decision_workflow",
    "run_journal_agent",
    "run_knowledge_agent",
    "run_market_data_agent",
    "run_risk_agent",
    "run_signal_agent",
    "run_strategy_agent",
    "run_vision_agent",
]
__version__ = WORKFLOW_VERSION
