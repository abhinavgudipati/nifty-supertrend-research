# Triple Supertrend on Nifty 50: point-in-time (survivorship-free) test

Generated 2026-10-12. Long-only, signals at close, fills at next open, 0.1% per side. Equal-weight portfolio of the stocks that were Nifty 50 members on each day, rebalanced daily.

## Data coverage

- Membership file: nifty50_membership_2010_2026.csv (98 distinct stocks over the period).
- Member-days with price data: **95.3%** (196,635 of 206,369).
- No price data for: CAIRN (1525 member-days), HDFC (3331 member-days), JPASSOCIAT (1039 member-days), RANBAXYLAB (1039 member-days), RELCAPITAL (439 member-days), STERLITE (674 member-days), TATAMTRDVR (369 member-days).
- Partially missing (no price on some member-days, e.g. not yet listed): IDFCFIRSTB (1318).
- One-day moves > 35% during membership (check for unadjusted corporate actions): INDUSINDBK 2020-03-26 +45%, YESBANK 2020-03-06 -56%, YESBANK 2020-03-11 +36%, YESBANK 2020-03-16 +45%, YESBANK 2020-03-17 +58%.

## 1. In-sample variant selection (portfolio Sharpe, 2010-2018)

| variant                         |   IS CAGR |   IS Sharpe |   IS MaxDD |
|:--------------------------------|----------:|------------:|-----------:|
| exit ST(11, 2)                  |     0.023 |       0.366 |     -0.156 |
| exit ST(11, 2) + 200d MA filter |     0.018 |       0.360 |     -0.119 |
| exit ST(12, 3) + 200d MA filter |     0.020 |       0.329 |     -0.145 |
| exit ST(12, 3)                  |     0.023 |       0.313 |     -0.194 |
| exit ST(10, 1)                  |     0.004 |       0.108 |     -0.129 |
| exit ST(10, 1) + 200d MA filter |     0.001 |       0.049 |     -0.112 |

**Chosen: exit ST(11, 2)**

## 2. Performance

| Period              | Portfolio                | CAGR   | Vol   |   Sharpe | MaxDD   |   Days |
|:--------------------|:-------------------------|:-------|:------|---------:|:--------|-------:|
| In-sample 2010-18   | Strategy (PIT members)   | 2.3%   | 6.8%  |     0.37 | -15.6%  |   2202 |
| In-sample 2010-18   | Buy & hold (PIT members) | 9.0%   | 16.2% |     0.61 | -28.8%  |   2202 |
| In-sample 2010-18   | Nifty 50 index           | 8.8%   | 15.6% |     0.62 | -27.9%  |   2202 |
| Out-of-sample 2019- | Strategy (PIT members)   | 6.1%   | 7.0%  |     0.88 | -12.4%  |   1918 |
| Out-of-sample 2019- | Buy & hold (PIT members) | 14.8%  | 17.4% |     0.88 | -39.2%  |   1918 |
| Out-of-sample 2019- | Nifty 50 index           | 10.0%  | 17.3% |     0.64 | -38.4%  |   1918 |

## 3. Is the difference real? (strategy minus buy & hold, daily)

| Period        |   Mean daily excess (bp) |   Newey-West t |   Sharpe diff | Sharpe diff 95% CI   |   Bootstrap p |
|:--------------|-------------------------:|---------------:|--------------:|:---------------------|--------------:|
| In-sample     |                   -2.939 |         -1.856 |        -0.247 | [-0.67, 0.15]        |         0.220 |
| Out-of-sample |                   -3.657 |         -1.794 |         0.000 | [-0.66, 0.66]        |         0.877 |

Newey-West t uses 10 lags. Bootstrap: circular blocks of 20 days, 2000 resamples, two-sided p.

## 4. Survivorship bias: point-in-time vs today's constituents

| Universe                | Period   | Strategy CAGR   | B&H CAGR   | Gap    |   Strategy Sharpe |   B&H Sharpe |
|:------------------------|:---------|:----------------|:-----------|:-------|------------------:|-------------:|
| Point-in-time members   | IS       | 2.3%            | 9.0%       | -6.7%  |              0.37 |         0.61 |
| Point-in-time members   | OOS      | 6.1%            | 14.8%      | -8.8%  |              0.88 |         0.88 |
| Today's members, back-filled | IS       | 5.8%            | 18.5%      | -12.7% |              0.88 |         1.21 |
| Today's members, back-filled | OOS      | 8.7%            | 21.9%      | -13.1% |              1.20 |         1.21 |

## Limitations

- Missing price history for the stocks listed above (mostly delisted or merged), so part of the survivorship effect remains.
- Daily equal-weight rebalancing is not cost-charged; only strategy entries/exits pay costs.
- When a stock leaves the index mid-trade, its return simply stops counting (no exit cost charged).
- Membership before the first change in the file (2010-04-08) is inferred by reversing that change.