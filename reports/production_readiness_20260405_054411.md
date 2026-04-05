# SIQE Production Readiness Report

**Generated:** 2026-04-05T05:44:11.491970+00:00
**Status:** ❌ RED - Not ready for production

---

## Executive Summary

| Metric | Value |
|--------|-------|
| Overall Status | **RED** |
| Data Quality | ✅ Valid |
| Walk-Forward (15m) | ❌ Failed |
| Walk-Forward (4h) | ❌ Failed |
| Parameter Stability | 4/9 stable |
| Safety Limits | 100% violation rate |

---

## 1. Data Quality

- **Rows:** 181
- **Date Range:** ('2026-03-05 00:00:00', '2026-04-04 00:00:00')
- **Missing Values:** {'high': 0, 'open': 0, 'low': 0, 'close': 0}
- **Price Anomalies:** []
- **Volume Stats:** {'mean': 30498.94770165746, 'median': 25041.797, 'min': 3902.732, 'max': 98820.429, 'zero_count': 0}
- **Warnings:** []

---

## 2. Walk-Forward Validation (15m)

| Metric | Value |
|--------|-------|
| **Passed** | False |
| **Windows** | 21 |
| **Avg Test Sharpe** | 0.059 |
| **Avg Test Return** | 1.02% |
| **Avg Test Drawdown** | -7.70% |
| **Pass Rate** | 95% |
| **Min Test Sharpe** | -1.103 |
| **Max Test Sharpe** | 0.876 |
| **Total Test Trades** | 649 |

### Per-Window Results

| Window | Train Sharpe | Test Sharpe | Train Return | Test Return | Trades | Passed |
|--------|-------------|-------------|--------------|-------------|--------|--------|
| 0 | 0.582 | 0.442 | 21.20% | 4.14% | 37 | ✅ |
| 1 | 0.441 | -0.719 | 16.09% | -8.04% | 53 | ✅ |
| 2 | 0.329 | 0.445 | 10.58% | 4.98% | 35 | ✅ |
| 3 | 0.410 | 0.324 | 13.55% | 4.77% | 22 | ✅ |
| 4 | 0.439 | -0.798 | 17.66% | -8.45% | 28 | ✅ |
| 5 | 0.173 | 0.821 | 5.97% | 9.93% | 31 | ✅ |
| 6 | 0.274 | -0.017 | 10.26% | -0.41% | 27 | ✅ |
| 7 | 0.331 | 0.120 | 11.10% | 1.25% | 19 | ✅ |
| 8 | 0.574 | 0.051 | 21.85% | 0.29% | 44 | ✅ |
| 9 | 0.358 | -0.079 | 11.62% | -0.61% | 48 | ✅ |
| 10 | 0.212 | -0.049 | 5.73% | -0.58% | 44 | ✅ |
| 11 | 0.084 | 0.145 | 1.68% | 1.08% | 37 | ✅ |
| 12 | 0.236 | -1.103 | 5.52% | -10.46% | 27 | ❌ |
| 13 | -0.435 | 0.876 | -11.58% | 17.32% | 17 | ✅ |
| 14 | 0.227 | -0.171 | 8.45% | -4.35% | 31 | ✅ |
| 15 | 0.193 | -0.109 | 8.88% | -1.41% | 22 | ✅ |
| 16 | 0.398 | 0.425 | 21.54% | 5.13% | 25 | ✅ |
| 17 | 0.157 | 0.193 | 6.29% | 2.71% | 18 | ✅ |
| 18 | 0.261 | -0.386 | 10.08% | -4.96% | 25 | ✅ |
| 19 | 0.265 | 0.593 | 10.51% | 6.49% | 25 | ✅ |
| 20 | 0.259 | 0.241 | 9.95% | 2.66% | 34 | ✅ |

---

## 3. Walk-Forward Validation (4h)

| Metric | Value |
|--------|-------|
| **Passed** | False |
| **Windows** | 0 |
| **Avg Test Sharpe** | 0.000 |
| **Pass Rate** | 0% |

---

## 4. Parameter Stability Analysis (15m)

| Parameter | Mean | Std | CV | Min | Max | Stable |
|-----------|------|-----|----|-----|-----|--------|
| bollinger_period | 26.19 | 11.48 | 0.44 | 10.00 | 40.00 | ⚠️ |
| bollinger_std | 1.87 | 0.48 | 0.26 | 1.00 | 2.50 | ✅ |
| rsi_period | 13.76 | 4.46 | 0.32 | 5.00 | 20.00 | ⚠️ |
| macd_fast | 9.43 | 3.49 | 0.37 | 5.00 | 15.00 | ⚠️ |
| macd_slow | 29.38 | 7.47 | 0.25 | 20.00 | 40.00 | ✅ |
| macd_signal | 8.57 | 2.52 | 0.29 | 5.00 | 12.00 | ✅ |
| atr_period | 13.48 | 5.43 | 0.40 | 5.00 | 20.00 | ⚠️ |
| donchian_period | 25.05 | 9.25 | 0.37 | 10.00 | 40.00 | ⚠️ |
| adx_period | 10.71 | 2.47 | 0.23 | 7.00 | 14.00 | ✅ |

- **Stable Parameters:** 4/9
- **Stable:** bollinger_std, macd_slow, macd_signal, adx_period
- **Unstable:** bollinger_period, rsi_period, macd_fast, atr_period, donchian_period

---

## 5. A/B Test Results

| Metric | Baseline (Default) | Treatment (Bayesian) |
|--------|-------------------|---------------------|
| **Sharpe** | 0.145 | 0.140 |
| **Return** | 39.44% | 37.88% |
| **P-Value** | - | 0.4175 |
| **Significant** | - | False |
| **Recommendation** | - | **INCONCLUSIVE** |

---

## 6. Safety Limits

- **Windows with Violations:** 21/21
- **Violation Rate:** 100%
- **Circuit Breaker:** not_triggered

**Sample Violations:**
- bollinger_period: 20 -> 37 (85.0% change exceeds 20% limit)
- bollinger_std: 2.0 -> 2.5 (25.0% change exceeds 20% limit)
- rsi_period: 14 -> 20 (42.9% change exceeds 20% limit)
- macd_fast: 12 -> 6 (50.0% change exceeds 20% limit)
- macd_slow: 26 -> 20 (23.1% change exceeds 20% limit)

---

## 7. Recommendations

### ❌ Not Ready for Production

- Critical validation failures detected
- Do not deploy until issues are resolved

**Required Actions:**
1. Investigate walk-forward failures
2. Review parameter optimization logic
3. Consider strategy redesign
4. Collect more diverse market data

---

## 8. Configuration Snapshot

**Default Config:**
```json
{
  "bollinger_period": 20,
  "bollinger_std": 2.0,
  "rsi_period": 14,
  "macd_fast": 12,
  "macd_slow": 26,
  "macd_signal": 9,
  "atr_period": 14,
  "donchian_period": 20,
  "adx_period": 14
}
```

**Report saved to:** `reports/production_readiness_20260405_054411.md`
