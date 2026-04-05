# SIQE Production Readiness Report

**Generated:** 2026-04-05T06:56:44.101919+00:00
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
- **Missing Values:** {'high': 0, 'close': 0, 'low': 0, 'open': 0}
- **Price Anomalies:** []
- **Volume Stats:** {'mean': 30498.94770165746, 'median': 25041.797, 'min': 3902.732, 'max': 98820.429, 'zero_count': 0}
- **Warnings:** []

---

## 2. Walk-Forward Validation (15m)

| Metric | Value |
|--------|-------|
| **Passed** | False |
| **Windows** | 21 |
| **Avg Test Sharpe** | 0.273 |
| **Avg Test Return** | 1.41% |
| **Avg Test Drawdown** | -2.61% |
| **Pass Rate** | 100% |
| **Min Test Sharpe** | -0.952 |
| **Max Test Sharpe** | 1.501 |
| **Total Test Trades** | 4633 |

### Per-Window Results

| Window | Train Sharpe | Test Sharpe | Train Return | Test Return | Trades | Passed |
|--------|-------------|-------------|--------------|-------------|--------|--------|
| 0 | -0.193 | -0.141 | -1.61% | -0.63% | 232 | ✅ |
| 1 | 0.277 | 1.276 | 4.76% | 7.21% | 219 | ✅ |
| 2 | 0.752 | 1.501 | 12.47% | 9.53% | 225 | ✅ |
| 3 | 0.859 | 0.690 | 15.47% | 2.09% | 231 | ✅ |
| 4 | 0.691 | -0.421 | 6.12% | -1.17% | 211 | ✅ |
| 5 | 0.390 | 0.146 | 4.70% | 0.60% | 190 | ✅ |
| 6 | 0.420 | 0.400 | 7.68% | 1.94% | 219 | ✅ |
| 7 | -0.137 | -0.472 | -2.33% | -3.38% | 223 | ✅ |
| 8 | -0.016 | 0.023 | -0.50% | 0.05% | 220 | ✅ |
| 9 | -0.457 | 1.029 | -8.12% | 3.37% | 224 | ✅ |
| 10 | -0.288 | -0.276 | -4.67% | -1.28% | 215 | ✅ |
| 11 | 0.122 | 0.493 | 1.32% | 1.90% | 218 | ✅ |
| 12 | 0.374 | -0.952 | 4.86% | -3.67% | 212 | ✅ |
| 13 | -0.285 | 0.494 | -3.81% | 4.57% | 226 | ✅ |
| 14 | 0.285 | -0.040 | 5.86% | -0.20% | 220 | ✅ |
| 15 | 0.316 | -0.530 | 5.74% | -2.75% | 235 | ✅ |
| 16 | 0.267 | 0.757 | 7.24% | 4.09% | 228 | ✅ |
| 17 | 0.164 | 0.870 | 2.77% | 2.86% | 228 | ✅ |
| 18 | -0.101 | -0.087 | -1.22% | -0.23% | 228 | ✅ |
| 19 | 0.314 | 0.795 | 3.50% | 3.93% | 206 | ✅ |
| 20 | 0.848 | 0.183 | 17.51% | 0.73% | 223 | ✅ |

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
| bollinger_std | 1.89 | 0.18 | 0.10 | 1.71 | 2.30 | ✅ |
| rsi_period | 14.00 | 0.00 | 0.00 | 14.00 | 14.00 | ✅ |
| macd_fast | 12.00 | 0.00 | 0.00 | 12.00 | 12.00 | ✅ |
| macd_slow | 26.10 | 1.34 | 0.05 | 24.00 | 28.00 | ✅ |
| macd_signal | 8.90 | 0.61 | 0.07 | 8.00 | 10.00 | ✅ |
| atr_period | 14.00 | 0.00 | 0.00 | 14.00 | 14.00 | ✅ |
| donchian_period | 20.00 | 0.00 | 0.00 | 20.00 | 20.00 | ✅ |
| adx_period | 14.38 | 0.49 | 0.03 | 14.00 | 15.00 | ✅ |

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

**Report saved to:** `reports/production_readiness_20260405_065644.md`
