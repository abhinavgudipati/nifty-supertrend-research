"""
Turns the Triple Supertrend signal on an index into an option idea.

Rules
  all 3 Supertrends green -> buy ATM call (CE)
  all 3 red               -> buy ATM put (PE)   [optional]
  mixed                   -> no new trade
  stop: index closes beyond the exit Supertrend line

Premiums are Black-Scholes ESTIMATES from India VIX, not live quotes.
Expiry days and lot sizes change with exchange circulars - edit INDICES below.
"""
import datetime as dt
import math

import numpy as np
import pandas as pd

import backtest
import scan

# Tuesday=1, Thursday=3. Lot sizes are editable in the dashboard.
INDICES = {
    "NIFTY 50":   {"yf": "^NSEI",    "step": 50,  "lot": 75, "expiry_wd": 1, "weekly": True},
    "SENSEX":     {"yf": "^BSESN",   "step": 100, "lot": 20, "expiry_wd": 3, "weekly": True},
    "BANK NIFTY": {"yf": "^NSEBANK", "step": 100, "lot": 30, "expiry_wd": 1, "weekly": False},
}
RISK_FREE = 0.065


def _ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs_price(spot, strike, days, vol, call):
    t = max(days, 0.5) / 365
    d1 = (math.log(spot / strike) + (RISK_FREE + vol ** 2 / 2) * t) / (vol * math.sqrt(t))
    d2 = d1 - vol * math.sqrt(t)
    if call:
        return spot * _ncdf(d1) - strike * math.exp(-RISK_FREE * t) * _ncdf(d2), _ncdf(d1)
    return strike * math.exp(-RISK_FREE * t) * _ncdf(-d2) - spot * _ncdf(-d1), _ncdf(d1) - 1


def next_expiry(today, weekday, weekly, min_days):
    """First expiry at least min_days away (ignores exchange holidays)."""
    d = today + dt.timedelta(days=min_days)
    if weekly:
        return d + dt.timedelta(days=(weekday - d.weekday()) % 7)
    # monthly: last <weekday> of the month
    y, m = d.year, d.month
    while True:
        last = dt.date(y + m // 12, m % 12 + 1, 1) - dt.timedelta(days=1)
        exp = last - dt.timedelta(days=(last.weekday() - weekday) % 7)
        if exp >= d:
            return exp
        y, m = y + m // 12, m % 12 + 1


def signal_age(dirs):
    """Bars since all three Supertrends last changed agreement state."""
    state = dirs.sum(axis=1).clip(-3, 3).map({3: 1, -3: -1}).fillna(0)
    changed = state.ne(state.shift())
    return int(len(state) - 1 - changed[changed].index.map(state.index.get_loc).max())


def recommend(df, cfg, vix, exit_st, allow_puts=True, min_days=3, today=None):
    today = today or dt.date.today()
    dirs = backtest.pd.concat([backtest.supertrend(df, p, m) for p, m in backtest.FILTERS], axis=1)
    last = dirs.iloc[-1]
    exit_dir, exit_line = backtest.supertrend(df, *exit_st, with_line=True)
    spot = float(df["Close"].iloc[-1])

    if (last == 1).all():
        side = "CE"
    elif (last == -1).all() and allow_puts:
        side = "PE"
    else:
        return {"action": "NO TRADE", "spot": spot, "dirs": last.tolist(),
                "reason": "Supertrends disagree - wait for all three to line up."}

    strike = round(spot / cfg["step"]) * cfg["step"]
    expiry = next_expiry(today, cfg["expiry_wd"], cfg["weekly"], min_days)
    days = (expiry - today).days
    prem, delta = bs_price(spot, strike, days, vix, side == "CE")
    stop = float(exit_line.iloc[-1])
    # reprice the option with the index at the stop, assuming that takes ~2 days
    prem_at_stop, _ = bs_price(stop, strike, max(days - 2, 0.5), vix, side == "CE")
    return {
        "action": f"BUY {side}", "side": side, "spot": spot, "strike": strike, "expiry": expiry,
        "days": days, "premium": prem, "delta": delta, "stop_index": stop,
        "premium_at_stop": prem_at_stop, "lot_cost": prem * cfg["lot"],
        "risk_per_lot": (prem - prem_at_stop) * cfg["lot"], "age": signal_age(dirs),
        "dirs": last.tolist(),
    }


def load_index(cfg, start):
    return scan.load(cfg["yf"], start, "1d")


def implied_vol(df, nifty, vix):
    """India VIX as the vol for Nifty; other indices scale it by their realised vol vs Nifty's."""
    v = (vix / 100).reindex(df.index).ffill().bfill()
    rv = df["Close"].pct_change().rolling(60).std()
    rv_n = nifty["Close"].pct_change().rolling(60).std().reindex(df.index).ffill()
    ratio = (rv / rv_n).clip(0.6, 2.5).fillna(1.0)
    return v if df.index.equals(nifty.index) else v * ratio


def backtest_options(df, iv, cfg, exit_st, allow_puts=True, min_days=3, cost=0.01):
    """
    Synthetic option backtest, 1 lot per trade.
    Signal and fills at the daily close. Held to the exit-Supertrend flip or expiry
    (settled at intrinsic value; if the signal still holds, a new contract is bought).
    """
    dirs = pd.concat([backtest.supertrend(df, p, m) for p, m in backtest.FILTERS], axis=1).to_numpy()
    ex = backtest.supertrend(df, *exit_st).to_numpy()
    close, vol, dates, lot = df["Close"].to_numpy(), iv.to_numpy(), df.index, cfg["lot"]

    trades, pos, realised = [], None, 0.0
    equity = np.zeros(len(df))
    start = max(p for p, _ in backtest.FILTERS) * 3  # let the ATR warm up

    def price(i, p):
        days = (p["expiry"] - dates[i].date()).days
        return bs_price(close[i], p["strike"], max(days, 0.5), vol[i], p["side"] == "CE")[0]

    def close_pos(i, px, why):
        nonlocal pos, realised
        sell = px * (1 - cost)
        pnl = (sell - pos["buy"]) * lot
        realised += pnl
        trades.append({"side": pos["side"], "entry_date": pos["date"], "exit_date": dates[i],
                       "strike": pos["strike"], "expiry": pos["expiry"], "entry_index": pos["spot"],
                       "exit_index": close[i], "entry_prem": pos["buy"], "exit_prem": sell,
                       "pnl": pnl, "return": sell / pos["buy"] - 1, "exit_reason": why})
        pos = None

    for i in range(start, len(df)):
        today = dates[i].date()
        if pos:
            if today >= pos["expiry"]:
                k = pos["strike"]
                close_pos(i, max(close[i] - k, 0) if pos["side"] == "CE" else max(k - close[i], 0), "expiry")
            elif (pos["side"] == "CE" and ex[i] == -1) or (pos["side"] == "PE" and ex[i] == 1):
                close_pos(i, price(i, pos), "signal")
        if pos is None:
            side = "CE" if (dirs[i] == 1).all() else "PE" if allow_puts and (dirs[i] == -1).all() else None
            if side:
                pos = {"side": side, "date": dates[i], "spot": close[i],
                       "strike": round(close[i] / cfg["step"]) * cfg["step"],
                       "expiry": next_expiry(today, cfg["expiry_wd"], cfg["weekly"], min_days)}
                pos["buy"] = price(i, pos) * (1 + cost)
        equity[i] = realised + ((price(i, pos) - pos["buy"]) * lot if pos else 0)

    eq = pd.Series(equity, index=dates).iloc[start:]
    return eq, pd.DataFrame(trades)


def option_stats(eq, trades):
    if trades.empty:
        return {}
    win = trades[trades["pnl"] > 0]
    loss = trades[trades["pnl"] <= 0]
    return {
        "Total P&L (1 lot)": trades["pnl"].sum(),
        "Trades": len(trades),
        "Win rate": len(win) / len(trades),
        "Avg win": win["pnl"].mean() if len(win) else 0.0,
        "Avg loss": loss["pnl"].mean() if len(loss) else 0.0,
        "Profit factor": win["pnl"].sum() / -loss["pnl"].sum() if loss["pnl"].sum() < 0 else np.inf,
        "Max drawdown": (eq - eq.cummax()).min(),
        "Biggest loss": trades["pnl"].min(),
    }
