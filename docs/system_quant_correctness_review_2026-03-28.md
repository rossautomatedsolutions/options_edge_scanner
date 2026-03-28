# System Quant Correctness Review (Critical)

Date: 2026-03-28  
Reviewer stance: correctness-first, intentionally adversarial.

## Scope

Repository-wide review with priority on:

1. Spread construction correctness
2. Pricing math correctness (max profit / max loss / breakeven)
3. Probability model assumptions and implementation
4. Expected value (EV) logic

## Highest-Severity Findings

### 1) `estimate_probability_of_profit()` computes probability of finishing **between strikes**, not probability of **profit** for most spread types

- Implementation computes `P(low <= S_T <= high)` using lognormal CDF difference.
- For vertical debit or credit spreads, actual probability of profit depends on **entry cost/credit** and therefore **breakeven**, not simply the interval between strikes.
- Example conceptual mismatch:
  - Bull put credit spread profits for all `S_T > short_strike - credit`, not only a bounded interval.
  - Bear call credit spread profits for all `S_T < short_strike + credit`.
- Result: reported PoP is structurally biased and can be directionally wrong.

### 2) `calculate_expected_value()` is schema-incompatible with generated spread rows and can silently produce inconsistent EV definitions

- EV calculator expects keys `payoff` and `loss`.
- Spread generators produce fields like `credit`, `max_loss`, `max_profit`, `cost` and do **not** emit `payoff` / `loss` consistently.
- There are effectively multiple incompatible EV schemas in repo, so integration can fail or produce apples-to-oranges ranking depending on caller adaptation.

### 3) Spread ranking applies contradictory filters (`EV` and `expected_value`) from different conventions

- Ranker requires columns `EV`, `probability`, `expected_value`, `edge_pct` simultaneously.
- This implies duplicated or differently-defined EV measures must coexist in one frame.
- A candidate can pass one EV metric and fail another due to naming mismatch, not economics.

### 4) Quote preprocessing (`bid/ask` NaN -> `0.0`) can create fake edge

- Loader fills missing bid/ask with zero, then computes mid = `(bid + ask)/2`.
- This can manufacture tiny/cheap quotes that do not exist in executable markets.
- Any downstream credit/debit and EV based on these mids is potentially upward biased.

## Detailed Findings by Area

## A) Spread Construction

### A1. `scanner/spread_generator.py` constructs **debit verticals** only, while `run_scanner.py` constructs **credit verticals**

- `generate_vertical_spreads()` outputs call debit + put debit verticals (`cost`, `max_profit=width-cost`).
- `run_scanner.py` builds put/call credit spreads (`credit`, `max_loss=width-credit`).
- This is not inherently wrong, but the repository has no canonical spread schema, causing downstream ambiguity in probability and EV treatment.

### A2. Hard strike-width cap in one module (`width > 10` skipped) is arbitrary and non-scale-aware

- A fixed 10-point cap is used in `generate_vertical_spreads()`.
- This silently drops valid wide spreads on high-price underlyings and keeps proportionally huge widths on low-price names.
- `run_scanner.py` instead uses a relative cap (`MAX_STRIKE_GAP_RATIO`), creating non-uniform behavior across pipelines.

### A3. Pairwise combinatorics include non-adjacent strikes without liquidity validation

- Both generators iterate all strike pairs.
- No open-interest, volume, quote quality, or crossed-market checks exist.
- Spreads can be generated from stale/illiquid legs, making payoff math mechanically valid but economically misleading.

## B) Pricing Math (Max Profit / Max Loss / Breakeven)

### B1. Credit spread `max_loss = width - credit` is correct, but breakeven is missing where probability/EV uses short strike thresholds

- `run_scanner.py` computes credit and max loss correctly for textbook vertical credits.
- However, PoP logic uses short strike as the event boundary (max-profit boundary), not breakeven (`short ± credit`) for positive expectancy event.
- This systematically misstates the probability associated with EV sign.

### B2. Debit spread math in `spread_generator.py` omits breakeven and max-loss field

- It computes `cost`, `max_profit=width-cost`, `width`.
- For debit spreads, max loss should be explicitly `cost`, and breakeven should be tracked (`lower+cost` for call debit, `upper-cost` for put debit).
- Missing fields promote misuse by downstream generic EV functions expecting `loss`/`payoff`.

### B3. `cost < width` validity gate assumes European expiry payoff only and ignores early-exercise/assignment path risk

- Algebraically valid at expiration, but hidden assumption is that PnL is evaluated only at expiry with no assignment/frictions.
- This can materially understate risk for short American legs.

## C) Probability Model

### C1. Drift assumption is risk-neutral-like (`-0.5σ²T` in log-return) but presented as “probability of profit” for trading decisions

- The implementation effectively uses zero expected return in spot measure with lognormal volatility term.
- This is a modeling choice closer to risk-neutral terminal distribution usage than physical-return forecasting.
- Using it as alpha-driving PoP is a hidden assumption: no risk premium, no skew dynamics, no jumps/regimes.

### C2. Vol input handling assumes IV in decimal (e.g., 0.25) with no guardrails for percentage-form inputs (e.g., 25)

- If upstream data occasionally provides IV in percent units, sigma explodes and PoP collapses toward trivial values.
- No sanity bounds or normalization checks are present.

### C3. Time basis inconsistency (252 vs 365.25)

- `probability_estimator.py` uses 252 trading days per year.
- `run_scanner.py` uses 365.25 calendar days conversion.
- This creates systematic drift between modules for otherwise identical inputs.

### C4. Single underlying snapshot reused across all expirations in loader

- Loader fetches one underlying close and stamps every contract with it.
- For asynchronous quote collection, this can desynchronize moneyness and probability calculations.

## D) Expected Value Logic

### D1. EV formula in calculator is two-point payoff approximation with constant fixed transaction cost

- `EV = p*payoff - (1-p)*loss - 0.05` treats payoff as binary win/loss outcome.
- Real spread payoff is piecewise linear; for many spreads, expected payoff cannot be represented by a simple Bernoulli with one profit/loss magnitude unless `p` is specifically probability of max-profit/max-loss endpoints and middle region treated explicitly.
- Current implementation does not model middle-zone outcomes.

### D2. `run_scanner.py` EV uses `pop*credit - (1-pop)*max_loss` with PoP = probability of max-profit condition

- This again collapses continuous payoff into binary states and over/under-estimates EV depending on distribution mass in partial-loss/partial-profit region near strikes.
- No explicit transaction costs/slippage included here (unlike fixed cost in calculator), creating inconsistent EV across modules.

### D3. Edge percentage denominator choice is fragile

- `edge_pct = expected_value / loss` uses maximum loss as denominator.
- For comparing debit vs credit spreads, this is not scale-neutral and can mis-rank structurally different profiles.
- Not “wrong” mathematically, but a hidden normalization assumption that can mislead consumers.

## Where Outputs Can Mislead Users

1. **Labeling mismatch:** “probability_of_profit” may actually mean probability of max-profit region or between-strikes mass, depending on module.
2. **Apparent precision from placeholder/stubbed pipeline:** core production modules (`pricing.py`, `signals/generator.py`, `scanner/engine.py`) are stubs, yet executable script emits ranked opportunities.
3. **Data quality artifacts:** zero-filled quotes can create fake cheap legs and exaggerated EV.
4. **Inconsistent annualization and schema conventions:** two code paths can disagree materially while both appear “correct.”

## Conclusion

The repository contains pockets of mathematically correct local formulas (e.g., width/credit/loss identities) but fails system-level correctness due to semantic mismatches:

- “Probability of profit” is inconsistently defined and often not profit-aligned.
- EV is modeled with incompatible schemas and inconsistent assumptions.
- Data preprocessing can inject artificial edge.

As currently implemented, outputs should be treated as exploratory diagnostics, **not** decision-grade quantitative signals.
