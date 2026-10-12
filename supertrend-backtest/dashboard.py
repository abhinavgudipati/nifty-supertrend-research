"""
Triple Supertrend backtest dashboard.

Run:
    conda activate quant
    streamlit run dashboard.py
"""
import datetime as dt

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import backtest
import options_ideas as oi
import scan

st.set_page_config(page_title="Supertrend Backtester", layout="wide")


@st.cache_data(ttl=3600, show_spinner=False)
def load(ticker, start, interval):
    return scan.load(ticker, start, interval)


@st.cache_data(ttl=3600, show_spinner=False)
def load_index(name, start):
    return oi.load_index(oi.INDICES[name], start)


@st.cache_data(ttl=86400, show_spinner=False)
def search(query):
    return scan.search_symbols(query)


@st.cache_data(ttl=86400, show_spinner=False)
def resolve(name):
    return scan.resolve(name)


def no_data_msg(name, cfg):
    return f"No data from Yahoo for {name}."


DATE_FMT = "%d %b %Y"  # 09 Oct 2026
# shows datetime columns as "09 Oct 2026" while keeping them sortable as dates
DATE_COLS = {c: st.column_config.DateColumn(c.replace("_", " ").title(), format="DD MMM YYYY")
             for c in ["entry_date", "exit_date", "expiry"]}


def nice_date(d):
    return "" if pd.isna(d) else pd.Timestamp(d).strftime(DATE_FMT)


def run(ticker, start, interval, exit_st, trend_ma, cost):
    df = load(ticker, start, interval)
    if len(df) < 100:
        return None, None, None
    backtest.EXIT_FILTER, backtest.TREND_MA, backtest.COST_PER_SIDE = exit_st, trend_ma, cost
    backtest.STRATEGY, backtest.ALLOW_SHORT = strategy, allow_short
    df, trades = backtest.backtest(df.copy())
    return df, trades, scan.metrics(df, trades)


# ---------- sidebar ----------
st.sidebar.title("Settings")
STRATS = {"Triple Supertrend": "supertrend", "MACD crossover": "macd", "Supertrend + MACD filter": "combo"}
strategy = STRATS[st.sidebar.selectbox("Strategy", list(STRATS), help=(
    "MACD crossover: buy when MACD crosses above its signal line, sell when it crosses below. "
    "Supertrend + MACD: all three Supertrends green AND MACD above signal to buy; Supertrend exit."))]
if strategy != "supertrend":
    m1, m2, m3 = st.sidebar.columns(3)
    backtest.MACD = (m1.number_input("Fast", 2, 50, 12), m2.number_input("Slow", 5, 100, 26),
                     m3.number_input("Signal", 2, 50, 9))
start = st.sidebar.date_input("Start date", dt.date(2018, 1, 1), min_value=dt.date(2000, 1, 1))
interval = st.sidebar.radio("Bars", ["1d", "1wk"], format_func={"1d": "Daily", "1wk": "Weekly"}.get, horizontal=True)
exit_label = st.sidebar.selectbox(
    "Exit when this Supertrend turns red",
    ["12,3 (slow, recommended)", "11,2 (medium)", "10,1 (fast)"],
)
exit_st = tuple(int(x) for x in exit_label.split()[0].split(","))
trend_ma = 200 if st.sidebar.checkbox("Only buy above 200-bar average") else 0
allow_short = st.sidebar.checkbox("Also short when the trend is down", help=(
    "Mirror of the buy rule: all signals red → short, cover when the exit signal turns green. "
    "Indian stocks can't be held short overnight in cash - this needs futures."))
cost = st.sidebar.number_input("Cost per side (%)", 0.0, 2.0, 0.10, 0.05) / 100
st.sidebar.caption("Indian stocks need `.NS` (e.g. SBIN.NS). Crypto: BTC-USD. Indices: ^NSEI, ^GSPC.")

tab1, tab2, tab3 = st.tabs(["Single stock", "Scanner", "Index options"])

# ---------- single stock ----------
with tab1:
    query = st.text_input("Company name or ticker", "Reliance",
                          help="e.g. 'hdfc bank', 'infosys', 'bitcoin', 'nifty bank', or a symbol like TCS.NS").strip()
    try:
        hits = search(query) if query else []
    except Exception:
        # Yahoo search unreachable: fall back to treating the input as a symbol
        hits = [(query.upper(), f"{query.upper()}  ·  (Yahoo search unavailable, using as typed)")]
    if query and not hits:
        st.warning("No match on Yahoo. Try another spelling, the company's current name, or the exact symbol.")
    ticker = st.selectbox("Match", [h[0] for h in hits], format_func=dict(hits).get) if hits else None
    if ticker:
        with st.spinner(f"Fetching {ticker} from Yahoo and backtesting..."):
            df, trades, m = run(ticker, str(start), interval, exit_st, trend_ma, cost)
        if df is None:
            st.error("No data (or too little). Check the ticker - NSE stocks need .NS at the end.")
        else:
            st.caption(f"{nice_date(df.index[0])} → {nice_date(df.index[-1])}  ·  {len(df)} bars")
            c = st.columns(6)
            c[0].metric("Strategy CAGR", f"{m['CAGR']:.1%}", f"{m['CAGR'] - m['B&H CAGR']:+.1%} vs B&H")
            c[1].metric("Buy & hold CAGR", f"{m['B&H CAGR']:.1%}")
            c[2].metric("Worst fall", f"{m['MaxDD']:.0%}", f"B&H {m['B&H MaxDD']:.0%}", delta_color="off")
            c[3].metric("Sharpe", f"{m['Sharpe']:.2f}")
            c[4].metric("Trades", m["Trades"], f"{m['WinRate']:.0%} win" if m["Trades"] else None, delta_color="off")
            c[5].metric("Time invested", f"{m['Exposure']:.0%}")

            # growth of 1 lakh: strategy vs buy & hold
            bh = df["Close"] / df["Close"].iloc[0]
            fig = go.Figure()
            fig.add_scatter(x=df.index, y=df["equity"] * 100000, name="Strategy")
            fig.add_scatter(x=df.index, y=bh * 100000, name="Buy & hold", line=dict(dash="dot"))
            fig.update_layout(title="Growth of ₹1,00,000", height=380, margin=dict(t=40, b=10), hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)

            # price with buy/sell markers
            fig = go.Figure()
            fig.add_scatter(x=df.index, y=df["Close"], name="Close", line=dict(color="gray", width=1))
            if trend_ma:
                fig.add_scatter(x=df.index, y=df["Close"].rolling(trend_ma).mean(), name=f"{trend_ma} MA")
            if len(trades):
                for side, color in [("LONG", "green"), ("SHORT", "red")]:
                    t = trades[trades["side"] == side]
                    if len(t):
                        fig.add_scatter(x=t["entry_date"], y=t["entry"], mode="markers", name=f"{side.title()} entry",
                                        marker=dict(symbol="triangle-up" if side == "LONG" else "triangle-down",
                                                    size=10, color=color))
                        fig.add_scatter(x=t["exit_date"], y=t["exit"], mode="markers", name=f"{side.title()} exit",
                                        marker=dict(symbol="x", size=8, color=color))
            fig.update_layout(title="Price & trades", height=380, margin=dict(t=40, b=10))
            st.plotly_chart(fig, use_container_width=True)

            if "macd" in df:
                fig = go.Figure()
                fig.add_bar(x=df.index, y=df["macd"] - df["macd_signal"], name="Histogram", marker_color="lightgray")
                fig.add_scatter(x=df.index, y=df["macd"], name="MACD")
                fig.add_scatter(x=df.index, y=df["macd_signal"], name="Signal")
                fig.update_layout(title="MACD", height=260, margin=dict(t=40, b=10))
                st.plotly_chart(fig, use_container_width=True)

            # is it in a trade right now?
            st.subheader("Current signal")
            last_exit_red = backtest.supertrend(df, *exit_st).iloc[-1] == -1
            all_green = all(df[f"st_{p}_{mm}"].iloc[-1] == 1 for p, mm in backtest.FILTERS)
            if "macd" in df:
                macd_up = df["macd"].iloc[-1] > df["macd_signal"].iloc[-1]
                st.caption(f"MACD is {'above' if macd_up else 'below'} its signal line.")
                if strategy == "macd":
                    all_green, last_exit_red = macd_up, not macd_up
                else:
                    all_green = all_green and macd_up
            all_red = all(df[f"st_{p}_{mm}"].iloc[-1] == -1 for p, mm in backtest.FILTERS)
            if "macd" in df:
                all_red = not macd_up if strategy == "macd" else all_red and not macd_up
            if all_green:
                st.success("Buy conditions met → strategy would be LONG / buy at next open.")
            elif allow_short and all_red:
                st.error("Trend is down → strategy would be SHORT / sell at next open.")
            elif last_exit_red:
                st.error("Exit condition met → strategy would be OUT.")
            else:
                st.info("Mixed signals → hold if already in, otherwise wait.")

            st.subheader("Trades")
            if len(trades):
                t = trades.copy()
                t["days"] = (t["exit_date"] - t["entry_date"]).dt.days
                t["return"] = t["return"].map("{:.2%}".format)
                st.dataframe(t.iloc[::-1], use_container_width=True, hide_index=True, column_config=DATE_COLS)
                st.download_button("Download trades CSV", trades.to_csv(index=False), f"trades_{ticker}.csv")
            else:
                st.write("No trades in this period.")

# ---------- scanner ----------
ACTION_ORDER = ["ENTER LONG", "EXIT", "ENTER SHORT", "COVER SHORT", "HOLD LONG", "HOLD SHORT", "STAY OUT"]
ACTION_COLOR = {"ENTER LONG": "#1a7f37", "EXIT": "#cf222e", "ENTER SHORT": "#cf222e", "COVER SHORT": "#1a7f37",
                "HOLD LONG": "#4c9a5e", "HOLD SHORT": "#d1675f", "STAY OUT": "gray"}


def fetch(name, start, interval):
    """Runs in a worker thread: name -> symbol -> price history."""
    sym = name.upper() if scan.looks_like_symbol(name) else scan.resolve(name)
    return name, sym, scan.load(sym, start, interval)


@st.cache_data(ttl=86400, show_spinner=False)
def preset(name):
    return scan.load_preset(name)


def scan_one(name, sym, df, extra):
    df, trades = backtest.backtest(df.copy())
    line = backtest.supertrend(df, *exit_st, with_line=True)[1] if strategy != "macd" else None
    m = scan.metrics(df, trades)
    return {"Name": name, "Symbol": sym, **extra, **scan.status(df, line),
            "Strategy CAGR": m["CAGR"], "B&H CAGR": m["B&H CAGR"],
            "Edge": m["CAGR"] - m["B&H CAGR"], "Win rate": m["WinRate"], "Trades": m["Trades"]}


with tab2:
    st.caption("Uses the strategy and settings from the sidebar. Actions are for the **next open**, "
               "based on the last completed bar.")
    lists = list(scan.PRESETS) + ["Custom list"]
    choice = st.radio("Stock list", lists, horizontal=True)
    universe = None
    if choice == "Custom list":
        default = ["Reliance", "HDFC Bank", "Infosys", "TCS", "ICICI Bank", "Bharti Airtel", "ITC", "Larsen",
                   "State Bank of India", "Axis Bank"]
        raw = st.text_area("Companies (names or symbols), one per line or comma separated", "\n".join(default),
                           height=200)
        names = list(dict.fromkeys(n.strip() for n in raw.replace(",", "\n").splitlines() if n.strip()))
        st.caption(f"{len(names)} names")
    else:
        try:
            universe = preset(choice)
            names = list(universe["Symbol"])
            st.caption(f"{len(names)} stocks from NSE's current {choice} list. "
                       + ("A full scan takes a few minutes." if len(names) > 150 else ""))
        except Exception:
            names = []
            st.error("Couldn't download the list from niftyindices.com. Check your connection and retry.")

    if st.button("Scan", type="primary") and names:
        backtest.EXIT_FILTER, backtest.TREND_MA, backtest.COST_PER_SIDE = exit_st, trend_ma, cost
        backtest.STRATEGY, backtest.ALLOW_SHORT = strategy, allow_short
        rows, failed, bar = [], [], st.progress(0.0, "Fetching from Yahoo...")
        if universe is not None:
            # known NSE symbols: bulk download, then backtest each
            prices = scan.load_many(names, str(start), interval,
                                    progress=lambda d, n: bar.progress(d / n * 0.5, f"Downloaded {d}/{n}"))
            info = universe.set_index("Symbol")
            for k, sym in enumerate(names):
                df = prices.get(sym)
                if df is None or len(df) < 100:
                    failed.append(sym)
                else:
                    rows.append(scan_one(info.at[sym, "Company"], sym, df, {"Industry": info.at[sym, "Industry"]}))
                if k % 10 == 0:
                    bar.progress(0.5 + 0.5 * (k + 1) / len(names), f"Backtesting {k + 1}/{len(names)}  {sym}")
        else:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=8) as pool:
                futures = [pool.submit(fetch, n, str(start), interval) for n in names]
                for k, f in enumerate(as_completed(futures)):
                    try:
                        name, sym, df = f.result()
                    except Exception:
                        failed.append("?")
                        continue
                    bar.progress((k + 1) / len(names), f"{k + 1}/{len(names)}  {sym}")
                    if len(df) < 100:
                        failed.append(f"{name} ({sym})")
                        continue
                    rows.append(scan_one(name, sym, df, {}))
        bar.empty()
        st.session_state["scan"] = (pd.DataFrame(rows), failed)

    if "scan" in st.session_state:
        res, failed = st.session_state["scan"]
        # trade/stop columns only exist when some stock is in a trade (or uses a Supertrend exit)
        has_ind = "Industry" in res
        res = res.reindex(columns=["Name", "Symbol"] + (["Industry"] if has_ind else []) + ["Action", "Close", "Last bar", "In trade since", "Trade P&L",
                                   "Stop level", "Distance to stop", "Strategy CAGR", "B&H CAGR", "Edge",
                                   "Win rate", "Trades"])
        if failed:
            st.warning("No data for: " + ", ".join(failed) + " - try the exact symbol or current company name.")
        if len(res):
            res["_o"] = res["Action"].map(ACTION_ORDER.index)
            res = res.sort_values(["_o", "Edge"], ascending=[True, False]).drop(columns="_o")
            counts = res["Action"].value_counts()
            cols = st.columns(len(ACTION_ORDER))
            for c, a in zip(cols, ACTION_ORDER):
                c.metric(a.title(), int(counts.get(a, 0)))
            show = st.multiselect("Show", ACTION_ORDER, [a for a in ACTION_ORDER if a in counts])
            view = res[res["Action"].isin(show)]
            if has_ind:
                inds = st.multiselect("Industry", sorted(res["Industry"].dropna().unique()), placeholder="All industries")
                if inds:
                    view = view[view["Industry"].isin(inds)]
            q = st.text_input("🔍 Search stock", placeholder="Type a company name or symbol, e.g. 'tata' or 'SBIN'")
            if q.strip():
                hit = view["Name"].str.contains(q.strip(), case=False, na=False, regex=False) | \
                      view["Symbol"].str.contains(q.strip(), case=False, na=False, regex=False)
                view = view[hit]
                if view.empty:
                    st.info(f"No stock matching '{q}' in these results (check the Show/Industry filters above).")
            pct = {k: "{:.1%}" for k in ["Trade P&L", "Distance to stop", "Strategy CAGR", "B&H CAGR", "Edge", "Win rate"]}
            st.dataframe(
                view.style.format({**pct, "Close": "{:,.2f}", "Stop level": "{:,.2f}",
                                   "Last bar": nice_date, "In trade since": nice_date}, na_rep="")
                .map(lambda a: f"color: {ACTION_COLOR[a]}; font-weight: 600", subset=["Action"])
                .map(lambda v: "" if pd.isna(v) else f"color: {'green' if v > 0 else 'red'}", subset=["Edge", "Trade P&L"]),
                use_container_width=True, hide_index=True, height=min(38 * (len(view) + 1), 800),
            )
            st.caption("**Edge** = strategy CAGR minus buy-and-hold since the sidebar start date: a positive edge "
                       "means the strategy has historically worked on that stock. **Stop level / Distance to stop** = the "
                       "exit Supertrend line and how far the close is from it. In a trade, that's your exit level; "
                       "when out, it's how far price must move for that line to flip.")
            st.download_button("Download scan CSV", res.to_csv(index=False), "scan.csv")

# ---------- index options ----------
with tab3:
    st.caption("This tab always uses the Triple Supertrend rules (the Strategy picker doesn't apply here).")
    st.warning(
        "Rule-based output from your own strategy, not financial advice. Premiums are Black-Scholes "
        "**estimates** from India VIX and end-of-day prices - check the live option chain on your broker "
        "before placing anything. Verify expiry days and lot sizes against current NSE/BSE circulars."
    )
    o1, o2, o3 = st.columns(3)
    allow_puts = o1.checkbox("Suggest puts when all three are red", True)
    min_days = o2.slider("Minimum days to expiry", 1, 30, 3,
                         help="Skips contracts expiring too soon, where time decay is fastest")
    vix_df = load("^INDIAVIX", str(dt.date.today() - dt.timedelta(days=30)), "1d")
    vix_now = float(vix_df["Close"].iloc[-1]) if len(vix_df) else 15.0
    vix = o3.number_input("Volatility used (India VIX %)", 5.0, 80.0, round(vix_now, 1), 0.5) / 100

    for name, cfg in oi.INDICES.items():
        st.divider()
        h, lot_col = st.columns([4, 1])
        cfg = {**cfg, "lot": lot_col.number_input(f"{name} lot size", 1, 1000, cfg["lot"], key=f"lot_{name}")}
        df = load_index(name, str(dt.date.today() - dt.timedelta(days=500)))
        if len(df) < 100:
            h.subheader(name)
            st.info(no_data_msg(name, cfg))
            continue
        r = oi.recommend(df, cfg, vix, exit_st, allow_puts, min_days)
        lights = " ".join("🟢" if d == 1 else "🔴" for d in r["dirs"])
        h.subheader(f"{name}  ·  {r['spot']:,.0f}  ·  {lights}")
        if r["action"] == "NO TRADE":
            st.info(f"**No trade.** {r['reason']}")
            continue
        fresh = "fresh signal" if r["age"] <= 2 else f"signal is {r['age']} bars old - entry is late, consider waiting"
        (st.success if r["side"] == "CE" else st.error)(
            f"**{r['action']}  {name} {r['strike']:.0f} {r['side']}  ·  expiry {r['expiry']:%a %d %b %Y}** "
            f"({r['days']} days)  —  {fresh}"
        )
        c = st.columns(5)
        c[0].metric("Est. premium", f"₹{r['premium']:,.1f}")
        c[1].metric("Cost per lot", f"₹{r['lot_cost']:,.0f}")
        c[2].metric("Delta", f"{r['delta']:.2f}")
        c[3].metric("Exit if index closes", f"{'below' if r['side'] == 'CE' else 'above'} {r['stop_index']:,.0f}")
        c[4].metric("Est. loss per lot at exit", f"₹{r['risk_per_lot']:,.0f}")

    # ---------- options backtest ----------
    st.divider()
    st.header("Backtest: buying options on these signals")
    st.caption(
        "Simulated, not real option prices: each contract is priced daily with Black-Scholes using India VIX "
        "(scaled by each index's own volatility). Signal and fills at the daily close, 1 lot per trade, held "
        "until the exit Supertrend flips or the contract expires (then rolled if the signal still holds). "
        "Today's lot sizes and expiry days are used for the whole history."
    )
    b1, b2, b3, b4 = st.columns(4)
    bt_name = b1.selectbox("Index", list(oi.INDICES))
    bt_years = b2.slider("Years", 1, 10, 10)
    bt_days = b3.slider("Min days to expiry for backtest", 1, 60, min_days,
                        help="Longer-dated options lose less to time decay")
    bt_cost = b4.number_input("Slippage + charges per side (% of premium)", 0.0, 10.0, 1.0, 0.5) / 100
    if st.button("Run options backtest", type="primary"):
        bt_start = str(dt.date.today() - dt.timedelta(days=365 * bt_years + 120))
        cfg = {**oi.INDICES[bt_name], "lot": st.session_state.get(f"lot_{bt_name}", oi.INDICES[bt_name]["lot"])}
        df = load_index(bt_name, bt_start)
        if len(df) < 200:
            st.info(no_data_msg(bt_name, cfg))
        else:
            nifty = load("^NSEI", bt_start, "1d")
            iv = oi.implied_vol(df, nifty, load("^INDIAVIX", bt_start, "1d")["Close"])
            results = {}
            for label, puts in [("Calls only", False), ("Calls + puts", True)]:
                eq, tr = oi.backtest_options(df, iv, cfg, exit_st, puts, bt_days, bt_cost)
                results[label] = (eq, tr, oi.option_stats(eq, tr))
            st.session_state["opt_bt"] = (bt_name, results)

    # kept in session so switching the trade list below doesn't wipe the results
    if "opt_bt" in st.session_state:
        bt_name, results = st.session_state["opt_bt"]
        rows = {k: v[2] for k, v in results.items() if v[2]}
        if not rows:
            st.write("No trades.")
        else:
            tbl = pd.DataFrame(rows)
            fmt = lambda k, v: (f"{v:.0%}" if k == "Win rate" else f"{v:.2f}" if k == "Profit factor"
                                else f"{v:.0f}" if k == "Trades" else f"₹{v:,.0f}")
            st.dataframe(tbl.apply(lambda col: [fmt(k, v) for k, v in col.items()]), use_container_width=True)

            fig = go.Figure()
            for label, (eq, _, _) in results.items():
                fig.add_scatter(x=eq.index, y=eq, name=label)
            fig.update_layout(title=f"{bt_name}: cumulative P&L, 1 lot (₹)", height=380,
                              margin=dict(t=40, b=10), hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)

            label = st.radio("Show trades for", list(results), horizontal=True)
            tr = results[label][1]
            if len(tr):
                t = tr.iloc[::-1].copy()
                t["return"] = t["return"].map("{:.0%}".format)
                t["expiry"] = pd.to_datetime(t["expiry"])
                st.dataframe(t.round(1), use_container_width=True, hide_index=True, column_config=DATE_COLS)
