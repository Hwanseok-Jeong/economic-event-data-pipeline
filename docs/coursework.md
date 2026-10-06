# Original coursework and maintained project

The original Biological Databases project asked how global markets behaved around
economic announcements. Its data flow was:

`yfinance / investpy → pandas formatting and UTC CSVs → MySQL → SQLAlchemy queries → Streamlit`

It included economic-event records (actual/forecast/previous fields), daily and
hourly prices, MySQL table diagrams and query examples, a 1–24 hour event response
viewer, annual event heatmaps, and exploratory event-filtered Bollinger backtests.

The maintained version keeps that analytical context while adding explicit CSV
contracts, validation, transactional repeatable loads, ingestion records, and CI.
SQLite is the portable demo; MySQL is an alternate executable backend. Price
extraction uses yfinance, while economics-calendar collection through investpy is
historical context and is not currently supported as an executable connector.

The restored dashboard offers event/year selection, 1–24 hour response curves,
log or percentage returns, annual event heatmaps, valid observation counts,
underlying alignment records, and CSV export. Heatmaps now use completed hourly
bars at a selected fixed horizon (24h by default). The original daily heatmap used
calendar next-day joins and had per-instrument ordering issues; the new view must
not be described as an identical reproduction of those historical results.

Original presentations remain local. The [revised public presentation](presentation_public.pdf)
retains the question and historical MySQL design, explains the maintained schema,
and replaces old result plots with labeled synthetic examples from the pipeline.
Historical plots do not validate this refactor or establish causal impact or trading performance.
