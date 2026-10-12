"""
Step 1 of the research project: in-sample / out-of-sample test of the Triple Supertrend
strategy on the Nifty 50 universe.

  In-sample  (IS) : 2010-01-01 .. 2018-12-31  -> pick ONE variant (best median Sharpe)
  Out-of-sample (OOS): 2019-01-01 .. latest   -> report that variant, untouched

Everything is cached under research/data so a run can be reproduced exactly.

Run (quant env):
    python run_split.py            # uses cached data if present
    python run_split.py --refresh  # re-download constituents and prices
"""
import argparse
import datetime as dt
import io
import os
import sys
import urllib.request

import numpy as np
import pandas as pd
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "supertrend-backtest"))
import backtest  # noqa: E402
import scan  # noqa: E402

DATA, PRICES, RESULTS = (os.path.join(HERE, p) for p in ("data", "data/prices", "results"))
CONSTITUENTS_URL = "https://niftyindices.com/IndexConstituent/ind_nifty50list.csv"
INDICES = ["^NSEI", "^NSEBANK"]

DOWNLOAD_FROM = "2009-01-01"  # one extra year so indicators are warmed up by 2010
IS_START, IS_END = "2010-01-01", "2018-12-31"
OOS_START = "2019-01-01"
MIN_BARS = 250  # skip an asset in a window if it has less than ~1 year of data there

COST = 0.001  # per side
GRID = [{"exit": e, "trend_ma": ma} for e in [(10, 1), (11, 2), (12, 3)] for ma in [0, 200]]


# ---------- data ----------
def constituents(refresh):
    path = os.path.join(DATA, "nifty50_constituents.csv")
    if refresh or not os.path.exists(path):
        req = urllib.request.Request(CONSTITUENTS_URL, headers={"User-Agent": "Mozilla/5.0"})
        df = pd.read_csv(io.StringIO(urllib.request.urlopen(req, timeout=30).read().decode()))
        df["downloaded"] = dt.date.today().isoformat()
        df.to_csv(path, index=False)
    return pd.read_csv(path)


def prices(symbol, refresh):
    path = os.path.join(PRICES, symbol.replace("^", "IDX_") + ".csv")
    if refresh or not os.path.exists(path):
        scan.load(symbol, DOWNLOAD_FROM, "1d").to_csv(path)
    return pd.read_csv(path, index_col=0, parse_dates=True)


# ---------- metrics ----------
def window_stats(df, trades, start, end=None):
    w = df.loc[start:end]
    if len(w) < MIN_BARS:
        return None
    years = (w.index[-1] - w.index[0]).days / 365.25
    out = {}
    for tag, series in [("strat", w["equity"]), ("bh", w["Close"])]:
        r = series.pct_change().dropna()
        out[f"{tag}_cagr"] = (series.iloc[-1] / series.iloc[0]) ** (1 / years) - 1
        out[f"{tag}_sharpe"] = r.mean() / r.std() * np.sqrt(len(r) / years) if r.std() > 0 else 0.0
        out[f"{tag}_maxdd"] = (series / series.cummax() - 1).min()
    t = trades[(trades["entry_date"] >= w.index[0]) & (trades["entry_date"] <= w.index[-1])]
    out.update(trades=len(t), win_rate=(t["return"] > 0).mean() if len(t) else np.nan,
               exposure=(w["position"] != 0).mean(), start=w.index[0].date(), end=w.index[-1].date())
    return out


def run_variant(data, v):
    backtest.STRATEGY, backtest.ALLOW_SHORT, backtest.COST_PER_SIDE = "supertrend", False, COST
    backtest.EXIT_FILTER, backtest.TREND_MA = v["exit"], v["trend_ma"]
    rows = []
    for sym, (kind, px) in data.items():
        df, trades = backtest.backtest(px.copy())
        for period, (s, e) in {"IS": (IS_START, IS_END), "OOS": (OOS_START, None)}.items():
            st = window_stats(df, trades, s, e)
            if st:
                rows.append({"symbol": sym, "kind": kind, "period": period, **st})
    return pd.DataFrame(rows)


def label(v):
    return f"exit ST{v['exit']}" + (f" + {v['trend_ma']}d MA filter" if v["trend_ma"] else "")


def significance(df):
    """Across stocks: is strategy minus buy-and-hold different from zero?"""
    out = {}
    for m in ["cagr", "sharpe"]:
        d = (df[f"strat_{m}"] - df[f"bh_{m}"]).dropna()
        out[f"{m}_diff_median"] = d.median()
        out[f"{m}_beat_share"] = (d > 0).mean()
        out[f"{m}_ttest_p"] = stats.ttest_1samp(d, 0).pvalue
        out[f"{m}_wilcoxon_p"] = stats.wilcoxon(d).pvalue
    out["n"] = len(df)
    return out


# ---------- main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    for d in (DATA, PRICES, RESULTS):
        os.makedirs(d, exist_ok=True)

    cons = constituents(a.refresh)
    symbols = [(s + ".NS", "stock") for s in cons["Symbol"]] + [(s, "index") for s in INDICES]
    data, missing = {}, []
    for sym, kind in symbols:
        px = prices(sym, a.refresh)
        (data.__setitem__(sym, (kind, px)) if len(px) > MIN_BARS else missing.append(sym))
    print(f"Universe: {len(data)} assets ({len(cons)} Nifty 50 constituents as of "
          f"{cons['downloaded'].iloc[0]} + {len(INDICES)} indices). Missing: {missing or 'none'}")

    # 1) in-sample: evaluate every variant, choose by median Sharpe across STOCKS only
    all_rows, is_table = [], []
    for v in GRID:
        res = run_variant(data, v).assign(variant=label(v))
        all_rows.append(res)
        s = res[(res.period == "IS") & (res.kind == "stock")]
        is_table.append({"variant": label(v), "median_sharpe": s["strat_sharpe"].median(),
                         "median_cagr": s["strat_cagr"].median(), "median_bh_cagr": s["bh_cagr"].median(),
                         "stocks": len(s)})
    allres = pd.concat(all_rows)
    is_table = pd.DataFrame(is_table).sort_values("median_sharpe", ascending=False)
    chosen = is_table.iloc[0]["variant"]

    # 2) out-of-sample: the chosen variant only
    oos = allres[(allres.variant == chosen) & (allres.period == "OOS")]
    oos_stocks = oos[oos.kind == "stock"]
    sig = significance(oos_stocks)
    sig_is = significance(allres[(allres.variant == chosen) & (allres.period == "IS") & (allres.kind == "stock")])

    allres.to_csv(os.path.join(RESULTS, "all_variants_by_asset.csv"), index=False)
    is_table.to_csv(os.path.join(RESULTS, "in_sample_selection.csv"), index=False)
    oos.to_csv(os.path.join(RESULTS, "oos_chosen_by_asset.csv"), index=False)

    pct = lambda x: f"{x:.1%}"
    lines = [
        "# Triple Supertrend on Nifty 50: in-sample / out-of-sample",
        "",
        f"Generated {dt.date.today()}. Long-only, signals at close, fills at next open, "
        f"{COST:.1%} cost per side. In-sample {IS_START} to {IS_END}; out-of-sample from {OOS_START}.",
        "",
        "## 1. In-sample variant selection (stocks, median across stocks)",
        "",
        is_table.to_markdown(index=False, floatfmt=".3f"),
        "",
        f"**Chosen variant: {chosen}** (highest in-sample median Sharpe).",
        "",
        "## 2. Out-of-sample results for the chosen variant",
        "",
        "| | In-sample | Out-of-sample |",
        "|---|---|---|",
        f"| Stocks tested | {sig_is['n']} | {sig['n']} |",
        f"| Median CAGR difference vs buy & hold | {pct(sig_is['cagr_diff_median'])} | {pct(sig['cagr_diff_median'])} |",
        f"| Share of stocks beating B&H on CAGR | {pct(sig_is['cagr_beat_share'])} | {pct(sig['cagr_beat_share'])} |",
        f"| Median Sharpe difference vs B&H | {sig_is['sharpe_diff_median']:.2f} | {sig['sharpe_diff_median']:.2f} |",
        f"| Share of stocks beating B&H on Sharpe | {pct(sig_is['sharpe_beat_share'])} | {pct(sig['sharpe_beat_share'])} |",
        f"| t-test p-value (CAGR diff = 0) | {sig_is['cagr_ttest_p']:.3f} | {sig['cagr_ttest_p']:.3f} |",
        f"| Wilcoxon p-value (CAGR diff = 0) | {sig_is['cagr_wilcoxon_p']:.3f} | {sig['cagr_wilcoxon_p']:.3f} |",
        f"| t-test p-value (Sharpe diff = 0) | {sig_is['sharpe_ttest_p']:.3f} | {sig['sharpe_ttest_p']:.3f} |",
        "",
        "### Indices (out-of-sample)",
        "",
        oos[oos.kind == "index"][["symbol", "strat_cagr", "bh_cagr", "strat_sharpe", "bh_sharpe",
                                  "strat_maxdd", "bh_maxdd", "trades"]].to_markdown(index=False, floatfmt=".3f"),
        "",
        "## Known limitations (to fix in later steps)",
        "",
        "- **Survivorship bias:** universe is today's Nifty 50 applied backwards; firms that left the "
        "index are missing. That likely flatters buy & hold more than the strategy, which exits falling stocks.",
        "- Stocks are treated as independent in the p-values, but they are correlated; "
        "a block bootstrap is needed.",
        "- Flat cost assumption; no STT/stamp-duty breakdown or cost sensitivity yet.",
        "- Yahoo adjusted prices; no cross-check against NSE bhavcopy.",
    ]
    with open(os.path.join(RESULTS, "summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
