# SIQE Production Readiness Report

**Generated:** 2026-04-05T10:13:01.395514+00:00
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
- **Missing Values:** {'high': 0, 'low': 0, 'open': 0, 'close': 0}
- **Price Anomalies:** []
- **Volume Stats:** {'mean': 30498.94770165746, 'median': 25041.797, 'min': 3902.732, 'max': 98820.429, 'zero_count': 0}
- **Warnings:** []

---

## 2. Walk-Forward Validation (15m)

| Metric | Value |
|--------|-------|
| **Passed** | False |
| **Windows** | 21 |
| **Avg Test Sharpe** | 0.258 |
| **Avg Test Return** | 1.37% |
| **Avg Test Drawdown** | -2.69% |
| **Pass Rate** | 100% |
| **Min Test Sharpe** | -0.998 |
| **Max Test Sharpe** | 1.507 |
| **Total Test Trades** | 4733 |

### Per-Window Results

| Window | Train Sharpe | Test Sharpe | Train Return | Test Return | Trades | Passed |
|--------|-------------|-------------|--------------|-------------|--------|--------|
| 0 | -0.386 | -0.098 | -3.36% | -0.45% | 234 | ✅ |
| 1 | 0.257 | 1.367 | 4.41% | 7.83% | 230 | ✅ |
| 2 | 0.795 | 1.507 | 13.29% | 9.62% | 232 | ✅ |
| 3 | 0.908 | 0.416 | 16.52% | 1.38% | 246 | ✅ |
| 4 | 0.768 | -0.421 | 7.65% | -1.17% | 211 | ✅ |
| 5 | 0.310 | 0.137 | 3.79% | 0.56% | 197 | ✅ |
| 6 | 0.402 | 0.400 | 7.36% | 1.94% | 219 | ✅ |
| 7 | -0.139 | -0.472 | -2.35% | -3.38% | 223 | ✅ |
| 8 | 0.001 | 0.023 | -0.19% | 0.05% | 220 | ✅ |
| 9 | -0.438 | 1.029 | -7.80% | 3.37% | 224 | ✅ |
| 10 | -0.288 | -0.300 | -4.67% | -1.39% | 216 | ✅ |
| 11 | 0.112 | 0.518 | 1.21% | 2.01% | 225 | ✅ |
| 12 | 0.372 | -0.998 | 4.85% | -3.85% | 215 | ✅ |
| 13 | -0.299 | 0.483 | -4.00% | 4.45% | 243 | ✅ |
| 14 | 0.268 | -0.049 | 5.49% | -0.24% | 225 | ✅ |
| 15 | 0.232 | -0.577 | 4.16% | -2.99% | 236 | ✅ |
| 16 | 0.250 | 0.688 | 6.74% | 3.74% | 238 | ✅ |
| 17 | 0.132 | 0.946 | 2.20% | 3.19% | 231 | ✅ |
| 18 | -0.221 | -0.087 | -2.78% | -0.23% | 228 | ✅ |
| 19 | 0.247 | 0.723 | 3.02% | 3.61% | 211 | ✅ |
| 20 | 0.837 | 0.184 | 17.36% | 0.73% | 229 | ✅ |

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
| bollinger_std | 1.86 | 0.16 | 0.08 | 1.71 | 2.19 | ✅ |
| rsi_period | 14.00 | 0.00 | 0.00 | 14.00 | 14.00 | ✅ |
| macd_fast | 12.00 | 0.00 | 0.00 | 12.00 | 12.00 | ✅ |
| macd_slow | 26.10 | 1.34 | 0.05 | 24.00 | 28.00 | ✅ |
| macd_signal | 8.86 | 0.56 | 0.06 | 8.00 | 10.00 | ✅ |
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

- **Windows with Violations:** 7/21
- **Violation Rate:** 33%
- **Circuit Breaker:** not_triggered

**Sample Violations:**
- macd_signal: 9 -> 8 (11.1% change exceeds 10% limit)
- macd_signal: 9 -> 8 (11.1% change exceeds 10% limit)
- macd_signal: 9 -> 8 (11.1% change exceeds 10% limit)
- macd_signal: 9 -> 10 (11.1% change exceeds 10% limit)
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

**Report saved to:** `reports/production_readiness_20260405_101301.md`
