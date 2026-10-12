# Triple Supertrend on Nifty 50: point-in-time (survivorship-free) test

Generated 2026-10-12. Prices: NSE bhavcopy, split/bonus/demerger-adjusted, dividends not included. Long-only, signals at close, fills at next open, {base.COST:.1%} per side. Equal-weight portfolio of the stocks that were Nifty 50 members on each day, rebalanced daily.

## Data coverage

- Membership file: nifty50_membership_2010_2026.csv (98 distinct stocks over the period).
- Member-days with price data: **99.3%** (204,989 of 206,369).
- No price data for: none.
- Partially missing (no price on some member-days, e.g. not yet listed): IDFCFIRSTB (1318), HDFC (12), HDFCBANK (1), HCLTECH (1), APOLLOHOSP (1), ADANIPORTS (1), BAJAJ-AUTO (1), AXISBANK (1), BAJFINANCE (1), ASIANPAINT (1), BEL (1), BHARTIARTL (1), GRASIM (1), ETERNAL (1), CIPLA (1), DRREDDY (1), BSE (1), BAJAJFINSV (1), EICHERMOT (1), COALINDIA (1), HDFCLIFE (1), M&M (1), MAXHEALTH (1), MARUTI (1), NTPC (1), NESTLEIND (1), INFY (1), ITC (1), JIOFIN (1), INDIGO (1), HINDUNILVR (1), ICICIBANK (1), HINDALCO (1), ADANIENT (1), ONGC (1), POWERGRID (1), TATACONSUM (1), TITAN (1), TMPV (1), TRENT (1), ULTRACEMCO (1), TECHM (1), TCS (1), TATASTEEL (1), SBIN (1), SUNPHARMA (1), SHRIRAMFIN (1), LT (1), KOTAKBANK (1), JSWSTEEL (1), RELIANCE (1), SBILIFE (1).
- One-day moves > 35% during membership (check for unadjusted corporate actions): INDUSINDBK 2020-03-26 +45%, TATAMOTORS 2019-10-29 +36%, YESBANK 2020-03-06 -56%, YESBANK 2020-03-11 +36%, YESBANK 2020-03-16 +45%, YESBANK 2020-03-17 +58%.

## 1. In-sample variant selection (portfolio Sharpe, 2010-2018)

| variant                         |   IS CAGR |   IS Sharpe |   IS MaxDD |
|:--------------------------------|----------:|------------:|-----------:|
| exit ST(12, 3)                  |     0.014 |       0.210 |     -0.196 |
| exit ST(12, 3) + 200d MA filter |     0.010 |       0.184 |     -0.162 |
| exit ST(11, 2)                  |     0.009 |       0.166 |     -0.163 |
| exit ST(11, 2) + 200d MA filter |     0.006 |       0.137 |     -0.147 |
| exit ST(10, 1)                  |    -0.007 |      -0.109 |     -0.138 |
| exit ST(10, 1) + 200d MA filter |    -0.007 |      -0.157 |     -0.132 |

**Chosen: exit ST(12, 3)**

## 2. Performance

| Period              | Portfolio                | CAGR   | Vol   |   Sharpe | MaxDD   |   Days |
|:--------------------|:-------------------------|:-------|:------|---------:|:--------|-------:|
| In-sample 2010-18   | Strategy (PIT members)   | 1.4%   | 8.3%  |     0.21 | -19.6%  |   2202 |
| In-sample 2010-18   | Buy & hold (PIT members) | 7.0%   | 16.5% |     0.49 | -29.4%  |   2202 |
| In-sample 2010-18   | Nifty 50 index           | 8.8%   | 15.6% |     0.62 | -27.9%  |   2202 |
| Out-of-sample 2019- | Strategy (PIT members)   | 6.7%   | 8.4%  |     0.81 | -12.7%  |   1918 |
| Out-of-sample 2019- | Buy & hold (PIT members) | 13.1%  | 17.4% |     0.79 | -39.8%  |   1918 |
| Out-of-sample 2019- | Nifty 50 index           | 10.0%  | 17.3% |     0.64 | -38.4%  |   1918 |

## 3. Is the difference real? (strategy minus buy & hold, daily)

| Period        |   Mean daily excess (bp) |   Newey-West t |   Sharpe diff | Sharpe diff 95% CI   |   Bootstrap p |
|:--------------|-------------------------:|---------------:|--------------:|:---------------------|--------------:|
| In-sample     |                   -2.540 |         -1.773 |        -0.284 | [-0.65, 0.06]        |         0.102 |
| Out-of-sample |                   -2.801 |         -1.463 |         0.016 | [-0.56, 0.63]        |         0.916 |

Newey-West t uses 10 lags. Bootstrap: circular blocks of 20 days, 2000 resamples, two-sided p.

## 4. Survivorship bias: point-in-time vs today's constituents

| Universe                     | Period   | Strategy CAGR   | B&H CAGR   | Gap    |   Strategy Sharpe |   B&H Sharpe |
|:-----------------------------|:---------|:----------------|:-----------|:-------|------------------:|-------------:|
| Point-in-time members        | IS       | 1.4%            | 7.0%       | -5.6%  |              0.21 |         0.49 |
| Point-in-time members        | OOS      | 6.7%            | 13.1%      | -6.5%  |              0.81 |         0.79 |
| Today's members, back-filled | IS       | 6.5%            | 17.1%      | -10.6% |              0.82 |         1.13 |
| Today's members, back-filled | OOS      | 10.8%           | 20.4%      | -9.6%  |              1.21 |         1.14 |

## Limitations

- Missing price history for the stocks listed above (mostly delisted or merged), so part of the survivorship effect remains.
- Daily equal-weight rebalancing is not cost-charged; only strategy entries/exits pay costs.
- When a stock leaves the index mid-trade, its return simply stops counting (no exit cost charged).
- Membership before the first change in the file (2010-04-08) is inferred by reversing that change.