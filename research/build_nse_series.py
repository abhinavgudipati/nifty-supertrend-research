"""
Step 1 of the data clean-up: turn the daily NSE bhavcopy files into one RAW price series per
membership symbol, so delisted / renamed companies Yahoo lacks can be filled in.

Two kinds of symbol mismatch are handled:
  1. Renames (ZOMATO -> ETERNAL, INFRATEL -> INDUSTOWER, ...): linked automatically.
     Every bhavcopy row ties a symbol to an ISIN; ISINs of the same company share the issuer
     code (characters 3-7), even after a face-value split changes the rest. Symbols and issuer
     codes are joined with union-find, so all names a company ever traded under form one group.
  2. Aliases: older membership rows use company names cut to 10 characters (ALLAHABADB =
     Allahabad Bank, NSE symbol ALBK). These are mapped through data/symbol_aliases.csv,
     which this script seeds with ranked candidates for review (column 'nse_symbol').

Outputs
  data/nse_series/<MEMBERSHIP_SYMBOL>.csv   OHLC + volume, back-adjusted for splits/bonuses/demergers
                                            (see adjust(); dividends not adjusted)
  results/nse_corporate_actions.csv         every adjustment applied, for checking
  data/symbol_aliases.csv                   alias -> NSE symbol table (review the 'auto' rows)
  results/nse_coverage.md                   member-day coverage per index: Yahoo / NSE / combined

Run (quant env):  python build_nse_series.py
"""
import os
import re

import numpy as np
import pandas as pd

import run_pit as rp

HERE = os.path.dirname(os.path.abspath(__file__))
PANEL = os.path.join(HERE, "data", "bhav_panel.parquet")
ALIASES = os.path.join(HERE, "data", "symbol_aliases.csv")
OUT = os.path.join(HERE, "data", "nse_series")  # split/bonus/rights/demerger adjusted (price return)
OUT_TR = os.path.join(HERE, "data", "nse_series_tr")  # same + dividends reinvested (total return)


# ---------- panel ----------
def load_panel():
    """All daily files -> one table (cached as parquet)."""
    if not os.path.exists(PANEL):
        import glob
        files = sorted(glob.glob(os.path.join(HERE, "data", "bhavcopy", "*.csv.gz")))
        parts = []
        for f in files:
            d = pd.read_csv(f, dtype={"SYMBOL": str, "SERIES": str, "ISIN": str})
            d["DATE"] = pd.Timestamp(os.path.basename(f)[:10])
            parts.append(d)
        pd.concat(parts, ignore_index=True).to_parquet(PANEL, index=False)
    p = pd.read_parquet(PANEL)
    # one row per symbol-day: prefer the main EQ series over BE/BZ (trade-to-trade) rows
    rank = p["SERIES"].map({"EQ": 0, "BE": 1, "BZ": 2}).fillna(3)
    return p.assign(_r=rank).sort_values("_r").drop_duplicates(["SYMBOL", "DATE"]).drop(columns="_r")


# ---------- renames via ISIN ----------
class UnionFind(dict):
    def find(self, x):
        self.setdefault(x, x)
        while self[x] != x:
            self[x] = self[self[x]]
            x = self[x]
        return x

    def union(self, a, b):
        self[self.find(a)] = self.find(b)


def rename_groups(panel):
    """symbol -> group id; symbols sharing an ISIN issuer code end up in the same group."""
    uf = UnionFind()
    pairs = panel.dropna(subset=["ISIN"])[["SYMBOL", "ISIN"]].drop_duplicates()
    # rights entitlements / partly-paid lines share the company's ISIN issuer code but are separate
    # securities with their own prices - keep them out of the company's series
    pairs = pairs[~pairs["SYMBOL"].str.contains(r"-RE\d*$|-PP$", regex=True)]
    for sym, isin in pairs.itertuples(index=False):
        uf.union("S:" + sym, "I:" + isin[2:7])
    for sym in panel["SYMBOL"].unique():
        uf.find("S:" + sym)
    groups = {}
    for key in list(uf):
        if key.startswith("S:"):
            groups.setdefault(uf.find(key), []).append(key[2:])
    return {s: tuple(sorted(g)) for g in groups.values() for s in g}


# ---------- aliases ----------
def is_subsequence(short, long):
    it = iter(long)
    return all(c in it for c in short)


def alias_candidates(alias, spans, active_from, active_to, top=3):
    """Rank NSE symbols that traded during the alias's membership and look like its abbreviation."""
    a = alias.replace("&", "").replace("-", "")
    live = spans[(spans["min"] <= active_to) & (spans["max"] >= active_from)]
    scored = []
    for sym in live.index:
        s = sym.replace("&", "").replace("-", "")
        if not s or s[0] != a[0]:
            continue
        score = 0.0
        if a.startswith(s) or s.startswith(a[: len(s)]):
            score += 3 * min(len(s), len(a)) / len(a)  # prefix match: strongest evidence
        elif is_subsequence(s, a):
            score += 1.5 * len(s) / len(a)  # letters in order, e.g. ALBK in ALLAHABADB
        else:
            continue
        overlap = (min(active_to, live.at[sym, "max"]) - max(active_from, live.at[sym, "min"])).days
        score += 0.5 * overlap / max((active_to - active_from).days, 1)
        scored.append((round(score, 3), sym))
    return [s for _, s in sorted(scored, reverse=True)[:top]]


def membership_spans():
    """symbol -> (first day, last day) it was a member of any index."""
    days = rp.base.prices("^NSEI", False).loc[rp.START:].index
    spans = {}
    for file, _, _ in rp.INDEXES.values():
        mask = rp.membership_mask(days, os.path.join(rp.base.DATA, file))
        for s in mask.columns:
            d = mask.index[mask[s].to_numpy()]
            if len(d):
                lo, hi = spans.get(s, (d[0], d[-1]))
                spans[s] = (min(lo, d[0]), max(hi, d[-1]))
    return spans, days


def build_aliases(panel, mem_spans):
    sym_spans = panel.groupby("SYMBOL")["DATE"].agg(["min", "max"])
    old = pd.read_csv(ALIASES) if os.path.exists(ALIASES) else pd.DataFrame(columns=["alias"])
    old = old.set_index("alias")
    rows = []
    for alias, (lo, hi) in sorted(mem_spans.items()):
        if alias in sym_spans.index:
            continue  # real NSE symbol, no alias needed
        if alias in old.index and old.at[alias, "status"] in ("verified", "none"):
            rows.append(old.loc[alias].to_dict() | {"alias": alias})  # keep reviewed answers
            continue
        cands = alias_candidates(alias, sym_spans, lo, hi)
        rows.append({"alias": alias, "member_from": lo.date(), "member_to": hi.date(),
                     "nse_symbol": cands[0] if cands else "", "status": "auto" if cands else "unmatched",
                     "other_candidates": " ".join(cands[1:])})
    out = pd.DataFrame(rows)[["alias", "member_from", "member_to", "nse_symbol", "status", "other_candidates"]]
    out.to_csv(ALIASES, index=False)
    return out


# ---------- series ----------
def series_for(symbol, panel_by_sym, groups, alias_map):
    nse = alias_map.get(symbol, symbol)
    if not nse or nse not in groups:
        return None
    rows = pd.concat([panel_by_sym[s] for s in groups[nse] if s in panel_by_sym])
    rows = rows.sort_values("DATE").drop_duplicates("DATE", keep="last")  # rename day: keep the new symbol
    return rows.set_index("DATE")[["OPEN", "HIGH", "LOW", "CLOSE", "PREVCLOSE", "VOLUME"]].rename(
        columns={"PREVCLOSE": "PrevClose"} | {c: c.title() for c in ["OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"]})


CORP_ACTIONS = os.path.join(HERE, "data", "corporate_actions.csv")
BONUS = re.compile(r"bonus\s*(\d+)\s*:\s*(\d+)", re.I)
SPLIT = re.compile(r"(?:split|sub-division|consolidation).*?r[se]\.?\s*([\d.]+).*?\bto\s*r[se]\.?\s*([\d.]+)", re.I)
RIGHTS = re.compile(r"rights\s*(\d+)\s*:\s*(\d+).*?r[se]\.?\s*([\d.,]+)", re.I)
DEMERGER = re.compile(r"demerger|scheme of arrangement", re.I)
NOT_EQUITY = re.compile(r"debenture|ncrps|preference|redeemable", re.I)


def action_factor(subject):
    """
    Price multiplier implied by an NSE corporate-action description, or None.
      'Bonus 1:1'                            -> 0.5   (a new shares for every b held: b / (a + b))
      'Face Value Split From Rs.10 To Rs.2'  -> 0.2   (new face value / old)
    Demergers return 'demerger' (ratio is measured from prices instead). Dividends are ignored.
    """
    if NOT_EQUITY.search(subject):
        return None
    f, found = 1.0, False
    for a, b in BONUS.findall(subject):
        f *= int(b) / (int(a) + int(b))
        found = True
    for old, new in SPLIT.findall(subject):
        old, new = float(old.rstrip(".")), float(new.rstrip("."))
        if old > 0 and new > 0:
            f *= new / old
            found = True
    if found:
        return f
    m = RIGHTS.search(subject)
    if m:  # ("rights", new shares a, per b held, issue price) - ratio needs the cum-rights price
        return ("rights", int(m.group(1)), int(m.group(2)), float(m.group(3).replace(",", "").rstrip(".")))
    return "demerger" if DEMERGER.search(subject) else None


def load_actions():
    ca = pd.read_csv(CORP_ACTIONS, parse_dates=["ex_date"]).dropna(subset=["ex_date"])
    ca["factor"] = ca["subject"].map(action_factor)
    return ca[ca["factor"].notna()]


# "Dividend - Rs 5 Per Share", "Agm/Div-Rs.2.50/-", "Final Dividend Rs 8 And Special Dividend Rs 4"
DIVIDEND = re.compile(r"div[a-z]*\.?\s*[-:/]?\s*(?:of\s*)?r[se]\.?\s*(\d[\d.,]*)", re.I)
MAX_YIELD = 0.25  # a single dividend above 25% of the price is treated as a data error and skipped


def dividend_amount(subject):
    """Rupees per share in an NSE dividend description (summed if several), or None.
    Percent-of-face-value dividends ('Dividend - 50%') are skipped: face value isn't in the record."""
    amounts = []
    for x in DIVIDEND.findall(subject):
        x = re.sub(r"\.+", ".", x.replace(",", "")).rstrip(".")  # NSE typos like "62..50"
        try:
            amounts.append(float(x))
        except ValueError:
            pass
    return sum(amounts) if amounts else None


def load_dividends():
    ca = pd.read_csv(CORP_ACTIONS, parse_dates=["ex_date"]).dropna(subset=["ex_date"])
    ca["amount"] = ca["subject"].map(dividend_amount)
    ca = ca[ca["amount"].notna() & (ca["amount"] > 0)]
    # revised announcements repeat the same ex-date: keep one record per symbol and ex-date
    return ca.sort_values("amount").drop_duplicates(["symbol", "ex_date"], keep="last")


def adjust(s, symbols, actions, name, dividends=None):
    """
    Back-adjust raw NSE prices using NSE's corporate-action records for every symbol the company
    traded under. Splits/bonuses use the stated ratio; rights issues the theoretical ex-rights price.
    Demergers have no stated price ratio, so the ex-date ratio is measured as
    Open(ex-date) / Close(day before), kept only if it moved > 2%.
    If `dividends` is given, prices are also total-return adjusted: on each ex-date earlier prices
    are scaled by (1 - dividend / previous close). Returns (adjusted frame, list of applied events).
    """
    ev = actions[actions["symbol"].isin(symbols)]
    ratio = pd.Series(1.0, index=s.index)
    log = []
    if dividends is not None:
        for r in dividends[dividends["symbol"].isin(symbols)].itertuples():
            on = s.index[s.index >= r.ex_date]
            if not len(on) or on[0] == s.index[0] or (on[0] - r.ex_date).days > 5:
                continue  # before our data, or no trading near the ex-date
            d = on[0]
            p = s.at[s.index[s.index.get_loc(d) - 1], "Close"]
            y = r.amount / p
            if y > MAX_YIELD:
                log.append({"symbol": name, "nse_symbol": r.symbol, "ex_date": d.date(), "subject": r.subject,
                            "factor": None, "type": "dividend SKIPPED (yield > 25%)", "raw_move_on_ex_date": None})
                continue
            ratio[d] *= 1 - y
            log.append({"symbol": name, "nse_symbol": r.symbol, "ex_date": d.date(), "subject": r.subject,
                        "factor": round(1 - y, 6), "type": "dividend", "raw_move_on_ex_date": None})
    for r in ev.itertuples():
        on = s.index[s.index >= r.ex_date]
        if not len(on) or on[0] == s.index[0]:
            continue  # action before / at the start of our data
        d = on[0]
        prev = s.index[s.index.get_loc(d) - 1]
        if isinstance(r.factor, tuple):
            # theoretical ex-rights price: (b * P + a * S) / (a + b), P = last cum-rights close.
            # S = stated premium; face value (usually Rs 1-10) is left out, a small understatement.
            _, a, b, issue = r.factor
            p = s.at[prev, "Close"]
            if issue >= p:
                continue  # rights priced at/above market carry no value
            f, kind = (b * p + a * issue) / ((a + b) * p), "rights (TERP)"
        elif r.factor == "demerger":
            f = s.at[d, "Open"] / s.at[prev, "Close"]
            if abs(f - 1) <= 0.02:
                continue
            kind = "demerger (price-implied)"
        else:
            f, kind = float(r.factor), "split/bonus"
        ratio[d] *= f
        log.append({"symbol": name, "nse_symbol": r.symbol, "ex_date": d.date(), "subject": r.subject,
                    "factor": round(f, 6), "type": kind,
                    "raw_move_on_ex_date": round(s.at[d, "Close"] / s.at[prev, "Close"] - 1, 4)})
    factor = ratio[::-1].cumprod()[::-1].shift(-1).fillna(1.0)  # day i: product of later ratios
    out = s[["Open", "High", "Low", "Close"]].mul(factor, axis=0)
    out["Volume"] = s["Volume"] / factor
    return out, log


def main():
    os.makedirs(OUT, exist_ok=True)
    panel = load_panel()
    groups = rename_groups(panel)
    mem_spans, days = membership_spans()
    aliases = build_aliases(panel, mem_spans)
    alias_map = {r.alias: r.nse_symbol for r in aliases.itertuples()
                 if isinstance(r.nse_symbol, str) and r.nse_symbol and r.status == "verified"}  # never unreviewed guesses

    panel_by_sym = {s: g for s, g in panel.groupby("SYMBOL")}
    os.makedirs(OUT_TR, exist_ok=True)
    built, have, events, div_events = 0, {}, [], []
    actions, dividends = load_actions(), load_dividends()
    for sym in mem_spans:
        raw = series_for(sym, panel_by_sym, groups, alias_map)
        if raw is not None and len(raw):
            nse_syms = groups[alias_map.get(sym, sym)]
            s, ev = adjust(raw, nse_syms, actions, sym)  # price only
            events += ev
            s.to_csv(os.path.join(OUT, f"{sym}.csv"))
            tr, ev_tr = adjust(raw, nse_syms, actions, sym, dividends)  # total return
            div_events += [e for e in ev_tr if e["type"].startswith("dividend")]
            tr.to_csv(os.path.join(OUT_TR, f"{sym}.csv"))
            have[sym] = s["Close"].reindex(days).notna()
            built += 1

    pd.DataFrame(events).to_csv(os.path.join(rp.base.RESULTS, "nse_corporate_actions.csv"), index=False)
    pd.DataFrame(div_events).to_csv(os.path.join(rp.base.RESULTS, "nse_dividends_applied.csv"), index=False)

    # coverage per index
    lines = ["# NSE bhavcopy coverage", "",
             "Share of index member-days with a price, by source. Only reviewed ('verified') aliases are used; 'auto' rows are unreviewed guesses and are ignored.", "",
             "| Index | Yahoo | NSE (renames + aliases) | Either | Still missing |", "|---|---|---|---|---|"]
    for file, _, name in rp.INDEXES.values():
        mask = rp.membership_mask(days, os.path.join(rp.base.DATA, file))
        tot = mask.values.sum()
        y = pd.DataFrame({s: (rp.base.prices(rp.YAHOO.get(s, s + ".NS"), False)["Close"].reindex(days).notna()
                              if os.path.exists(os.path.join(rp.base.PRICES, rp.YAHOO.get(s, s + ".NS") + ".csv"))
                              else pd.Series(False, index=days)) for s in mask.columns})
        n = pd.DataFrame({s: have.get(s, pd.Series(False, index=days)) for s in mask.columns})
        y, n = y.fillna(False).astype(bool), n.fillna(False).astype(bool)
        lines.append(f"| {name} | {(mask & y).values.sum() / tot:.1%} | {(mask & n).values.sum() / tot:.1%} | "
                     f"{(mask & (y | n)).values.sum() / tot:.1%} | {(mask & ~(y | n)).values.sum() / tot:.1%} |")
    counts = aliases["status"].value_counts().to_dict()
    lines += ["", f"Series built: {built} of {len(mem_spans)} membership symbols.",
              f"Alias table ({len(aliases)} names): {counts}. Review data/symbol_aliases.csv - set status to "
              "'verified' (correct), fix nse_symbol, or 'none' (no NSE match)."]
    with open(os.path.join(rp.base.RESULTS, "nse_coverage.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
