# Measurable definition backlog

Every ambiguous English term must become a versioned parameter/algorithm, an explicit advisory label, or a documented deferral.

| ID | Term | Candidate v1 (ENGINEERING — not locked) | Validation needed | Lock status |
|----|------|------------------------------------------|-------------------|-------------|
| VOL-001 | Significant volume (BOS) | `bos_volume_ratio = candle_volume / SMA(volume, 20) >= T_sig` | Labeled BOS examples | **OPEN** |
| VOL-002 | Low-volume retest | `retest_volume_ratio = retest_vol / SMA(volume, 20) <= T_low` | Safer-entry examples | **OPEN** |
| VOL-003 | High/low volume baseline | SMA(20) vs median(20) vs session VWAP deviation | Compare on journal | **OPEN** |
| RNG-001 | Wide / narrow range | Range percentile vs ATR(14) ratio thresholds | Chart labels | **OPEN** |
| STR-001 | Swing high/low | N-bar fractal (e.g. 3/5) left+right | Spec + examples | **OPEN** |
| STR-002 | BOS confirmation | Close beyond swing vs wick; wait 0/1 candle | Owner + examples | **OPEN** |
| STR-003 | MSB vs BOS | Document distinct predicates or merge | Course cite | **OPEN** |
| LIQ-001 | Sweep | Pierce level by X ticks/ATR then close back | Examples | **OPEN** |
| FVG-001 | FVG geometry | 3-candle gap; min size in ATR fraction | Course cite | **OPEN** |
| WYK-001 | Spring / UTAD / LPS | Checklist features or `advisory_only` | Course cite | **OPEN** |
| ENT-001 | Safer entry sequence | BOS+sig vol → retest zone → low vol → trigger | End-to-end fixtures | **OPEN** |
| ENT-002 | Aggressive entry | BOS+sig vol → next confirmation candle | Fixtures | **OPEN** |
| STP-001 | Stop buffer | Structure ± `k * ATR` or tick buffer | Risk policy | **OPEN** |
| TP-001 | Staged targets | TP1/TP2/TP3 structure or R-multiples | Owner | **OPEN** |
| RR-001 | Min R:R | `2.0` from five-question gate | Confirm | **PROPOSED 2.0** |
| SMT-001 | Smart Money state | TBD operational flags | Course | **OPEN** |
| SES-001 | Crypto weekend policy | Hard WAIT vs warning | Owner | **OPEN** |
| FXV-001 | FX volume harmony proxy | Tick volume / futures proxy — TBD | Forex materials | **DEFERRED** |

## Rule for coding

```
if lock_status != LOCKED and term is on a mandatory gate:
    either mark gate advisory_only
    or block READY_FOR_REVIEW with reason DEFINITION_UNLOCKED
```

Do not ship silent placeholder thresholds as if they were course fact.
