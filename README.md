# Survivorship-Free Backtesting of the Triple Supertrend on Indian Equities

Does a popular trend-following rule, the Triple Supertrend, beat buy-and-hold on Nifty 50 stocks?
This project tests it on the stocks that were actually in the index on each day from 2010 to 2026,
including companies later delisted, using prices built from the National Stock Exchange's own files.

**Main result (2019–2026, not used for tuning):** the strategy earns 8.0% a year against 15.1% for
buy-and-hold, with a similar Sharpe ratio (0.96 vs 0.90) and a third of the drawdown (−12% vs −39%).
The difference in Sharpe ratio is not statistically significant. Testing on today's index members instead
of point-in-time members overstates buy-and-hold by 7–10 percentage points a year. A top-10 momentum rule
and an index-options implementation also fail to beat buy-and-hold.

The full write-up is in [`research/paper/main.tex`](research/paper/main.tex).

## What's here

| Folder | Contents |
| --- | --- |
| `supertrend-backtest/` | Strategy code (`backtest.py`), multi-asset scanner (`scan.py`), index-options ideas (`options_ideas.py`) and a Streamlit dashboard (`dashboard.py`) |
| `research/` | Data pipeline and research scripts (below) |
| `research/results/` | Result tables and summaries for the Nifty 50 study |
| `research/paper/` | LaTeX paper (`main.tex` for SSRN/Overleaf, `main_arxiv.tex` with inlined references), figures and `make_figures.py` |

## Data pipeline

Raw data is not included (about 850 MB). It is rebuilt from public sources:

1. `python research/fetch_bhavcopy.py`: downloads NSE's daily equity bhavcopy files, 2009 to today.
2. `python research/fetch_corp_actions.py`: downloads NSE's corporate-action records (splits, bonuses, rights, demergers, dividends).
3. Point-in-time Nifty 50 membership: download from [niftyhistory.in](https://niftyhistory.in/) and save as
   `research/data/nifty50_membership_2010_2026.csv` (columns `effective_date, index_type, inclusions, exclusions, symbols`).
4. `python research/build_nse_series.py`: links renamed companies via ISIN, applies corporate actions, and writes
   price-only (`data/nse_series/`) and total-return (`data/nse_series_tr/`) series, plus a coverage report.
5. `python research/run_pit.py --index nifty50 --source nse_tr`: point-in-time portfolio test, variant selection
   on 2010–2018, out-of-sample test on 2019 onward, Newey–West and block-bootstrap inference.
6. `python research/run_momentum.py`: momentum comparison.
7. `python research/paper/make_figures.py`: regenerates the paper's figures.

The adjusted total-return series match Yahoo Finance's adjusted prices to a median difference of 0.00% a year.
Only the Nifty 50 membership file passed consistency checks; see `research/results/membership_audit.md`.

## Dashboard

```bash
pip install -r requirements.txt
cd supertrend-backtest
streamlit run dashboard.py
```

Backtest any stock by name, scan the Nifty Total Market (or Nifty 50/100/200/500) for current signals,
and view index-option ideas. Prices come from Yahoo Finance at run time.

## Disclaimer

This is research, not investment advice. Option prices in the options analysis are model estimates, not traded prices.
