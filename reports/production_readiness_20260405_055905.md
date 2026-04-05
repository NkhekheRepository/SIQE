# SIQE Production Readiness Report

**Generated:** 2026-04-05T05:59:05.561601+00:00
**Status:** ⚠️ YELLOW - Needs attention before production

---

## Executive Summary

| Metric | Value |
|--------|-------|
| Overall Status | **YELLOW** |
| Data Quality | ✅ Valid |
| Walk-Forward (15m) | ❌ Failed |
| Walk-Forward (4h) | ❌ Failed |
| Parameter Stability | 7/9 stable |
| Safety Limits | 100% violation rate |

---

## 1. Data Quality

- **Rows:** 181
- **Date Range:** ('2026-03-05 00:00:00', '2026-04-04 00:00:00')
- **Missing Values:** {'open': 0, 'high': 0, 'close': 0, 'low': 0}
- **Price Anomalies:** []
- **Volume Stats:** {'mean': 30498.94770165746, 'median': 25041.797, 'min': 3902.732, 'max': 98820.429, 'zero_count': 0}
- **Warnings:** []

---

## 2. Walk-Forward Validation (15m)

| Metric | Value |
|--------|-------|
| **Passed** | False |
| **Windows** | 21 |
| **Avg Test Sharpe** | 0.051 |
| **Avg Test Return** | 0.68% |
| **Avg Test Drawdown** | -4.76% |
| **Pass Rate** | 100% |
| **Min Test Sharpe** | -0.996 |
| **Max Test Sharpe** | 0.926 |
| **Total Test Trades** | 2225 |

### Per-Window Results

| Window | Train Sharpe | Test Sharpe | Train Return | Test Return | Trades | Passed |
|--------|-------------|-------------|--------------|-------------|--------|--------|
| 0 | -0.034 | 0.329 | -0.49% | 2.29% | 112 | ✅ |
| 1 | 0.176 | -0.063 | 4.30% | -0.67% | 80 | ✅ |
| 2 | 0.082 | 0.691 | 1.66% | 5.94% | 115 | ✅ |
| 3 | 0.388 | 0.326 | 9.64% | 1.77% | 110 | ✅ |
| 4 | 0.423 | -0.658 | 5.78% | -3.26% | 108 | ✅ |
| 5 | 0.253 | 0.818 | 4.26% | 7.26% | 89 | ✅ |
| 6 | 0.311 | -0.045 | 8.97% | -0.52% | 103 | ✅ |
| 7 | 0.134 | -0.073 | 3.10% | -0.87% | 99 | ✅ |
| 8 | 0.510 | -0.587 | 14.18% | -3.62% | 98 | ✅ |
| 9 | 0.090 | 0.538 | 1.89% | 2.75% | 107 | ✅ |
| 10 | 0.078 | -0.119 | 1.44% | -0.90% | 108 | ✅ |
| 11 | 0.002 | 0.037 | -0.17% | 0.16% | 107 | ✅ |
| 12 | 0.276 | -0.996 | 5.06% | -7.48% | 129 | ✅ |
| 13 | -0.387 | 0.926 | -8.09% | 13.34% | 81 | ✅ |
| 14 | 0.222 | -0.361 | 6.24% | -3.49% | 106 | ✅ |
| 15 | 0.045 | -0.225 | 0.74% | -2.04% | 108 | ✅ |
| 16 | 0.350 | -0.369 | 13.85% | -3.54% | 120 | ✅ |
| 17 | 0.059 | 0.027 | 1.37% | 0.09% | 112 | ✅ |
| 18 | 0.155 | 0.050 | 2.05% | 0.18% | 110 | ✅ |
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
| bollinger_std | 2.15 | 0.62 | 0.29 | 1.04 | 3.00 | ✅ |
| rsi_period | 14.00 | 0.00 | 0.00 | 14.00 | 14.00 | ✅ |
| macd_fast | 12.00 | 0.00 | 0.00 | 12.00 | 12.00 | ✅ |
| macd_slow | 31.48 | 9.89 | 0.31 | 20.00 | 48.00 | ⚠️ |
| macd_signal | 9.14 | 2.78 | 0.30 | 5.00 | 12.00 | ⚠️ |
| atr_period | 14.00 | 0.00 | 0.00 | 14.00 | 14.00 | ✅ |
| donchian_period | 20.00 | 0.00 | 0.00 | 20.00 | 20.00 | ✅ |
| adx_period | 11.95 | 2.92 | 0.24 | 7.00 | 17.00 | ✅ |

- **Stable Parameters:** 7/9
- **Stable:** bollinger_period, bollinger_std, rsi_period, macd_fast, atr_period, donchian_period, adx_period
- **Unstable:** macd_slow, macd_signal

---

## 5. A/B Test Results

| Metric | Baseline (Default) | Treatment (Bayesian) |
|--------|-------------------|---------------------|
| **Sharpe** | 0.145 | 0.139 |
| **Return** | 39.44% | 37.78% |
| **P-Value** | - | 0.3894 |
| **Significant** | - | False |
| **Recommendation** | - | **INCONCLUSIVE** |

---

## 6. Safety Limits

- **Windows with Violations:** 21/21
- **Violation Rate:** 100%
- **Circuit Breaker:** not_triggered

**Sample Violations:**
- bollinger_std: 2.0 -> 2.8771054180315008 (43.9% change exceeds 15% limit)
- macd_slow: 26 -> 20 (23.1% change exceeds 10% limit)
- macd_signal: 9 -> 12 (33.3% change exceeds 10% limit)
- macd_slow: 26 -> 23 (11.5% change exceeds 10% limit)
- macd_signal: 9 -> 8 (11.1% change exceeds 10% limit)

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

**Report saved to:** `reports/production_readiness_20260405_055905.md`
