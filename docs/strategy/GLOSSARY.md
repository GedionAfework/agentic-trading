# Strategy glossary

**Status:** Draft — definitions pending primary source cites  
**Legend:** SD = SOURCE-DERIVED (pending cite) · EC = ENGINEERING CANDIDATE · ADV = AI-only/advisory until locked · GAP = unspecified

| Term | Working meaning | Status | Measurable? |
|------|-----------------|--------|-------------|
| Effort vs Result | Volume = Effort; Price = Result | SD | Partial — needs volume/range formulas |
| Harmony | Volume and price movement agree (continuation bias) | SD | Needs rule version |
| Divergence | Volume and price disagree (reversal warning) | SD | Needs rule version |
| BOS | Break of structure — strategy-specific, not universal ICT | SD | **Must lock** close vs wick, confirmation |
| MSB | Market structure break (related structural event) | SD | Must lock vs BOS distinction |
| CHOCH | Change of character (if used) | GAP/ADV | Confirm if in course |
| HTF | Higher timeframe: Weekly/Monthly for Wyckoff/structure | SD | Enum of TFs |
| Setup TF | Daily / 4H for setup/trend/entry zone | SD | Enum |
| Timing TF | 1H / 30m for order flow / entry timing | SD | Enum |
| Accumulation / Distribution | Wyckoff cause phases | SD | Phase classifier: code vs advisory |
| Spring | Wyckoff spring event | SD | Needs deterministic criteria or ADV |
| UTAD | Upthrust after distribution | SD | Needs criteria or ADV |
| LPS | Last point of support | SD | Needs criteria or ADV |
| Liquidity sweep / stop hunt | Sweep beyond structural level then reclaim | SD | Needs displacement/reclaim rules |
| FVG / imbalance | Fair value gap / inefficiency | SD | Gap geometry version |
| Safer entry | BOS + significant volume → retest → low retest volume → entry | SD | Thresholds EC |
| Aggressive entry | Confirmed BOS + volume → first confirmation candle | SD | Confirmation candle EC |
| Significant volume | Course concept — not yet numeric | SD → EC | Backlog item VOL-001 |
| Low-volume retest | Course concept — not yet numeric | SD → EC | Backlog item VOL-002 |
| Structural stop | Invalidation beyond hunt zone / structure | SD | Buffer policy OWNER |
| R:R gate | Minimum 1:2 in five-question checklist | SD | `min_rr = 2.0` default candidate |
| Smart Money state | Pre-entry checklist item | SD | Needs operational definition |
| Balance vs imbalance | Auction / market context | SD | ADV until features locked |
| CVD | Cumulative volume delta (crypto) | SD context | Provider-dependent |
| OI / funding / liquidations | Crypto derivatives context | SD context | Optional hard gate later |

## Product terms (engineering)

| Term | Meaning |
|------|---------|
| Setup | Candidate trade condition from a strategy version; not guaranteed publishable |
| Signal | User-facing lifecycle after publish/risk policy |
| Decision | Final recommendation action + evidence snapshot |
| UNKNOWN | Rule result when required evidence missing — blocks READY |
