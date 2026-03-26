# Options Edge Scanner Pipeline Review

Date: 2026-03-26
Scope: End-to-end pipeline with emphasis on probability modeling and expected value (EV) calculation.

## Executive Summary

The current codebase has a clean package structure, but the core quantitative pipeline is not yet implemented. As a result, there is no production-valid probability model, no EV engine, and no signal quality controls. The largest immediate risk is false confidence: outputs may appear numeric while encoding placeholder assumptions (e.g., missing quotes set to zero).

## Current Pipeline Assessment

### 1) Data Layer

- `load_option_chain()` is the only substantive component currently in place.
- Calls/puts are normalized and merged, but several data-quality shortcuts can distort downstream EV:
  - Missing bid/ask are filled with `0.0`.
  - Midpoint is always `(bid + ask)/2` regardless of spread quality, staleness, or crossed/locked markets.
  - One underlying spot snapshot is reused for all expirations in the loop.

### 2) Modeling Layer (Probability/Fair Value)

- `estimate_fair_value()` is currently a stub that returns an empty series.
- No distributional assumptions are defined (risk-neutral vs. real-world).
- No calibration routine exists (surface smoothing, arbitrage checks, or model diagnostics).

### 3) Signal Layer

- `generate_edge_signals()` is currently a stub that returns an empty dataframe.
- No ranking, risk constraints, or confidence gating exists.

### 4) Backtest/Validation Layer

- `run_backtest()` is currently a stub.
- No transaction-cost model, no slippage, no queue/partial-fill logic, and no Greeks-based risk decomposition exists.

### 5) Orchestration/Config

- `run_scan()` is not wired.
- Default config has an empty symbol universe and a `0.0` risk-free rate, which can silently produce unrealistic valuations if reused downstream.

## Weaknesses (Focused on Probability Model & EV)

1. **No probability model exists today**
   - There is no implemented framework for mapping market data to outcome probabilities.
   - Consequence: EV cannot be computed on a defensible probabilistic basis.

2. **Potentially invalid input prices for EV**
   - Filling missing bid/ask with zero creates artificial cheap options and systematically biases EV upward for long-option candidates.
   - Raw midpoint without liquidity filters can overstate executable edge.

3. **No definition of EV measure**
   - EV can mean risk-neutral value gap, real-world PnL expectation, utility-adjusted value, or cost-adjusted trade expectancy.
   - Without explicit definition, signal ranking will be inconsistent and fragile.

4. **No separation of risk-neutral vs. physical probabilities**
   - Option prices imply risk-neutral densities; trading alpha depends on physical (real-world) probabilities net of risk premia and costs.
   - Treating one as the other is a common but material conceptual error.

5. **No uncertainty accounting around parameter estimation**
   - Even with a model, edge should include confidence intervals or posterior uncertainty.
   - Point estimates alone can cause severe overtrading of noise.

6. **No horizon consistency checks**
   - Probability horizon (e.g., to expiration vs. fixed holding period) must align with EV horizon and execution assumptions.

## Unrealistic Assumptions to Remove

1. **Bid/ask missing implies zero**
   - Unrealistic in live markets and harmful for EV.

2. **Midpoint is always executable**
   - Unrealistic, especially in wide-spread contracts.

3. **Single spot value valid for all contracts throughout data collection**
   - In fast markets, stale underlying snapshots can skew moneyness and Greeks.

4. **Risk-free rate = 0.0 by default**
   - Unrealistic in current rate regimes and distorts forward/discounting logic.

5. **Implicit frictionless trading**
   - No commissions, fees, slippage, assignment risk, borrow constraints, or margin effects are modeled.

## Improvement Plan (Priority Order)

### Phase 1 — Hardening Inputs for EV

- Replace zero-fill with NA-preserving logic; drop or quarantine contracts with invalid quotes.
- Add liquidity filters: minimum open interest/volume, maximum relative spread, minimum NBBO quality.
- Define executable price policy (e.g., conservative fill = mid ± spread penalty based on side and liquidity).
- Timestamp and align underlying spot with option quote times where possible.

### Phase 2 — Implement Probability Model (Two-track)

1. **Risk-neutral track (market-implied)**
   - Build a clean implied vol surface per expiry.
   - Enforce static arbitrage sanity checks (calendar and butterfly constraints where practical).
   - Convert to risk-neutral payoff expectations for consistency checks.

2. **Physical track (forecasting alpha)**
   - Train/estimate a real-world return distribution model (regime-aware volatility + jump component, or quantile model).
   - Calibrate with rolling windows and strict out-of-sample evaluation.

### Phase 3 — EV Engine Definition

Define EV per trade candidate as:

- `EV = E_physical[payoff at horizon] - executable_entry_cost - carry/fees - slippage - margin/financing adjustments`

and report alongside:

- Probability of profit,
- Expected shortfall / CVaR,
- Break-even move,
- Sensitivity to vol and skew shifts.

### Phase 4 — Signal and Portfolio Controls

- Rank by **cost-adjusted EV per unit risk** (not raw EV).
- Add confidence thresholds (e.g., only trade when lower CI bound of EV > 0).
- Enforce portfolio-level constraints: net delta/vega/gamma/theta, concentration, expiry buckets.

### Phase 5 — Backtest Realism

- Event-driven backtest with realistic execution model.
- Include early assignment modeling for American options (for short ITM legs with dividends/carry triggers).
- Validate stability across market regimes (high/low vol, crash/rebound).

## Minimal Technical Spec for Next Iteration

1. `models/pricing.py`
   - Implement `estimate_fair_value()` with explicit interface:
     - inputs: normalized chain + rates + dividend assumptions + horizon
     - outputs: fair value, model probability metrics, uncertainty bands

2. `signals/generator.py`
   - Implement schema with:
     - candidate side, executable price, EV, EV CI, liquidity score, risk score

3. `backtest/runner.py`
   - Implement fill simulator + cost model + PnL attribution

4. `scanner/engine.py`
   - Wire deterministic pipeline and fail fast if required fields are missing

## Acceptance Criteria for “Probability + EV Ready”

- EV definition documented and unit-tested.
- No zero-filled quote artifacts entering EV calculation.
- Out-of-sample evaluation demonstrates stable edge after costs.
- Backtest includes transaction costs and conservative fill assumptions.
- Signal output includes EV uncertainty and liquidity-adjusted confidence.
