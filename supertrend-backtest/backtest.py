"""
Triple Supertrend backtest (long-only).

Entry : all three Supertrends green -> buy at NEXT bar's open
Exit  : Supertrend(11,2) turns red   -> sell at NEXT bar's open

Usage:
    pip install yfinance pandas numpy
    python backtest.py RELIANCE.NS --start 2018-01-01 --interval 1d
"""
import argparse

import numpy as np
import pandas as pd
import yfinance as yf

# (ATR period, multiplier)
FILTERS = [(12, 3), (10, 1), (11, 2)]
EXIT_FILTER = (11, 2)
COST_PER_SIDE = 0.001  # 0.1% brokerage + STT + slippage, adjust to taste
TREND_MA = 0  # if > 0, only enter when Close is above this many-bar simple moving average
# "supertrend": 3 Supertrends; "macd": MACD crossover alone; "combo": Supertrends + MACD above signal to enter
STRATEGY = "supertrend"
MACD = (12, 26, 9)  # fast EMA, slow EMA, signal EMA
ALLOW_SHORT = False  # also short when the trend is down (mirror image of the long rules)


def supertrend(df, period, mult, with_line=False):
    """Returns Series of direction: 1 = green (uptrend), -1 = red.
    With with_line=True, also returns the Supertrend line (the trailing stop level)."""
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()  # Wilder's RMA, same as TradingView
    hl2 = (h + l) / 2
    upper = (hl2 + mult * atr).to_numpy()
    lower = (hl2 - mult * atr).to_numpy()
    close = c.to_numpy()

    fu, fl = upper.copy(), lower.copy()
    direction = np.ones(len(df), dtype=int)
    for i in range(1, len(df)):
        fu[i] = upper[i] if upper[i] < fu[i - 1] or close[i - 1] > fu[i - 1] else fu[i - 1]
        fl[i] = lower[i] if lower[i] > fl[i - 1] or close[i - 1] < fl[i - 1] else fl[i - 1]
        if direction[i - 1] == -1 and close[i] > fu[i - 1]:
            direction[i] = 1
        elif direction[i - 1] == 1 and close[i] < fl[i - 1]:
            direction[i] = -1
        else:
            direction[i] = direction[i - 1]
    if with_line:
        line = np.where(direction == 1, fl, fu)
        return pd.Series(direction, index=df.index), pd.Series(line, index=df.index)
    return pd.Series(direction, index=df.index)


def macd(df, fast=12, slow=26, signal=9):
    """Returns (macd line, signal line)."""
    c = df["Close"]
    line = c.ewm(span=fast, adjust=False).mean() - c.ewm(span=slow, adjust=False).mean()
    return line, line.ewm(span=signal, adjust=False).mean()


def backtest(df):
    for p, m in FILTERS:
        df[f"st_{p}_{m}"] = supertrend(df, p, m)
    all_green = np.all([df[f"st_{p}_{m}"] == 1 for p, m in FILTERS], axis=0)
    all_red = np.all([df[f"st_{p}_{m}"] == -1 for p, m in FILTERS], axis=0)
    if TREND_MA:
        ma = df["Close"].rolling(TREND_MA).mean()
        all_green &= (df["Close"] > ma).to_numpy()
        all_red &= (df["Close"] < ma).to_numpy()
    exit_dir = supertrend(df, *EXIT_FILTER).to_numpy()
    exit_long, exit_short = exit_dir == -1, exit_dir == 1
    if STRATEGY in ("macd", "combo"):
        df["macd"], df["macd_signal"] = macd(df, *MACD)
        macd_up = (df["macd"] > df["macd_signal"]).to_numpy()
        if STRATEGY == "macd":
            all_green, all_red, exit_long, exit_short = macd_up, ~macd_up, ~macd_up, macd_up
        else:
            all_green &= macd_up
            all_red &= ~macd_up
    if not ALLOW_SHORT:
        all_red = np.zeros(len(df), dtype=bool)

    trades, pos, entry_px, entry_dt, eq0 = [], 0, 0.0, None, 1.0
    equity, position = np.ones(len(df)), np.zeros(len(df), dtype=int)
    opens, closes, idx = df["Open"].to_numpy(), df["Close"].to_numpy(), df.index

    def value(px):
        # long: grows with price; short: gains what the price loses (fixed notional from entry)
        return eq0 * (px / entry_px if pos == 1 else 2 - px / entry_px)

    for i in range(1, len(df)):
        equity[i] = equity[i - 1]
        # act on previous bar's signal at this bar's open (no lookahead)
        if (pos == 1 and exit_long[i - 1]) or (pos == -1 and exit_short[i - 1]):
            exit_px = opens[i] * (1 - pos * COST_PER_SIDE)
            equity[i] = value(exit_px)
            ret = (exit_px / entry_px - 1) * pos
            trades.append(("LONG" if pos == 1 else "SHORT", entry_dt, idx[i], entry_px, exit_px, ret))
            pos = 0
        if pos == 0 and (all_green[i - 1] or all_red[i - 1]):
            pos = 1 if all_green[i - 1] else -1
            entry_px, entry_dt, eq0 = opens[i] * (1 + pos * COST_PER_SIDE), idx[i], equity[i]
        if pos:
            equity[i] = value(closes[i])
        position[i] = pos

    df["equity"], df["position"] = equity, position  # position held at each bar's close
    # signals at each close (acted on at the next open) - used by the scanner
    df["sig_long"], df["sig_short"], df["sig_exit_long"], df["sig_exit_short"] = all_green, all_red, exit_long, exit_short
    df["entry_price"] = np.nan
    if pos:
        df.loc[df.index[-1], "entry_price"] = entry_px
    trades = pd.DataFrame(trades, columns=["side", "entry_date", "exit_date", "entry", "exit", "return"])
    return df, trades


def report(df, trades, ticker):
    eq = df["equity"]
    years = (df.index[-1] - df.index[0]).days / 365.25
    bh = df["Close"].iloc[-1] / df["Close"].iloc[0]
    dd = (eq / eq.cummax() - 1).min()
    rets = eq.pct_change().dropna()
    sharpe = rets.mean() / rets.std() * np.sqrt(len(rets) / years) if rets.std() > 0 else 0
    wins = trades[trades["return"] > 0]

    print(f"\n=== Triple Supertrend: {ticker} ({df.index[0].date()} -> {df.index[-1].date()}) ===")
    print(f"Strategy return : {eq.iloc[-1] - 1:8.1%}   CAGR {eq.iloc[-1] ** (1 / years) - 1:6.1%}")
    print(f"Buy & hold      : {bh - 1:8.1%}   CAGR {bh ** (1 / years) - 1:6.1%}")
    print(f"Max drawdown    : {dd:8.1%}")
    print(f"Sharpe (daily)  : {sharpe:8.2f}")
    print(f"Trades          : {len(trades):8d}")
    if len(trades):
        print(f"Win rate        : {len(wins) / len(trades):8.1%}")
        print(f"Avg win / loss  : {wins['return'].mean():.2%} / {trades[trades['return'] <= 0]['return'].mean():.2%}")
        print(f"Time in market  : {(trades['exit_date'] - trades['entry_date']).dt.days.sum() / (years * 365.25):8.1%}")
    trades.to_csv(f"trades_{ticker}.csv", index=False)
    print(f"\nTrade log -> trades_{ticker}.csv")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker", help="e.g. RELIANCE.NS, ^NSEI, TCS.NS")
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--interval", default="1d", help="1d, 1wk, 1h (hourly limited to ~2y)")
    ap.add_argument("--exit", default="11,2", help="exit Supertrend as period,mult")
    ap.add_argument("--trend-filter", type=int, default=0, help="only buy above this moving average, e.g. 200")
    ap.add_argument("--strategy", default="supertrend", choices=["supertrend", "macd", "combo"])
    ap.add_argument("--short", action="store_true", help="also short when the trend is down")
    a = ap.parse_args()
    TREND_MA = a.trend_filter
    STRATEGY = a.strategy
    ALLOW_SHORT = a.short
    EXIT_FILTER = tuple(float(x) if "." in x else int(x) for x in a.exit.split(","))

    data = yf.download(a.ticker, start=a.start, interval=a.interval, auto_adjust=True, progress=False)
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    data = data.dropna()
    if data.empty:
        raise SystemExit("No data. Check the ticker (NSE stocks need .NS suffix).")
    df, trades = backtest(data)
    report(df, trades, a.ticker)
