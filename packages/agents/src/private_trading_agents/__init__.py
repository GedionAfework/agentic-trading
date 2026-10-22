"""Decision orchestrator — recommendation contract (Phase 12)."""

from private_trading_agents.agent_runtime import (
    AgentBudget,
    AgentSession,
    BudgetExceededError,
    ToolTrace,
    agent_session,
    call_tool,
)
from private_trading_agents.ask_agent import (
    AskAgentResult,
    AskTradeAuthorityError,
    assert_ask_surface_permissions,
    run_ask_agent,
)
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
from private_trading_agents.shadow import (
    ShadowCompareResult,
    compare_decision_snapshots,
    run_decision_with_optional_shadow,
    shadow_agentic_enabled,
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
    "AgentBudget",
    "AgentId",
    "AgentSession",
    "AskAgentResult",
    "AskTradeAuthorityError",
    "BudgetExceededError",
    "CitationModel",
    "CitationRef",
    "DecisionAction",
    "DecisionSnapshot",
    "MarketDataAgentIn",
    "MarketDataAgentOut",
    "OrchestratorAgentIn",
    "OrchestratorAgentOut",
    "ShadowCompareResult",
    "ToolId",
    "ToolPermissionError",
    "ToolTrace",
    "UnknownToolError",
    "agent_session",
    "allowed_tools",
    "assert_ask_surface_permissions",
    "call_tool",
    "catalog_summary",
    "compare_decision_snapshots",
    "has_permission",
    "invoke_tool",
    "permissions_matrix",
    "run_ask_agent",
    "run_decision_ml_agent",
    "run_decision_with_optional_shadow",
    "run_decision_workflow",
    "run_journal_agent",
    "run_knowledge_agent",
    "run_market_data_agent",
    "run_risk_agent",
    "run_signal_agent",
    "run_strategy_agent",
    "run_vision_agent",
    "shadow_agentic_enabled",
]
__version__ = WORKFLOW_VERSION
