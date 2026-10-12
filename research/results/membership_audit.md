# Membership file audit (2026-10-12)

Checks run on the four `data/nifty*_membership_2010_2026.csv` files supplied by the author.

| File | Rows where a stock is listed as excluded but still appears in that row's list | Latest list matches NSE's official list today |
|---|---|---|
| Nifty 50 | 0 of 35 | yes (50/50) |
| Nifty 100 | 30 of 46 | yes (100/100) |
| Nifty 200 | 42 of 54 | yes (200/200) |
| Nifty 500 | 55 of 75 | yes (501/501) |

- **Nifty 50: internally consistent.** Usable for the point-in-time study.
- **Nifty 100 / 200 / 500: not usable as they stand.** Their historical lists contain stocks that the same
  file records as removed (e.g. Reliance Natural Resources is excluded from the Nifty 500 on 2010-07-10 but
  still listed in 2020). Replaying the inclusion/exclusion columns backwards from today's (correct) list does
  not fix it either: the Nifty 500 would grow to 630 names by 2010, so the change records are incomplete too.
- Older rows also use company names cut to 10 characters instead of NSE symbols (e.g. `ALLAHABADB`).

**Consequence:** the earlier Nifty 100/200/500 point-in-time results (`nifty100_pit_*`, `nifty200_pit_*`,
`nifty500_pit_*`) are built on this membership data and must not be cited. The Nifty 50 results stand.

**Needed:** an authoritative history of index changes for the broader indices, e.g. NSE Indices' semi-annual
reconstitution press releases (niftyindices.com), or a vendor dataset such as CMIE Prowess.
