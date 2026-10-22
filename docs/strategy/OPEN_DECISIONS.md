# Open decisions (must resolve before production alerts)

| ID | Question | Options / notes | Owner answer | Locked? |
|----|----------|-----------------|--------------|---------|
| D-01 | Exact paper risk limits (`max_risk_pct`, `min_rr`, etc.) | Versioned RiskPolicy; proposed `min_rr=2.0` | Soak policy locked: SOL V1 `min_rr=3.0`, base `risk_pct=0.5`, cut to 0.35 if holdout DD>10R or 0.25 if DD>15R. Never raise size because soak looked good. Active only when `soak_step4` PASSes | Yes (policy) |
| D-02 | Significant / low volume thresholds | See VOL-001 / VOL-002 candidates | | No |
| D-03 | BOS semantics | Close vs wick; pivot confirmation bars | Course still teaches **close-based** MSB; engine already uses close vs prior swing (STR-002 EC). Not locked | No |
| D-04 | Wyckoff events in code vs advisory | Spring/UTAD/LPS list | | No |
| D-05 | Forex volume-harmony proxy | Deferred until FX materials; OHLC can ingest via Yahoo free feed (volume often 0) | Specialist FX families also ignored Yahoo volume and used price, daily trend, and London/NY sessions only. All eight pairs failed after-cost walk-forward; USD/CAD, NZD/USD, and EUR/GBP stayed WAIT every fold. FX remains research-only | Deferred |
| D-06 | News/event blackout | Severities + minutes before/after | | No |
| D-07 | Crypto weekend policy | Hard WAIT vs warning vs ignore | | No |
| D-08 | Futures/perp recommendations | Spot-only v1 vs later perps + leverage cap | Propose spot-first | No |
| D-09 | Target policy | Structure TPs vs opposite-MSB vs R-multiples | | No |
| D-10 | Public research authority | Stay Tier 5 unless promoted | Propose Tier 5 only | No |
| D-11 | Aggressive entry allowed in v1 alerts? | Yes with tighter risk / No safer-only | No. Live alerts stay blocked until Step 5 `READY` **and** explicit release unlock. Soak gate default is WAIT; `live_alerts_allowed` stays false in code | Yes |
| D-12 | First alert channels | Telegram only vs Telegram+mobile | Telegram only (Phase 20 default) | Yes |
| D-13 | Promote any pair specialist to paper? | Per-symbol nested walk-forward vs pooled ranking | No. BTC/ETH/BNB/FX failed gates; SOL specialists did not beat V1 expectancy or V2 win rate. Registry stays empty until a later research version beats those bars | Yes |
| D-14 | Which model is the paper soak? | V1 profit vs V2 win-rate | V1 (`profit`, `sol-mtf-bos-volume-profit`). V2 stays frozen; do not switch without updating `SOAK_FREEZE.md` | Yes |
| D-15 | SOL soak-confirmed for paper? | Wait until Step 3/4 vs force-confirm | No until `soak_step4.decision=PASS`. Live alerts stay blocked even after PASS | Yes (gate) |
| D-16 | Enable live alerts after soak? | Auto vs explicit owner unlock | Explicit only. Requires Step 4 PASS + `soak_live_alert_owner_unlock` + release checklist. Default WAIT; Telegram only | Yes |
| D-17 | Promote SOL daily4h V3 challenger? | Promote vs reject vs re-search | Reject. Nested WF: 42 trades, +0.475R, 2.18 PF — beats V1 mean R but fails ≥80 trade floor. Keep research-only; do not lower the gate | Yes |
| D-18 | Owner 2-week coin set? | Keep BNB vs BTC/ETH/SOL/DOGE | Owner set = BTC, ETH, SOL, DOGE. Best agent fail-closes; paper only for validated models; live alerts off by default | Yes |

Update this table as decisions lock. Do not hide defaults inside code without a row here.
