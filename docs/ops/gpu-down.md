# Runbook: GPU / Ollama down

## Symptoms
- `/v1/ai/health` fails or circuit breaker opens.
- Vision / Ask AI return 502/503 with retryable AI gateway errors.
- Explanations fall back to grounded deterministic text (expected).

## Immediate actions
1. Confirm Ollama is bound to `127.0.0.1:11434` only (never public).
2. Restart Ollama; verify `main_model` / `embedding_model` tags exist.
3. Trading path stays online: strategy/risk/scanner do not require GPU.
4. If VLM is down, screenshot flow remains advisory — `authorizes_trade` stays false.

## Verify
- AI health recovers; no change to kill switches required unless alert spam starts.
- Never promote a challenger model because “GPU was down.”
