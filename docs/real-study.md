# Question, sources, sessions, and empirical analysis

## Research question

How do major cash equity indices respond around economic announcements when
Asian, European, and U.S. trading sessions open at different times?

The working question determines the schema and alignment rules: an observed price
in an open market and the next available price of a closed market represent
different elapsed times and information windows. They must not share a misleading
“one hour after release” label.

## Sources and instruments

| Region | Cash index | Yahoo ticker | Calendar used |
|---|---|---|---|
| Asia | Hang Seng | `^HSI` | XHKG |
| Europe | EURO STOXX 50 | `^STOXX50E` | XPAR main cash-session proxy |
| U.S. | Nasdaq-100 | `^NDX` | XNYS regular-session proxy |

These proxies describe regular cash trading, not index dissemination or futures
hours. EURO STOXX 50 spans venues; XPAR is not a complete constituent-level
calendar. XNYS is not a Nasdaq-specific calendar, though it supplies the regular
U.S. cash session used here. Those differences are limitations, not hidden assumptions.

Original Yahoo HSI/STOXX hourly archives are reused. `NQ=F` is not renamed into
cash data: actual `^NDX` hourly observations were downloaded for 2024-10-08 to
2024-12-30. Investing.com events come from the original calendar CSV, whose
importance, country, timestamp, actual, forecast and previous fields are imported
into SQL. No new economic source has replaced Investing.com. Automated live
Investing.com scraping is not advertised as a maintained connector; a sourced CSV
archive/export is the input boundary.

Calendar source times are explicitly declared as UTC. Spot checks against
[BLS CPI on 2024-10-10](https://www.bls.gov/news.release/archives/cpi_10102024.htm),
[BLS payrolls on 2024-11-01](https://www.bls.gov/news.release/archives/empsit_11012024.htm),
and [the Fed statement on 2024-11-07](https://www.federalreserve.gov/newsevents/pressreleases/monetary20241107a.htm)
match the archived values. These checks support the chosen timezone; they do not
certify every archived event time or the original collection code.

## Audit of the original opening / closing slide

| Original label / interval in CEST | Finding |
|---|---|
| HSI 03:30–10:00, lunch 06:00–07:00 | Summer conversion of Hong Kong regular continuous hours; winter Brussels time is 02:30–09:00, lunch 05:00–06:00. Closing auction is a separate window. |
| STOXX50E 09:00–17:30 | A main underlying cash-session illustration, not the full EURO STOXX 50 dissemination window. |
| U.S. NQ=F 15:30–22:00 | U.S. cash regular hours in Brussels for most dates; wrong label for futures. Use NDX cash. During DST-mismatch weeks it is 14:30–21:00. |

[HKEX](https://www.hkex.com.hk/Services/Trading-hours-and-Severe-Weather-Arrangements/Trading-Hours/Securities-Market)
documents continuous sessions and closing auctions.
[Nasdaq](https://www.nasdaq.com/market-activity/stock-market-holiday-schedule)
documents 09:30–16:00 ET regular hours.
[STOXX](https://stoxx.com/index/SX5E/)
lists a 09:00–18:00 CET dissemination period, which must not be conflated with
the proxy's underlying cash trading window.
The revised date-aware chart uses exchange calendars for holidays, half-days,
Hong Kong lunch, and actual UTC-to-Europe/Brussels conversion. Cash sessions
overlap but leave an overnight gap; the project does not claim 24h continuity.

## Normalization and SQL

Start-labelled UTC 1h OHLC observations are accepted only when the entire bar is
inside a regular continuous segment. Partial closing/lunch bars are conservatively
excluded. Their future close is never assigned to an invented earlier endpoint.
All Day / missing-time events are excluded from intraday alignment; no midnight
time is manufactured.

`study.py prepare` validates source batches, then atomically replaces a dedicated
real-study snapshot in SQL. The loader refuses mixed synthetic instruments. It
preserves successful ingestion run records and stores source hashes and calendar
assumptions. Additional tables hold OHLC intervals, actual market segments,
economic-event details, and study metadata. Query results from SQL are the input
to analysis; the report is not computed directly from bypassed CSVs.
The portable [session-context SQL query](../sql/session_context.sql) exposes
open/closed state, next opening, and previous observed close for each event/market.

## Alignment

1. Classify each event / market as open or closed using the actual calendar.
2. Open market: reference is release time. Use the latest completed pre-release
   close, or an already observable bar open if no completed bar in this segment exists.
3. Closed market: reference is the next segment opening, including a lunch reopening
   when relevant. Baseline remains the latest observed pre-release close.
4. At nominal +1 to +24 clock hours after the reference, require the target to lie
   in a trading segment (its exact close is allowed). Select the first full bar
   ending at/after the target, at most 60 minutes later, in that same segment.
5. Otherwise record missing/closed status. Do not fill with a future reopening price.

Each record includes baseline type/time/age, next-opening wait, requested target,
actual observed time, elapsed hours since release, and simultaneous high-importance
release count. The source's exact open/close tick cannot be reconstructed from
all 1h bars, so “previous observed close” is intentionally different from official
previous-session settlement/closing price.

## Findings and limits

The [empirical results](../results/real/findings.md) report means, medians and counts.
The sample is short, and each focus family has only two or three releases. Some
releases are simultaneous and their responses cannot be independently attributed.
Later reopening observations include intervening news. Baseline windows and market
composition differ; returns are not controlled for background trends, currency,
or event surprise. Index price levels are not compared across markets.

There is no causal inference, statistical significance claim, trading strategy,
or claim of faster information incorporation. Tests verify calendar/alignment and
data processing behavior, not an economic hypothesis.

## Reproduce with sourced files

```sh
python -m pip install -r requirements-study.txt
python fetch_cash_prices.py --market NDX --start 2024-10-08 --end 2024-12-31
python study.py prepare --hsi HSI_1h_UTC.csv --stoxx STOXX50E_1h_UTC.csv --ndx data/raw/NDX_1h_yahoo.csv --events economic_calendar_data_final.csv --event-timezone UTC
python build_real_report.py
streamlit run dashboard.py
```

With a dedicated MySQL database and `DATABASE_URL` configured, add `--db mysql`
to `study.py prepare` and `build_real_report.py`; select `mysql` in Streamlit.
Other Yahoo CSVs can be acquired through `fetch_cash_prices.py` and passed to the
same importer. Date-only economic calendars must be exported with ISO dates and
the declared timezone; legacy formatted archives use the documented column names.
This exact historical snapshot requires the archived files. Yahoo intraday
retention changes, so a fresh download may fail or differ. Published hashes help
identify the original sources; raw provider datasets are deliberately not checked in.
