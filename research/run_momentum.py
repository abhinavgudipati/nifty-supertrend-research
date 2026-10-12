"""
Momentum test on point-in-time Nifty 50 members: does picking the recent winners beat holding all members?

Each month-end t, among stocks that were index members on t, rank by past return
    close[t - skip months] / close[t - lookback months] - 1
and hold the top K equally weighted for the next month. Signal uses the close of t; the trade is
assumed at the close of the next trading day, so holdings earn returns from t+2 (no look-ahead).
A stock picked stays held until the next rebalance even if it leaves the index; if its prices stop
(delisting), it drops out and the rest are re-weighted. Each rebalance pays 0.1% per side on turnover.

Variants (lookback 6/12 months x skip 0/1 month x K 5/10/15) are ranked by 2010-2018 Sharpe;
the best is run unchanged on 2019 onward. Prices: NSE total-return series (build_nse_series.py).

Run (quant env):  python run_momentum.py
"""
import datetime as dt
import os

import numpy as np
import pandas as pd

import run_pit as rp
from run_pit import base

START, IS_END, OOS_START = rp.START, rp.IS_END, rp.OOS_START
COST = base.COST
GRID = [{"lookback": lb, "skip": sk, "k": k} for lb in (6, 12) for sk in (0, 1) for k in (5, 10, 15)]


def label(v):
    return f"top {v['k']}, {v['lookback']}m lookback" + (", skip last month" if v["skip"] else "")


def load():
    cal = base.prices("^NSEI", False).index  # trading calendar from 2009
    mask_days = cal[cal >= pd.Timestamp(START)]
    mask = rp.membership_mask(mask_days, os.path.join(base.DATA, rp.INDEXES["nifty50"][0]))
    close = pd.DataFrame({s: rp.nse_prices(s, "nse_tr")["Close"] for s in mask.columns
                          if len(rp.nse_prices(s, "nse_tr"))}).reindex(cal)
    return cal, mask, close


def run(v, cal, mask, close):
    rets = close.pct_change(fill_method=None)
    month_ends = pd.Series(cal, index=cal).groupby(cal.to_period("M")).last()
    month_ends = month_ends[month_ends >= pd.Timestamp(START)]
    port = pd.Series(np.nan, index=cal)
    held, log = [], []
    for j, t in enumerate(month_ends):
        # momentum at t: past return from t-lookback to t-skip (month-end closes, last valid price)
        def px_at(months_back):
            d = t - pd.DateOffset(months=months_back)
            return close.loc[:d].iloc[-1] if months_back else close.loc[t]
        members = mask.columns[mask.loc[t].to_numpy()] if t in mask.index else []
        mom = (px_at(v["skip"]) / px_at(v["lookback"]) - 1)[list(members)].dropna()
        new = list(mom.sort_values(ascending=False).index[: v["k"]])
        # holding window: from t+2 to the next month-end + 1 (inclusive)
        i0 = cal.get_loc(t) + 2
        nxt = month_ends.iloc[j + 1] if j + 1 < len(month_ends) else cal[-1]
        i1 = min(cal.get_loc(nxt) + 1, len(cal) - 1)
        if i0 > i1:
            continue
        window = cal[i0: i1 + 1]
        turnover = 2 * len(set(new) - set(held)) / v["k"] if held else 1.0
        r = rets.loc[window, new].mean(axis=1, skipna=True).fillna(0.0)
        r.iloc[0] -= COST * turnover
        port.loc[window] = r
        log.append({"rebalance": t.date(), "holdings": " ".join(new), "turnover": turnover})
        held = new
    return port.loc[START:].dropna(), pd.DataFrame(log)


def main():
    cal, mask, close = load()
    daily = pd.read_csv(os.path.join(base.RESULTS, "nifty50_nse_tr_pit_daily_returns.csv"),
                        index_col=0, parse_dates=True)  # strategy, buy_hold, index from run_pit nse_tr

    rows, cache = [], {}
    for v in GRID:
        p, log = run(v, cal, mask, close)
        cache[label(v)] = (p, log)
        st = rp.perf(p[:IS_END])
        rows.append({"variant": label(v), "IS CAGR": st["CAGR"], "IS Sharpe": st["Sharpe"], "IS MaxDD": st["MaxDD"],
                     "avg turnover": log["turnover"].mean()})
    sel = pd.DataFrame(rows).sort_values("IS Sharpe", ascending=False)
    chosen = sel.iloc[0]["variant"]
    mom, log = cache[chosen]

    idx = mom.index.intersection(daily.index)
    mom, bh, st_, nifty = mom.loc[idx], daily.loc[idx, "buy_hold"], daily.loc[idx, "strategy"], daily.loc[idx, "index"]

    table, tests = [], []
    for period, (lo, hi) in {"In-sample 2010-18": (START, IS_END), "Out-of-sample 2019-": (OOS_START, None)}.items():
        for name, r in [(f"Momentum ({chosen})", mom), ("Buy & hold all members", bh),
                        ("Triple Supertrend", st_), ("Nifty 50 price index", nifty)]:
            table.append({"Period": period, "Portfolio": name, **rp.perf(r[lo:hi])})
        a, b = mom[lo:hi], bh[lo:hi]
        obs, ci, p = rp.bootstrap_sharpe_diff(a, b)
        tests.append({"Period": period, "Mean daily excess (bp)": (a - b).mean() * 1e4, "Newey-West t": rp.nw_tstat(a - b),
                      "Sharpe diff": obs, "Sharpe diff 95% CI": f"[{ci[0]:.2f}, {ci[1]:.2f}]", "Bootstrap p": p})
    table, tests = pd.DataFrame(table), pd.DataFrame(tests)

    sel.to_csv(os.path.join(base.RESULTS, "nifty50_momentum_selection.csv"), index=False)
    table.to_csv(os.path.join(base.RESULTS, "nifty50_momentum_performance.csv"), index=False)
    tests.to_csv(os.path.join(base.RESULTS, "nifty50_momentum_tests.csv"), index=False)
    log.to_csv(os.path.join(base.RESULTS, "nifty50_momentum_holdings.csv"), index=False)
    pd.DataFrame({"momentum": mom, "buy_hold": bh, "supertrend": st_, "index": nifty}).to_csv(
        os.path.join(base.RESULTS, "nifty50_momentum_daily_returns.csv"))

    show = table.copy()
    for k, f in {"CAGR": "{:.1%}", "Vol": "{:.1%}", "Sharpe": "{:.2f}", "MaxDD": "{:.1%}"}.items():
        show[k] = show[k].map(f.format)
    sv = sel.copy()
    for k in ["IS CAGR", "IS MaxDD"]:
        sv[k] = sv[k].map("{:.1%}".format)
    lines = [
        "# Momentum on point-in-time Nifty 50 members", "",
        f"Generated {dt.date.today()}. NSE total-return prices. Monthly rebalance, signal at month-end close, "
        f"trade at next day's close, {COST:.1%} per side on turnover.", "",
        "## 1. In-sample selection (2010-2018, by Sharpe)", "", sv.to_markdown(index=False, floatfmt=".2f"), "",
        f"**Chosen: {chosen}**", "", "## 2. Performance", "", show.to_markdown(index=False), "",
        "## 3. Momentum minus buy & hold (all members)", "", tests.to_markdown(index=False, floatfmt=".3f"), "",
        f"Average monthly turnover of chosen variant: {log['turnover'].mean():.0%} of the portfolio.",
    ]
    with open(os.path.join(base.RESULTS, "nifty50_momentum_summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
