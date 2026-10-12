"""
Download NSE's daily equity bhavcopy files (official end-of-day prices for every listed stock,
including ones later delisted) for every trading day since 2009.

Saves one small gzip CSV per day to research/data/bhavcopy/YYYY-MM-DD.csv.gz with columns
  SYMBOL, SERIES, ISIN, OPEN, HIGH, LOW, CLOSE, PREVCLOSE, VOLUME
PREVCLOSE is NSE's base price for the day: on the ex-date of a split/bonus it is already adjusted,
which is how corporate actions are detected later.
keeping only equity series (EQ, BE, BZ, SM, ST). Prices are RAW: not adjusted for splits,
bonuses or demergers - that is handled in a later step.

Resumable: days already saved are skipped. Days NSE has no file for are logged to missing_days.txt.

Run (quant env):  python fetch_bhavcopy.py [--start 2009-01-01] [--workers 4]
"""
import argparse
import io
import os
import random
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "bhavcopy")
CALENDAR = os.path.join(HERE, "data", "prices", "IDX_NSEI.csv")  # Nifty trading days (Yahoo)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
NEW_FORMAT_FROM = pd.Timestamp("2024-07-08")  # NSE switched to the UDiFF file format
SERIES = {"EQ", "BE", "BZ", "SM", "ST"}
COLS = ["SYMBOL", "SERIES", "ISIN", "OPEN", "HIGH", "LOW", "CLOSE", "PREVCLOSE", "VOLUME"]


def urls(day):
    mon = day.strftime("%b").upper()
    old = (f"https://archives.nseindia.com/content/historical/EQUITIES/{day:%Y}/{mon}/"
           f"cm{day:%d}{mon}{day:%Y}bhav.csv.zip")
    new = f"https://archives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{day:%Y%m%d}_F_0000.csv.zip"
    return [new, old] if day >= NEW_FORMAT_FROM else [old, new]


def parse(raw):
    df = pd.read_csv(io.BytesIO(raw), dtype=str)
    df.columns = [c.strip() for c in df.columns]
    if "TckrSymb" in df.columns:  # new format
        df = df.rename(columns={"TckrSymb": "SYMBOL", "SctySrs": "SERIES", "OpnPric": "OPEN", "HghPric": "HIGH",
                                "LwPric": "LOW", "ClsPric": "CLOSE", "PrvsClsgPric": "PREVCLOSE",
                                "TtlTradgVol": "VOLUME"})
    else:
        df = df.rename(columns={"TOTTRDQTY": "VOLUME"})
    df["SERIES"] = df["SERIES"].str.strip()
    df = df[df["SERIES"].isin(SERIES)].reindex(columns=COLS)  # pre-2011 files have no ISIN column
    df["SYMBOL"] = df["SYMBOL"].str.strip()
    return df


def fetch(day, redo=False):
    path = os.path.join(OUT, f"{day:%Y-%m-%d}.csv.gz")
    if os.path.exists(path) and not (redo and "PREVCLOSE" not in pd.read_csv(path, nrows=0).columns):
        return day, "cached"
    for url in urls(day):
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.nseindia.com/"})
                raw = urllib.request.urlopen(req, timeout=30).read()
                with zipfile.ZipFile(io.BytesIO(raw)) as z:
                    df = parse(z.read(z.namelist()[0]))
                df.to_csv(path, index=False, compression="gzip")
                time.sleep(0.3 + random.random() * 0.4)  # be polite to NSE
                return day, "ok"
            except urllib.error.HTTPError as e:
                if e.code in (403, 404):
                    break  # no file at this URL; try the other format
                time.sleep(2 ** attempt)
            except Exception:
                time.sleep(2 ** attempt)
    return day, "missing"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2009-01-01")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--redo", action="store_true", help="re-download days saved without PREVCLOSE")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    days = [d for d in pd.read_csv(CALENDAR, index_col=0, parse_dates=True).index if d >= pd.Timestamp(a.start)]
    print(f"{len(days)} trading days from {days[0]:%Y-%m-%d} to {days[-1]:%Y-%m-%d}", flush=True)
    counts, missing = {"ok": 0, "cached": 0, "missing": 0}, []
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        for k, f in enumerate(as_completed([pool.submit(fetch, d, a.redo) for d in days]), 1):
            day, status = f.result()
            counts[status] += 1
            if status == "missing":
                missing.append(f"{day:%Y-%m-%d}")
            if k % 100 == 0 or k == len(days):
                print(f"{k}/{len(days)}  {counts}", flush=True)
    with open(os.path.join(OUT, "missing_days.txt"), "w") as f:
        f.write("\n".join(sorted(missing)))
    print(f"Done. {counts}. Missing days listed in data/bhavcopy/missing_days.txt", flush=True)


if __name__ == "__main__":
    main()
