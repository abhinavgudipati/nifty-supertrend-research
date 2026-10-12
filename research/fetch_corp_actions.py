"""
Download NSE's corporate-action records (ex-date + purpose, e.g. 'Bonus 1:1',
'Face Value Split From Rs.10/- To Rs.2/-', 'Demerger') for every year since 2009,
including companies that have since been delisted.

Saves research/data/corporate_actions.csv with columns symbol, ex_date, subject, series.
These drive the split/bonus adjustment in build_nse_series.py.

Run (quant env):  python fetch_corp_actions.py
"""
import os
import time

import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "corporate_actions.csv")
API = "https://www.nseindia.com/api/corporates-corporateActions"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
           "Accept": "application/json,text/plain,*/*",
           "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-actions"}


def main():
    s = requests.Session()
    rows = []
    for year in range(2009, pd.Timestamp.today().year + 1):
        # half-year windows keep each response a manageable size
        for lo, hi in [(f"01-01-{year}", f"30-06-{year}"), (f"01-07-{year}", f"31-12-{year}")]:
            for attempt in range(4):
                try:
                    r = s.get(API, params={"index": "equities", "from_date": lo, "to_date": hi},
                              headers=HEADERS, timeout=60)
                    r.raise_for_status()
                    data = r.json()
                    break
                except Exception:
                    time.sleep(2 + 3 * attempt)
            else:
                raise SystemExit(f"Failed to download {lo} to {hi}")
            rows += [{"symbol": d.get("symbol"), "ex_date": d.get("exDate"), "subject": (d.get("subject") or "").strip(),
                      "series": d.get("series")} for d in data]
            print(f"{lo} to {hi}: {len(data)} records", flush=True)
            time.sleep(1)
    df = pd.DataFrame(rows).drop_duplicates()
    df["ex_date"] = pd.to_datetime(df["ex_date"], format="%d-%b-%Y", errors="coerce")
    df.sort_values(["ex_date", "symbol"]).to_csv(OUT, index=False)
    print(f"Saved {len(df)} records to {OUT}")


if __name__ == "__main__":
    main()
