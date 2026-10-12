"""
Step 2: survivorship-bias-free test using point-in-time Nifty 50 membership (2010-2026).

Each day, the "universe" is exactly the stocks that were in the Nifty 50 on that day.
Two equal-weight portfolios are compared, rebalanced daily across those members:
  - Strategy : each member's Triple Supertrend (long-only) daily return, costs included
  - Buy & hold: each member's plain daily return
The strategy signals use each stock's full price history (only past data at each date).

  In-sample  2010-01-01 .. 2018-12-31 -> choose ONE variant (best portfolio Sharpe)
  Out-of-sample 2019-01-01 .. latest  -> report that variant untouched

Also re-runs the same thing on TODAY's constituents to measure the survivorship bias.

Run (quant env):  python run_pit.py [--refresh]
"""
import argparse
import datetime as dt
import os

import numpy as np
import pandas as pd

import run_split as base  # data paths, price cache, grid, cost, constituents
from run_split import backtest

# index -> (membership file, Yahoo benchmark, display name)
INDEXES = {
    "nifty50": ("nifty50_membership_2010_2026.csv", "^NSEI", "Nifty 50"),
    "nifty100": ("nifty100_membership_2010_2026.csv", "^CNX100", "Nifty 100"),
    "nifty200": ("nifty200_membership_2010_2026.csv", "^CNX200", "Nifty 200"),
    "nifty500": ("nifty500_membership_2010_2026.csv", "^CRSLDX", "Nifty 500"),
}
START, IS_END, OOS_START = "2010-01-01", "2018-12-31", "2019-01-01"

# NSE symbol in the membership file -> Yahoo symbol, where they differ
YAHOO = {"TATAMOTORS": "TMPV.NS"}  # Tata Motors kept its price history under the renamed PV entity
# corporate actions Yahoo leaves unadjusted: (yahoo symbol, ex-date) -> that day's return is
# treated as zero by scaling all earlier prices (holders received the demerged shares)
UNADJUSTED = [("TMPV.NS", "2025-10-14")]  # Tata Motors CV demerger
SPIKE = 0.35  # flag any one-day move bigger than this inside a membership window
BLOCK, N_BOOT = 20, 2000  # block bootstrap: 20-day blocks, 2000 resamples


# ---------- membership ----------
def read_membership(path):
    return pd.read_csv(path, parse_dates=["effective_date"]).sort_values("effective_date")


def membership_mask(index, path):
    """DataFrame[date x NSE symbol] = True when the stock was an index member that day."""
    m = read_membership(path)
    sets = [set(s.split(",")) for s in m["symbols"]]
    # before the first change: undo its inclusions/exclusions
    first = m.iloc[0]
    pre = (sets[0] - set(str(first["inclusions"]).split(","))) | set(str(first["exclusions"]).split(","))
    starts = [pd.Timestamp(START)] + list(m["effective_date"])
    members = [pre] + sets
    syms = sorted(set().union(*members) - {"nan"})
    mask = pd.DataFrame(False, index=index, columns=syms)
    for i, (s, mem) in enumerate(zip(starts, members)):
        e = starts[i + 1] if i + 1 < len(starts) else index[-1] + pd.Timedelta(days=1)
        rows = (index >= s) & (index < e)
        mask.loc[rows, [x for x in mem if x in mask.columns]] = True
    return mask


def prefetch(ysyms, refresh, chunk=80):
    """Bulk-download prices not yet cached (one request per chunk instead of per stock)."""
    path = lambda s: os.path.join(base.PRICES, s.replace("^", "IDX_") + ".csv")
    todo = [s for s in ysyms if refresh or not os.path.exists(path(s))]
    for i in range(0, len(todo), chunk):
        part = todo[i:i + chunk]
        print(f"  downloading {i + len(part)}/{len(todo)}", flush=True)
        raw = base.scan.yf.download(part, start=base.DOWNLOAD_FROM, auto_adjust=True, progress=False,
                                    group_by="ticker", threads=True)
        for s in part:
            try:
                df = raw[s][["Open", "High", "Low", "Close"]].dropna()
            except KeyError:
                df = pd.DataFrame(columns=["Open", "High", "Low", "Close"])
            df.to_csv(path(s))


def adjusted_prices(ysym, refresh):
    px = base.prices(ysym, refresh)
    for s, d in UNADJUSTED:
        if s == ysym and pd.Timestamp(d) in px.index:
            i = px.index.get_loc(pd.Timestamp(d))
            factor = px["Close"].iloc[i] / px["Close"].iloc[i - 1]
            px.iloc[:i, px.columns.get_indexer(["Open", "High", "Low", "Close"])] *= factor
    return px


# ---------- portfolio ----------
def daily_returns(data, variant):
    """Per-stock daily returns (strategy, buy & hold) as two date x symbol frames."""
    backtest.STRATEGY, backtest.ALLOW_SHORT, backtest.COST_PER_SIDE = "supertrend", False, base.COST
    backtest.EXIT_FILTER, backtest.TREND_MA = variant["exit"], variant["trend_ma"]
    strat, bh = {}, {}
    for sym, px in data.items():
        df, _ = backtest.backtest(px.copy())
        strat[sym] = df["equity"].pct_change()
        bh[sym] = df["Close"].pct_change()
    return pd.DataFrame(strat), pd.DataFrame(bh)


def portfolio(rets, mask):
    """Equal-weight across members that have a return that day."""
    r = rets.reindex(index=mask.index, columns=mask.columns)
    r = r.where(mask)
    return r.mean(axis=1, skipna=True).fillna(0.0)


def perf(r):
    r = r.dropna()
    years = len(r) / 252
    eq = (1 + r).cumprod()
    return {"CAGR": eq.iloc[-1] ** (1 / years) - 1, "Vol": r.std() * np.sqrt(252),
            "Sharpe": r.mean() / r.std() * np.sqrt(252), "MaxDD": (eq / eq.cummax() - 1).min(),
            "Days": len(r)}


def nw_tstat(diff, lags=10):
    """t-stat of the mean daily difference, robust to autocorrelation (Newey-West)."""
    x = np.asarray(diff)
    d = x - x.mean()
    n = len(d)
    var = d @ d / n
    for k in range(1, lags + 1):
        var += 2 * (1 - k / (lags + 1)) * (d[k:] @ d[:-k]) / n
    return x.mean() / np.sqrt(var / n)


def bootstrap_sharpe_diff(a, b, seed=0):
    """Circular block bootstrap of Sharpe(a) - Sharpe(b); returns (diff, 95% CI, p-value of diff >= 0)."""
    rng = np.random.default_rng(seed)
    a, b = np.asarray(a), np.asarray(b)
    n = len(a)
    sh = lambda x: x.mean() / x.std() * np.sqrt(252)
    diffs = np.empty(N_BOOT)
    for k in range(N_BOOT):
        starts = rng.integers(0, n, n // BLOCK + 1)
        idx = (starts[:, None] + np.arange(BLOCK)).ravel()[:n] % n
        diffs[k] = sh(a[idx]) - sh(b[idx])
    obs = sh(a) - sh(b)
    p = min(1.0, 2 * min((diffs <= 0).mean(), (diffs >= 0).mean()))  # two-sided
    return obs, np.percentile(diffs, [2.5, 97.5]), p


# ---------- main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default="nifty50", choices=list(INDEXES) + ["all"])
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--source", default="yahoo", choices=["yahoo", "nse", "nse_tr"],
                    help="nse = NSE bhavcopy series (split/bonus adjusted, includes delisted stocks); "
                         "nse_tr = same with dividends reinvested (total return)")
    a = ap.parse_args()
    for idx in (INDEXES if a.index == "all" else [a.index]):
        run(idx, a.refresh, a.source)


NSE_SERIES = {"nse": os.path.join(base.DATA, "nse_series"), "nse_tr": os.path.join(base.DATA, "nse_series_tr")}


def nse_prices(symbol, source="nse"):
    path = os.path.join(NSE_SERIES[source], symbol + ".csv")
    return pd.read_csv(path, index_col=0, parse_dates=True) if os.path.exists(path) else pd.DataFrame()


def run(idx, refresh, source="yahoo"):
    tag = idx if source == "yahoo" else f"{idx}_{source}"  # output file prefix
    file, bench_sym, idx_name = INDEXES[idx]
    membership = os.path.join(base.DATA, file)
    print(f"\n===== {idx_name} =====", flush=True)
    nifty = base.prices("^NSEI", refresh)  # trading calendar
    days = nifty.loc[START:].index
    mask = membership_mask(days, membership)
    prefetch(([YAHOO.get(n, n + ".NS") for n in mask.columns] if source == "yahoo" else []) + [bench_sym], refresh)
    bench = base.prices(bench_sym, False)

    data, missing = {}, []
    for nse in mask.columns:
        ysym = YAHOO.get(nse, nse + ".NS")
        try:
            # prefetch() already honoured --refresh
            px = adjusted_prices(ysym, False) if source == "yahoo" else nse_prices(nse, source)
        except Exception:
            px = pd.DataFrame()
        if len(px) > 30:
            data[nse] = px
        else:
            missing.append(nse)

    # data quality: coverage of member-days, and suspicious one-day jumps while a member
    have = pd.DataFrame({s: data[s]["Close"].reindex(days).notna() for s in data}).reindex(columns=mask.columns,
                                                                                          fill_value=False)
    member_days = mask.values.sum()
    covered = (mask & have).values.sum()
    miss_days = (mask & ~have).sum().sort_values(ascending=False)
    miss_days = miss_days[miss_days > 0]
    spikes = []
    for s, px in data.items():
        r = px["Close"].pct_change().reindex(days)
        bad = r[(r.abs() > SPIKE) & mask[s]]
        spikes += [(s, d.date(), f"{v:+.0%}") for d, v in bad.items()]

    # 1) in-sample selection on the point-in-time portfolio
    rows, cache = [], {}
    for v in base.GRID:
        s, b = daily_returns(data, v)
        ps, pb = portfolio(s, mask), portfolio(b, mask)
        cache[base.label(v)] = (ps, pb, s, b)
        rows.append({"variant": base.label(v), **{f"IS {k}": x for k, x in perf(ps[:IS_END]).items()
                                                  if k in ("CAGR", "Sharpe", "MaxDD")}})
    sel = pd.DataFrame(rows).sort_values("IS Sharpe", ascending=False)
    chosen = sel.iloc[0]["variant"]
    ps, pb, s_rets, b_rets = cache[chosen]
    nifty_r = bench["Close"].pct_change().reindex(days).fillna(0)

    # 2) results table for the chosen variant
    table = []
    for period, (lo, hi) in {"In-sample 2010-18": (START, IS_END), "Out-of-sample 2019-": (OOS_START, None)}.items():
        for name, r in [("Strategy (PIT members)", ps), ("Buy & hold (PIT members)", pb), (f"{idx_name} index", nifty_r)]:
            table.append({"Period": period, "Portfolio": name, **perf(r[lo:hi])})
    table = pd.DataFrame(table)

    tests = []
    for period, (lo, hi) in {"In-sample": (START, IS_END), "Out-of-sample": (OOS_START, None)}.items():
        a_, b_ = ps[lo:hi], pb[lo:hi]
        obs, ci, p = bootstrap_sharpe_diff(a_, b_)
        tests.append({"Period": period, "Mean daily excess (bp)": (a_ - b_).mean() * 1e4,
                      "Newey-West t": nw_tstat(a_ - b_), "Sharpe diff": obs,
                      "Sharpe diff 95% CI": f"[{ci[0]:.2f}, {ci[1]:.2f}]", "Bootstrap p": p})
    tests = pd.DataFrame(tests)

    # 3) survivorship bias: same test on today's 50 names, held for the whole period
    today = set(read_membership(membership)["symbols"].iloc[-1].split(","))  # latest list in the file
    today_mask = pd.DataFrame({c: c in today for c in mask.columns}, index=days)
    surv = []
    for name, m in [("Point-in-time members", mask), ("Today's members, back-filled", today_mask)]:
        for period, (lo, hi) in {"IS": (START, IS_END), "OOS": (OOS_START, None)}.items():
            st_, bh_ = perf(portfolio(s_rets, m)[lo:hi]), perf(portfolio(b_rets, m)[lo:hi])
            surv.append({"Universe": name, "Period": period, "Strategy CAGR": st_["CAGR"], "B&H CAGR": bh_["CAGR"],
                         "Gap": st_["CAGR"] - bh_["CAGR"], "Strategy Sharpe": st_["Sharpe"], "B&H Sharpe": bh_["Sharpe"]})
    surv = pd.DataFrame(surv)

    # ---------- write ----------
    sel.to_csv(os.path.join(base.RESULTS, f"{tag}_pit_in_sample_selection.csv"), index=False)
    table.to_csv(os.path.join(base.RESULTS, f"{tag}_pit_performance.csv"), index=False)
    tests.to_csv(os.path.join(base.RESULTS, f"{tag}_pit_tests.csv"), index=False)
    surv.to_csv(os.path.join(base.RESULTS, f"{tag}_pit_survivorship.csv"), index=False)
    pd.DataFrame({"strategy": ps, "buy_hold": pb, "index": nifty_r}).to_csv(
        os.path.join(base.RESULTS, f"{tag}_pit_daily_returns.csv"))

    fmt = {"CAGR": "{:.1%}", "Vol": "{:.1%}", "Sharpe": "{:.2f}", "MaxDD": "{:.1%}"}
    show = table.copy()
    for k, f in fmt.items():
        show[k] = show[k].map(f.format)
    sv = surv.copy()
    for k in ["Strategy CAGR", "B&H CAGR", "Gap"]:
        sv[k] = sv[k].map("{:.1%}".format)
    lines = [
        f"# Triple Supertrend on {idx_name}: point-in-time (survivorship-free) test",
        "",
        f"Generated {dt.date.today()}. Prices: "
        + {"yahoo": "Yahoo (split- and dividend-adjusted)",
           "nse": "NSE bhavcopy, split/bonus/rights/demerger-adjusted, dividends NOT included (price return)",
           "nse_tr": "NSE bhavcopy, split/bonus/rights/demerger-adjusted, dividends reinvested (total return)"}[source] + ". Long-only, signals at close, fills at next open, {base.COST:.1%} per side. "
        "Equal-weight portfolio of the stocks that were Nifty 50 members on each day, rebalanced daily.",
        "",
        "## Data coverage",
        "",
        f"- Membership file: {file} ({mask.shape[1]} distinct stocks over the period).",
        f"- Member-days with price data: **{covered / member_days:.1%}** ({covered:,} of {member_days:,}).",
        f"- No price data for: {', '.join(f'{s} ({int(miss_days.get(s, 0))} member-days)' for s in missing) or 'none'}.",
        "- Partially missing (no price on some member-days, e.g. not yet listed): "
        + (", ".join(f"{s} ({n})" for s, n in miss_days.items() if s not in missing) or "none") + ".",
        f"- One-day moves > {SPIKE:.0%} during membership (check for unadjusted corporate actions): "
        + (", ".join(f"{s} {d} {v}" for s, d, v in spikes) or "none") + ".",
        "",
        "## 1. In-sample variant selection (portfolio Sharpe, 2010-2018)",
        "",
        sel.to_markdown(index=False, floatfmt=".3f"),
        "",
        f"**Chosen: {chosen}**",
        "",
        "## 2. Performance",
        "",
        show.to_markdown(index=False),
        "",
        "## 3. Is the difference real? (strategy minus buy & hold, daily)",
        "",
        tests.to_markdown(index=False, floatfmt=".3f"),
        "",
        f"Newey-West t uses 10 lags. Bootstrap: circular blocks of {BLOCK} days, {N_BOOT} resamples, two-sided p.",
        "",
        "## 4. Survivorship bias: point-in-time vs today's constituents",
        "",
        sv.to_markdown(index=False, floatfmt=".2f"),
        "",
        "## Limitations",
        "",
        "- Missing price history for the stocks listed above (mostly delisted or merged), so part of the "
        "survivorship effect remains.",
        "- Daily equal-weight rebalancing is not cost-charged; only strategy entries/exits pay costs.",
        "- When a stock leaves the index mid-trade, its return simply stops counting (no exit cost charged).",
        f"- Membership before the first change in the file ({read_membership(membership)['effective_date'].iloc[0].date()}) "
        "is inferred by reversing that change.",
    ]
    with open(os.path.join(base.RESULTS, f"{tag}_pit_summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
