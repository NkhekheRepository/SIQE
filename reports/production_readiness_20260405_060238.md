# SIQE Production Readiness Report

**Generated:** 2026-04-05T06:02:38.319866+00:00
**Status:** ⚠️ YELLOW - Needs attention before production

---

## Executive Summary

| Metric | Value |
|--------|-------|
| Overall Status | **YELLOW** |
| Data Quality | ✅ Valid |
| Walk-Forward (15m) | ❌ Failed |
| Walk-Forward (4h) | ❌ Failed |
| Parameter Stability | 9/9 stable |
| Safety Limits | 33% violation rate |

---

## 1. Data Quality

- **Rows:** 181
- **Date Range:** ('2026-03-05 00:00:00', '2026-04-04 00:00:00')
- **Missing Values:** {'close': 0, 'high': 0, 'low': 0, 'open': 0}
- **Price Anomalies:** []
- **Volume Stats:** {'mean': 30498.94770165746, 'median': 25041.797, 'min': 3902.732, 'max': 98820.429, 'zero_count': 0}
- **Warnings:** []

---

## 2. Walk-Forward Validation (15m)

| Metric | Value |
|--------|-------|
| **Passed** | False |
| **Windows** | 21 |
| **Avg Test Sharpe** | 0.103 |
| **Avg Test Return** | 1.07% |
| **Avg Test Drawdown** | -4.89% |
| **Pass Rate** | 95% |
| **Min Test Sharpe** | -1.411 |
| **Max Test Sharpe** | 0.835 |
| **Total Test Trades** | 2247 |

### Per-Window Results

| Window | Train Sharpe | Test Sharpe | Train Return | Test Return | Trades | Passed |
|--------|-------------|-------------|--------------|-------------|--------|--------|
| 0 | -0.239 | 0.425 | -3.00% | 3.00% | 108 | ✅ |
| 1 | 0.145 | -0.116 | 3.46% | -1.12% | 84 | ✅ |
| 2 | 0.130 | 0.516 | 2.87% | 4.40% | 111 | ✅ |
| 3 | 0.412 | 0.295 | 10.23% | 1.52% | 114 | ✅ |
| 4 | 0.342 | -0.465 | 4.56% | -2.32% | 106 | ✅ |
| 5 | 0.339 | 0.743 | 5.61% | 6.56% | 99 | ✅ |
| 6 | 0.218 | 0.364 | 6.02% | 3.01% | 101 | ✅ |
| 7 | 0.291 | 0.043 | 7.28% | 0.25% | 101 | ✅ |
| 8 | 0.426 | -0.677 | 11.67% | -4.16% | 100 | ✅ |
| 9 | 0.016 | 0.835 | 0.05% | 4.32% | 103 | ✅ |
| 10 | 0.040 | -0.257 | 0.60% | -1.88% | 106 | ✅ |
| 11 | -0.107 | 0.024 | -2.15% | 0.08% | 113 | ✅ |
| 12 | 0.221 | -1.411 | 3.94% | -10.26% | 137 | ❌ |
| 13 | -0.528 | 0.789 | -10.65% | 11.22% | 87 | ✅ |
| 14 | 0.035 | -0.180 | 0.51% | -1.83% | 106 | ✅ |
| 15 | 0.051 | 0.007 | 0.86% | -0.07% | 112 | ✅ |
| 16 | 0.311 | 0.224 | 12.13% | 1.97% | 116 | ✅ |
| 17 | 0.101 | 0.082 | 2.90% | 0.40% | 110 | ✅ |
| 18 | 0.225 | 0.099 | 3.04% | 0.39% | 110 | ✅ |
| 19 | 0.116 | 0.627 | 1.55% | 5.16% | 109 | ✅ |
| 20 | 0.248 | 0.205 | 7.19% | 1.75% | 114 | ✅ |

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
| bollinger_period | 20.00 | 0.00 | 0.00 | 20.00 | 20.00 | ✅ |
| bollinger_std | 1.90 | 0.16 | 0.08 | 1.72 | 2.24 | ✅ |
| rsi_period | 14.00 | 0.00 | 0.00 | 14.00 | 14.00 | ✅ |
| macd_fast | 12.00 | 0.00 | 0.00 | 12.00 | 12.00 | ✅ |
| macd_slow | 26.00 | 1.63 | 0.06 | 24.00 | 28.00 | ✅ |
| macd_signal | 8.95 | 0.58 | 0.06 | 8.00 | 10.00 | ✅ |
| atr_period | 14.00 | 0.00 | 0.00 | 14.00 | 14.00 | ✅ |
| donchian_period | 20.00 | 0.00 | 0.00 | 20.00 | 20.00 | ✅ |
| adx_period | 14.10 | 0.61 | 0.04 | 13.00 | 15.00 | ✅ |

- **Stable Parameters:** 9/9
- **Stable:** bollinger_period, bollinger_std, rsi_period, macd_fast, macd_slow, macd_signal, atr_period, donchian_period, adx_period
- **Unstable:** 

---

## 5. A/B Test Results

| Metric | Baseline (Default) | Treatment (Bayesian) |
|--------|-------------------|---------------------|
| **Sharpe** | 0.145 | 0.141 |
| **Return** | 39.44% | 38.27% |
| **P-Value** | - | 0.4880 |
| **Significant** | - | False |
| **Recommendation** | - | **INCONCLUSIVE** |

---

## 6. Safety Limits

- **Windows with Violations:** 7/21
- **Violation Rate:** 33%
- **Circuit Breaker:** not_triggered

**Sample Violations:**
- macd_signal: 9 -> 8 (11.1% change exceeds 10% limit)
- macd_signal: 9 -> 8 (11.1% change exceeds 10% limit)
- macd_signal: 9 -> 10 (11.1% change exceeds 10% limit)
- macd_signal: 9 -> 10 (11.1% change exceeds 10% limit)
- macd_signal: 9 -> 10 (11.1% change exceeds 10% limit)

---

## 7. Recommendations

### ⚠️ Needs Attention Before Production

- Some validation criteria not fully met
- Review unstable parameters and consider freezing them
- Increase walk-forward window size for more robust testing

**Recommended Actions:**
1. Freeze unstable parameters (use defaults)
2. Collect more historical data
3. Re-run validation with adjusted thresholds
4. Paper trade for 2-4 weeks before live deployment

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

**Report saved to:** `reports/production_readiness_20260405_060238.md`
