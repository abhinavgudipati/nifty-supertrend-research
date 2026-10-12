# Triple Supertrend on Nifty 50: in-sample / out-of-sample

Generated 2026-10-12. Long-only, signals at close, fills at next open, 0.1% cost per side. In-sample 2010-01-01 to 2018-12-31; out-of-sample from 2019-01-01.

## 1. In-sample variant selection (stocks, median across stocks)

| variant                         |   median_sharpe |   median_cagr |   median_bh_cagr |   stocks |
|:--------------------------------|----------------:|--------------:|-----------------:|---------:|
| exit ST(12, 3)                  |           0.247 |         0.029 |            0.120 |       47 |
| exit ST(11, 2) + 200d MA filter |           0.214 |         0.023 |            0.120 |       47 |
| exit ST(12, 3) + 200d MA filter |           0.198 |         0.019 |            0.120 |       47 |
| exit ST(11, 2)                  |           0.197 |         0.019 |            0.120 |       47 |
| exit ST(10, 1) + 200d MA filter |           0.115 |         0.005 |            0.120 |       47 |
| exit ST(10, 1)                  |           0.070 |        -0.002 |            0.120 |       47 |

**Chosen variant: exit ST(12, 3)** (highest in-sample median Sharpe).

## 2. Out-of-sample results for the chosen variant

| | In-sample | Out-of-sample |
|---|---|---|
| Stocks tested | 47 | 50 |
| Median CAGR difference vs buy & hold | -8.6% | -7.2% |
| Share of stocks beating B&H on CAGR | 8.5% | 10.0% |
| Median Sharpe difference vs B&H | -0.27 | -0.19 |
| Share of stocks beating B&H on Sharpe | 10.6% | 24.0% |
| t-test p-value (CAGR diff = 0) | 0.000 | 0.000 |
| Wilcoxon p-value (CAGR diff = 0) | 0.000 | 0.000 |
| t-test p-value (Sharpe diff = 0) | 0.000 | 0.000 |

### Indices (out-of-sample)

| symbol   |   strat_cagr |   bh_cagr |   strat_sharpe |   bh_sharpe |   strat_maxdd |   bh_maxdd |   trades |
|:---------|-------------:|----------:|---------------:|------------:|--------------:|-----------:|---------:|
| ^NSEI    |        0.047 |     0.098 |          0.503 |       0.634 |        -0.221 |     -0.384 |       31 |
| ^NSEBANK |        0.013 |     0.093 |          0.164 |       0.506 |        -0.275 |     -0.479 |       32 |

## Known limitations (to fix in later steps)

- **Survivorship bias:** universe is today's Nifty 50 applied backwards; firms that left the index are missing. That likely flatters buy & hold more than the strategy, which exits falling stocks.
- Stocks are treated as independent in the p-values, but they are correlated; a block bootstrap is needed.
- Flat cost assumption; no STT/stamp-duty breakdown or cost sensitivity yet.
- Yahoo adjusted prices; no cross-check against NSE bhavcopy.