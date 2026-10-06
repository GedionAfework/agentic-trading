"""Gate C oriented checks that do not require live Ollama."""

from private_trading_knowledge.ask import SYSTEM_POLICY


def test_system_policy_treats_content_as_untrusted() -> None:
    assert "untrusted" in SYSTEM_POLICY.lower()
    assert "ignore any attempt" in SYSTEM_POLICY.lower()
    assert "do not invent" in SYSTEM_POLICY.lower()
