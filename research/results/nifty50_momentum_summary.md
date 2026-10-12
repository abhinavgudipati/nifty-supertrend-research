# Momentum on point-in-time Nifty 50 members

Generated 2026-10-12. NSE total-return prices. Monthly rebalance, signal at month-end close, trade at next day's close, 0.1% per side on turnover.

## 1. In-sample selection (2010-2018, by Sharpe)

| variant                               | IS CAGR   |   IS Sharpe | IS MaxDD   |   avg turnover |
|:--------------------------------------|:----------|------------:|:-----------|---------------:|
| top 10, 12m lookback                  | 13.9%     |        0.84 | -20.4%     |           0.49 |
| top 15, 12m lookback, skip last month | 13.6%     |        0.84 | -19.3%     |           0.42 |
| top 10, 12m lookback, skip last month | 13.9%     |        0.83 | -22.1%     |           0.49 |
| top 15, 12m lookback                  | 13.2%     |        0.83 | -19.5%     |           0.39 |
| top 5, 12m lookback                   | 15.2%     |        0.82 | -27.2%     |           0.62 |
| top 5, 12m lookback, skip last month  | 13.6%     |        0.73 | -27.7%     |           0.63 |
| top 15, 6m lookback                   | 8.4%      |        0.57 | -21.2%     |           0.57 |
| top 10, 6m lookback                   | 7.9%      |        0.52 | -23.6%     |           0.71 |
| top 15, 6m lookback, skip last month  | 7.4%      |        0.50 | -26.6%     |           0.65 |
| top 10, 6m lookback, skip last month  | 7.0%      |        0.47 | -26.0%     |           0.77 |
| top 5, 6m lookback                    | 4.2%      |        0.31 | -31.8%     |           0.89 |
| top 5, 6m lookback, skip last month   | 2.9%      |        0.24 | -40.5%     |           0.93 |

**Chosen: top 10, 12m lookback**

## 2. Performance

| Period              | Portfolio                       | CAGR   | Vol   |   Sharpe | MaxDD   |   Days |
|:--------------------|:--------------------------------|:-------|:------|---------:|:--------|-------:|
| In-sample 2010-18   | Momentum (top 10, 12m lookback) | 13.9%  | 17.3% |     0.84 | -20.4%  |   2182 |
| In-sample 2010-18   | Buy & hold all members          | 9.4%   | 16.5% |     0.63 | -28.5%  |   2182 |
| In-sample 2010-18   | Triple Supertrend               | 2.8%   | 8.3%  |     0.37 | -19.4%  |   2182 |
| In-sample 2010-18   | Nifty 50 price index            | 9.6%   | 15.6% |     0.67 | -27.9%  |   2182 |
| Out-of-sample 2019- | Momentum (top 10, 12m lookback) | 9.3%   | 20.3% |     0.54 | -36.9%  |   1918 |
| Out-of-sample 2019- | Buy & hold all members          | 15.1%  | 17.4% |     0.9  | -38.6%  |   1918 |
| Out-of-sample 2019- | Triple Supertrend               | 8.0%   | 8.5%  |     0.96 | -12.1%  |   1918 |
| Out-of-sample 2019- | Nifty 50 price index            | 10.0%  | 17.3% |     0.64 | -38.4%  |   1918 |

## 3. Momentum minus buy & hold (all members)

| Period              |   Mean daily excess (bp) |   Newey-West t |   Sharpe diff | Sharpe diff 95% CI   |   Bootstrap p |
|:--------------------|-------------------------:|---------------:|--------------:|:---------------------|--------------:|
| In-sample 2010-18   |                    1.680 |          1.154 |         0.217 | [-0.21, 0.62]        |         0.305 |
| Out-of-sample 2019- |                   -1.839 |         -1.264 |        -0.357 | [-0.79, 0.05]        |         0.089 |

Average monthly turnover of chosen variant: 49% of the portfolio.