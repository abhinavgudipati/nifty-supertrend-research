"""
Run the Triple Supertrend strategy from backtest.py across a universe of
equities, indices and crypto, and print one comparison table.

Usage:
    python scan.py                                # default universe
    python scan.py BTC-USD ETH-USD TCS.NS ^GSPC   # custom tickers
    python scan.py --start 2018-01-01 --interval 1wk
"""
import argparse
import os
import time
import urllib.request

import numpy as np
import pandas as pd
import yfinance as yf

import backtest

UNIVERSE = {
    "Index": ["^NSEI", "^NSEBANK", "^GSPC", "^IXIC"],
    "Equity": ["RELIANCE.NS", "HDFCBANK.NS", "TCS.NS", "INFY.NS", "AAPL", "MSFT"],
    "Crypto": ["BTC-USD", "ETH-USD", "SOL-USD"],
}


def load(ticker, start, interval):
    df = yf.download(ticker, start=start, interval=interval, auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df[["Open", "High", "Low", "Close"]].dropna()


def load_many(tickers, start, interval, chunk=100, progress=None):
    """Bulk download: {ticker: OHLC frame}. Much faster than one request per stock."""
    out = {}
    for i in range(0, len(tickers), chunk):
        part = tickers[i:i + chunk]
        raw = yf.download(part, start=start, interval=interval, auto_adjust=True, progress=False,
                          group_by="ticker", threads=True)
        for t in part:
            try:
                out[t] = raw[t][["Open", "High", "Low", "Close"]].dropna()
            except KeyError:
                out[t] = pd.DataFrame(columns=["Open", "High", "Low", "Close"])
        if progress:
            progress(min(i + chunk, len(tickers)), len(tickers))
    return out


# NSE's official constituent lists, refreshed weekly into presets/
PRESETS = {
    "Nifty Total Market": "ind_niftytotalmarket_list",
    "Nifty 500": "ind_nifty500list",
    "Nifty 200": "ind_nifty200list",
    "Nifty 100": "ind_nifty100list",
    "Nifty 50": "ind_nifty50list",
}
PRESET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "presets")


def load_preset(name, max_age_days=7):
    """DataFrame with Symbol (Yahoo, .NS), Company, Industry. Uses the cached copy if NSE is unreachable."""
    os.makedirs(PRESET_DIR, exist_ok=True)
    path = os.path.join(PRESET_DIR, PRESETS[name] + ".csv")
    stale = not os.path.exists(path) or time.time() - os.path.getmtime(path) > max_age_days * 86400
    if stale:
        try:
            req = urllib.request.Request(f"https://niftyindices.com/IndexConstituent/{PRESETS[name]}.csv",
                                         headers={"User-Agent": "Mozilla/5.0"})
            with open(path, "wb") as f:
                f.write(urllib.request.urlopen(req, timeout=30).read())
        except Exception:
            if not os.path.exists(path):
                raise
    df = pd.read_csv(path)
    return pd.DataFrame({"Symbol": df["Symbol"].str.strip() + ".NS", "Company": df["Company Name"].str.strip(),
                         "Industry": df["Industry"].str.strip()})


# Indian listings first, then crypto/US; skip mutual funds, futures, options
EXCHANGE_RANK = {"NSI": 0, "BSE": 1}
QUOTE_TYPES = {"EQUITY", "INDEX", "ETF", "CRYPTOCURRENCY"}


def search_symbols(query, limit=8):
    """Company name (or ticker) -> list of (symbol, label), best Indian match first."""
    quotes = yf.Search(query, max_results=15, news_count=0).quotes
    quotes = [q for q in quotes if q.get("quoteType") in QUOTE_TYPES and q.get("symbol")]
    quotes.sort(key=lambda q: EXCHANGE_RANK.get(q.get("exchange"), 2))
    return [(q["symbol"], f"{q['symbol']}  ·  {q.get('shortname') or q.get('longname', '')}  ·  {q.get('exchDisp', q.get('exchange'))}")
            for q in quotes[:limit]]


def resolve(query):
    """Best single symbol for a name; falls back to the input as typed."""
    try:
        hits = search_symbols(query, 1)
    except Exception:  # Yahoo search unreachable
        hits = []
    return hits[0][0] if hits else query.strip().upper()


def looks_like_symbol(text):
    t = text.strip()
    return t == t.upper() and " " not in t and any(c in t for c in ".^-=")


def status(df, exit_line):
    """What the strategy says to do at the next open, from a backtested df."""
    last = df.iloc[-1]
    pos = int(last["position"])
    if pos == 1:
        action = "EXIT" if last["sig_exit_long"] else "HOLD LONG"
    elif pos == -1:
        action = "COVER SHORT" if last["sig_exit_short"] else "HOLD SHORT"
    else:
        action = "ENTER LONG" if last["sig_long"] else "ENTER SHORT" if last["sig_short"] else "STAY OUT"
    out = {"Action": action, "Close": last["Close"], "Last bar": df.index[-1].date()}
    if pos:
        changed = df["position"].ne(pos)
        since = df.index[changed.to_numpy().nonzero()[0].max() + 1] if changed.any() else df.index[0]
        out["In trade since"] = since.date()
        out["Trade P&L"] = (last["Close"] / last["entry_price"] - 1) * pos
    if exit_line is not None:
        # distance from today's close to the exit Supertrend line (the trailing stop)
        out["Stop level"] = exit_line.iloc[-1]
        out["Distance to stop"] = abs(last["Close"] / exit_line.iloc[-1] - 1)
    return out


def metrics(df, trades):
    eq, close = df["equity"], df["Close"]
    years = (df.index[-1] - df.index[0]).days / 365.25
    rets = eq.pct_change().dropna()
    # bars/year is measured from the data, so crypto (365d) and stocks (~250d) annualise correctly
    sharpe = rets.mean() / rets.std() * np.sqrt(len(rets) / years) if rets.std() > 0 else 0.0
    bh = close.iloc[-1] / close.iloc[0]
    held = (trades["exit_date"] - trades["entry_date"]).dt.days.sum() / (years * 365.25) if len(trades) else 0
    return {
        "CAGR": eq.iloc[-1] ** (1 / years) - 1,
        "B&H CAGR": bh ** (1 / years) - 1,
        "MaxDD": (eq / eq.cummax() - 1).min(),
        "B&H MaxDD": (close / close.cummax() - 1).min(),
        "Sharpe": sharpe,
        "Trades": len(trades),
        "WinRate": (trades["return"] > 0).mean() if len(trades) else np.nan,
        "Exposure": held,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="*")
    ap.add_argument("--start", default="2018-01-01")
    ap.add_argument("--interval", default="1d")
    ap.add_argument("--cost", type=float, default=0.001, help="cost per side, e.g. 0.001 = 0.1%%")
    a = ap.parse_args()
    backtest.COST_PER_SIDE = a.cost

    groups = {"Custom": a.tickers} if a.tickers else UNIVERSE
    rows = []
    for cls, tickers in groups.items():
        for t in tickers:
            df = load(t, a.start, a.interval)
            if len(df) < 100:
                print(f"skip {t}: not enough data")
                continue
            df, trades = backtest.backtest(df)
            rows.append({"Class": cls, "Ticker": t, **metrics(df, trades)})

    res = pd.DataFrame(rows).set_index(["Class", "Ticker"])
    res["Edge"] = res["CAGR"] - res["B&H CAGR"]
    pct = ["CAGR", "B&H CAGR", "Edge", "MaxDD", "B&H MaxDD", "WinRate", "Exposure"]
    out = res.copy()
    out[pct] = out[pct].map(lambda x: f"{x:6.1%}" if pd.notna(x) else "  -")
    out["Sharpe"] = out["Sharpe"].map("{:.2f}".format)
    pd.set_option("display.width", 200); pd.set_option("display.max_columns", None)
    print(f"\nTriple Supertrend  |  start {a.start}  interval {a.interval}  cost/side {a.cost:.2%}\n")
    print(out[["CAGR", "B&H CAGR", "Edge", "Sharpe", "MaxDD", "B&H MaxDD", "Trades", "WinRate", "Exposure"]])
    res.to_csv("scan_results.csv")
    print("\nSaved -> scan_results.csv")
