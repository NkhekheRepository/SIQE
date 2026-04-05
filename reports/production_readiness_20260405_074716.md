# SIQE Production Readiness Report

**Generated:** 2026-04-05T07:47:16.155171+00:00
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
| Safety Limits | 38% violation rate |

---

## 1. Data Quality

- **Rows:** 181
- **Date Range:** ('2026-03-05 00:00:00', '2026-04-04 00:00:00')
- **Missing Values:** {'low': 0, 'close': 0, 'high': 0, 'open': 0}
- **Price Anomalies:** []
- **Volume Stats:** {'mean': 30498.94770165746, 'median': 25041.797, 'min': 3902.732, 'max': 98820.429, 'zero_count': 0}
- **Warnings:** []

---

## 2. Walk-Forward Validation (15m)

| Metric | Value |
|--------|-------|
| **Passed** | False |
| **Windows** | 21 |
| **Avg Test Sharpe** | 0.301 |
| **Avg Test Return** | 1.34% |
| **Avg Test Drawdown** | -2.18% |
| **Pass Rate** | 100% |
| **Min Test Sharpe** | -0.952 |
| **Max Test Sharpe** | 1.468 |
| **Total Test Trades** | 3786 |

### Per-Window Results

| Window | Train Sharpe | Test Sharpe | Train Return | Test Return | Trades | Passed |
|--------|-------------|-------------|--------------|-------------|--------|--------|
| 0 | -0.193 | -0.198 | -1.61% | -0.72% | 109 | ✅ |
| 1 | 0.015 | 1.276 | 0.10% | 7.21% | 219 | ✅ |
| 2 | 0.752 | 1.468 | 12.47% | 7.86% | 131 | ✅ |
| 3 | 0.749 | 0.406 | 11.41% | 1.12% | 183 | ✅ |
| 4 | 0.642 | -0.421 | 5.24% | -1.17% | 211 | ✅ |
| 5 | 0.390 | 0.146 | 4.70% | 0.60% | 190 | ✅ |
| 6 | 0.420 | 0.461 | 7.68% | 1.42% | 133 | ✅ |
| 7 | -0.244 | -0.472 | -2.70% | -3.38% | 223 | ✅ |
| 8 | -0.016 | 0.023 | -0.50% | 0.05% | 220 | ✅ |
| 9 | -0.457 | 1.029 | -8.12% | 3.37% | 224 | ✅ |
| 10 | -0.288 | 0.440 | -4.67% | 1.53% | 103 | ✅ |
| 11 | 0.011 | 0.602 | 0.05% | 2.30% | 205 | ✅ |
| 12 | 0.258 | -0.952 | 2.18% | -3.67% | 212 | ✅ |
| 13 | -0.285 | 0.562 | -3.81% | 5.14% | 207 | ✅ |
| 14 | 0.542 | -0.051 | 11.22% | -0.19% | 126 | ✅ |
| 15 | 0.451 | -0.530 | 7.77% | -2.75% | 235 | ✅ |
| 16 | 0.267 | 0.687 | 7.24% | 3.02% | 146 | ✅ |
| 17 | 0.036 | 0.707 | 0.39% | 1.07% | 108 | ✅ |
| 18 | 0.139 | -0.087 | 1.14% | -0.23% | 228 | ✅ |
| 19 | 0.314 | 1.043 | 3.50% | 4.96% | 150 | ✅ |
| 20 | 0.681 | 0.183 | 8.26% | 0.73% | 223 | ✅ |

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
| bollinger_std | 1.87 | 0.16 | 0.09 | 1.71 | 2.24 | ✅ |
| rsi_period | 14.00 | 0.00 | 0.00 | 14.00 | 14.00 | ✅ |
| macd_fast | 12.00 | 0.00 | 0.00 | 12.00 | 12.00 | ✅ |
| macd_slow | 26.10 | 1.34 | 0.05 | 24.00 | 28.00 | ✅ |
| macd_signal | 8.90 | 0.61 | 0.07 | 8.00 | 10.00 | ✅ |
| atr_period | 14.00 | 0.00 | 0.00 | 14.00 | 14.00 | ✅ |
| donchian_period | 20.00 | 0.00 | 0.00 | 20.00 | 20.00 | ✅ |
| adx_period | 14.33 | 0.47 | 0.03 | 14.00 | 15.00 | ✅ |

- **Stable Parameters:** 9/9
- **Stable:** bollinger_period, bollinger_std, rsi_period, macd_fast, macd_slow, macd_signal, atr_period, donchian_period, adx_period
- **Unstable:** 

---

## 5. A/B Test Results

| Metric | Baseline (Default) | Treatment (Bayesian) |
|--------|-------------------|---------------------|
| **Sharpe** | 0.145 | 0.144 |
| **Return** | 39.44% | 39.31% |
| **P-Value** | - | 0.8262 |
| **Significant** | - | False |
| **Recommendation** | - | **INCONCLUSIVE** |

---

## 6. Safety Limits

- **Windows with Violations:** 8/21
- **Violation Rate:** 38%
- **Circuit Breaker:** not_triggered

**Sample Violations:**
- macd_signal: 9 -> 8 (11.1% change exceeds 10% limit)
- macd_signal: 9 -> 8 (11.1% change exceeds 10% limit)
- macd_signal: 9 -> 8 (11.1% change exceeds 10% limit)
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

**Report saved to:** `reports/production_readiness_20260405_074716.md`
