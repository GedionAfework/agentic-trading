"""Independent agent roles with Pydantic I/O contracts."""

from private_trading_agents.roles.ag02_knowledge import run_knowledge_agent
from private_trading_agents.roles.ag03_vision import run_vision_agent
from private_trading_agents.roles.ag04_market_data import run_market_data_agent
from private_trading_agents.roles.ag05_strategy import run_strategy_agent
from private_trading_agents.roles.ag06_risk import run_risk_agent
from private_trading_agents.roles.ag07_signal import run_signal_agent
from private_trading_agents.roles.ag08_journal import run_journal_agent
from private_trading_agents.roles.ag09_decision_ml import run_decision_ml_agent

__all__ = [
    "run_knowledge_agent",
    "run_vision_agent",
    "run_market_data_agent",
    "run_strategy_agent",
    "run_risk_agent",
    "run_signal_agent",
    "run_journal_agent",
    "run_decision_ml_agent",
]
