# Open decisions (must resolve before production alerts)

| ID | Question | Options / notes | Owner answer | Locked? |
|----|----------|-----------------|--------------|---------|
| D-01 | Exact paper risk limits (`max_risk_pct`, `min_rr`, etc.) | Versioned RiskPolicy; proposed `min_rr=2.0` | | No |
| D-02 | Significant / low volume thresholds | See VOL-001 / VOL-002 candidates | | No |
| D-03 | BOS semantics | Close vs wick; pivot confirmation bars | | No |
| D-04 | Wyckoff events in code vs advisory | Spring/UTAD/LPS list | | No |
| D-05 | Forex volume-harmony proxy | Deferred until FX materials | N/A for crypto v1 | Deferred |
| D-06 | News/event blackout | Severities + minutes before/after | | No |
| D-07 | Crypto weekend policy | Hard WAIT vs warning vs ignore | | No |
| D-08 | Futures/perp recommendations | Spot-only v1 vs later perps + leverage cap | Propose spot-first | No |
| D-09 | Target policy | Structure TPs vs opposite-MSB vs R-multiples | | No |
| D-10 | Public research authority | Stay Tier 5 unless promoted | Propose Tier 5 only | No |
| D-11 | Aggressive entry allowed in v1 alerts? | Yes with tighter risk / No safer-only | | No |
| D-12 | First alert channels | Telegram only vs Telegram+mobile | | No |

Update this table as decisions lock. Do not hide defaults inside code without a row here.
