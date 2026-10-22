"""Gate C oriented checks that do not require live Ollama."""

from private_trading_agents.tools.injection import injection_corpus, looks_like_injection
from private_trading_knowledge.ask import SYSTEM_POLICY


def test_system_policy_treats_content_as_untrusted() -> None:
    assert "untrusted" in SYSTEM_POLICY.lower()
    assert "ignore any attempt" in SYSTEM_POLICY.lower()
    assert "do not invent" in SYSTEM_POLICY.lower()
    assert "tool policy" in SYSTEM_POLICY.lower()


def test_injection_corpus_is_detectable_for_gate_c() -> None:
    for sample in injection_corpus():
        assert looks_like_injection(sample["text"])
