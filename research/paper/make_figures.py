"""
Builds the paper's figures as vector PDFs from the research results.

Run (quant env), from research/paper:  python make_figures.py
Needs: ../results/nifty50_nse_tr_pit_daily_returns.csv and ../results/nifty50_nse_tr_pit_survivorship.csv
(created by run_pit.py --index nifty50 --source nse_tr).
"""
import os

import matplotlib.pyplot as plt
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "..", "results")
OUT = os.path.join(HERE, "figures")

BLUE, GREY, RED, GREEN = "#2a6fdb", "#9a9a92", "#d9534f", "#5cb85c"
plt.rcParams.update({"font.family": "serif", "font.size": 9, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.titlesize": 9, "axes.titleweight": "bold"})


def growth_and_drawdown():
    d = pd.read_csv(os.path.join(RESULTS, "nifty50_nse_tr_pit_daily_returns.csv"), index_col=0, parse_dates=True)
    eq = (1 + d[["strategy", "buy_hold"]]).cumprod()
    dd = (eq / eq.cummax() - 1) * 100
    split = pd.Timestamp("2019-01-01")

    fig, (a, b) = plt.subplots(2, 1, figsize=(6.5, 5.2), sharex=True, gridspec_kw={"height_ratios": [1.6, 1]})
    a.plot(eq.index, eq["buy_hold"], color=GREY, lw=1.2, label="Buy and hold")
    a.plot(eq.index, eq["strategy"], color=BLUE, lw=1.5, label="Triple Supertrend")
    a.set_ylabel("Value of 1 invested (Jan 2010)")
    a.set_title("Panel A. Growth of 1 invested")
    for s, c in [("buy_hold", GREY), ("strategy", BLUE)]:
        a.annotate(f"{eq[s].iloc[-1]:.2f}", (eq.index[-1], eq[s].iloc[-1]), xytext=(4, 0),
                   textcoords="offset points", va="center", color=c, fontsize=8)
    a.legend(frameon=False, loc="upper left")

    b.fill_between(dd.index, dd["buy_hold"], 0, color=GREY, alpha=0.35, lw=0, label="Buy and hold")
    b.plot(dd.index, dd["strategy"], color=BLUE, lw=1.2, label="Triple Supertrend")
    b.set_ylabel("Fall from previous high (%)")
    b.set_title("Panel B. Drawdown")
    for s, c in [("buy_hold", GREY), ("strategy", BLUE)]:
        t = dd[s].idxmin()
        b.annotate(f"{dd[s].min():.1f}% ({t:%b %Y})", (t, dd[s].min()), xytext=(6, -2),
                   textcoords="offset points", color=c, fontsize=8)
    for ax in (a, b):
        ax.axvline(split, color="black", ls="--", lw=0.7)
    a.text(split, a.get_ylim()[1] * 0.97, "  out-of-sample  ", ha="left", va="top", fontsize=8)
    a.text(split, a.get_ylim()[1] * 0.97, "  in-sample  ", ha="right", va="top", fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_growth_drawdown.pdf"))
    plt.close(fig)


def survivorship():
    s = pd.read_csv(os.path.join(RESULTS, "nifty50_nse_tr_pit_survivorship.csv"))
    rows = []
    for period, label in [("IS", "2010–18"), ("OOS", "2019–26")]:
        pit = s[(s.Universe == "Point-in-time members") & (s.Period == period)].iloc[0]
        bf = s[(s.Universe != "Point-in-time members") & (s.Period == period)].iloc[0]
        rows.append((f"Buy and hold, {label}", pit["B&H CAGR"] * 100, bf["B&H CAGR"] * 100))
        rows.append((f"Triple Supertrend, {label}", pit["Strategy CAGR"] * 100, bf["Strategy CAGR"] * 100))
    fig, ax = plt.subplots(figsize=(6.5, 2.6))
    for i, (name, c, x) in enumerate(rows[::-1]):
        ax.plot([c, x], [i, i], color="#bbbbbb", lw=2, zorder=1)
        ax.scatter([c], [i], color=GREY, s=40, zorder=2, label="Point-in-time members" if i == 0 else None)
        ax.scatter([x], [i], color=BLUE, s=40, zorder=2, label="Today's members, back-filled" if i == 0 else None)
        ax.annotate(f"+{x - c:.1f} pp", (x, i), xytext=(8, 0), textcoords="offset points", va="center", fontsize=8)
    ax.set_yticks(range(len(rows)), [r[0] for r in rows[::-1]])
    ax.set_xlabel("Annual return (CAGR, %)")
    ax.set_xlim(0, 26)
    ax.legend(frameon=False, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=2, fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_survivorship.pdf"))
    plt.close(fig)


def options():
    # Totals from the synthetic option backtest (options_ideas.backtest_options), INR lakh, 1 lot per trade,
    # 2016-10 to 2026-10, exit Supertrend (12, 3), 1% slippage per side.
    idx = [("Nifty 50", -4.71, -6.91), ("Sensex", -2.39, -3.58), ("Bank Nifty", -2.85, -4.50)]
    dte = [(3, -4.71), (10, -2.74), (25, -1.51), (45, 0.58)]
    fig, (a, b) = plt.subplots(1, 2, figsize=(6.5, 2.8), sharey=True)
    xs = range(len(idx))
    a.bar([x - 0.2 for x in xs], [r[1] for r in idx], 0.38, color=RED, alpha=0.45, label="Calls only")
    a.bar([x + 0.2 for x in xs], [r[2] for r in idx], 0.38, color=RED, alpha=0.85, label="Calls and puts")
    a.set_xticks(list(xs), [r[0] for r in idx])
    a.axhline(0, color="black", lw=0.6)
    a.set_ylabel("Total P&L, INR lakh (1 lot)")
    a.set_title("Panel A. By index")
    a.legend(frameon=False, fontsize=8, loc="lower right")
    a.set_ylim(-8, 1.2)
    b.bar(range(len(dte)), [r[1] for r in dte], 0.6, color=[RED if v < 0 else GREEN for _, v in dte], alpha=0.7)
    b.set_xticks(range(len(dte)), [f"{d} days" for d, _ in dte])
    b.axhline(0, color="black", lw=0.6)
    b.set_title("Panel B. Nifty calls by minimum expiry")
    for ax, vals in [(a, [(x - 0.2, r[1]) for x, r in zip(xs, idx)] + [(x + 0.2, r[2]) for x, r in zip(xs, idx)]),
                     (b, list(enumerate(v for _, v in dte)))]:
        for x, v in vals:
            ax.annotate(f"{v:+.1f}", (x, v), xytext=(0, -10 if v < 0 else 3), textcoords="offset points",
                        ha="center", fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_options.pdf"))
    plt.close(fig)


def momentum_by_year():
    d = pd.read_csv(os.path.join(RESULTS, "nifty50_momentum_daily_returns.csv"), index_col=0, parse_dates=True)
    y = ((1 + d[["momentum", "buy_hold"]]).groupby(d.index.year).prod() - 1) * 100
    diff = y["momentum"] - y["buy_hold"]
    fig, ax = plt.subplots(figsize=(6.5, 2.8))
    ax.bar(diff.index, diff, color=[GREEN if v > 0 else RED for v in diff], alpha=0.7)
    ax.axhline(0, color="black", lw=0.6)
    ax.axvline(2018.5, color="black", ls="--", lw=0.7)
    ax.set_ylim(diff.min() - 5, diff.max() + 9)  # room for value labels and the period labels
    ax.text(2018.4, diff.max() + 6, "in-sample ", ha="right", fontsize=8)
    ax.text(2018.6, diff.max() + 6, " out-of-sample", ha="left", fontsize=8)
    for x, v in diff.items():
        ax.annotate(f"{v:+.0f}", (x, v), xytext=(0, 3 if v > 0 else -10), textcoords="offset points",
                    ha="center", fontsize=7)
    ax.set_xticks(diff.index, [f"'{str(x)[2:]}" for x in diff.index[:-1]] + [f"{diff.index[-1]}*"])
    ax.set_ylabel("Momentum minus buy and hold (pp)")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_momentum_by_year.pdf"))
    plt.close(fig)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    growth_and_drawdown()
    survivorship()
    options()
    momentum_by_year()
    print("Figures written to", OUT)
