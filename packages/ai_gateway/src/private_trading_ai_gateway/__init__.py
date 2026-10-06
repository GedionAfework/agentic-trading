"""Private AI gateway — backend-only access to local inference."""

from private_trading_ai_gateway.client import AIGateway, AIGatewayError

__all__ = ["AIGateway", "AIGatewayError"]
__version__ = "0.1.0"
