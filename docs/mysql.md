# MySQL execution path

The same validation, business keys, event alignment, and reports work against
SQLite or MySQL. MySQL uses SQLAlchemy 2 and PyMySQL, parameterized statements,
InnoDB transactions, and backend-specific upserts. MySQL DDL initializes tables
before the data transaction because DDL implicitly commits.

Install `requirements.txt`, then create a dedicated database and a dedicated user
on your MySQL 8.0.16+ / 8.4 instance. Grant that user CREATE, INDEX, SELECT, INSERT,
and UPDATE on this database only. Do not use your production database for a demo.

PowerShell:

```powershell
$env:DATABASE_URL = 'mysql+pymysql://USER:URL_ENCODED_PASSWORD@localhost:3306/market_events'
python pipeline.py demo --db mysql --output outputs/mysql_demo.csv
python pipeline.py analyze --db mysql
streamlit run dashboard.py
```

Linux/macOS:

```sh
export DATABASE_URL='mysql+pymysql://USER:URL_ENCODED_PASSWORD@localhost:3306/market_events'
python pipeline.py demo --db mysql --output outputs/mysql_demo.csv
```

Select `mysql` in the dashboard database field. For your own data, use the existing
CSV contracts and `python pipeline.py ingest --db mysql --prices ... --events ...`.
For session-aware actual analysis, use `python study.py prepare --db mysql`
with the source arguments in [the real-study guide](real-study.md), then
`python build_real_report.py --db mysql`. The study adds interval, session, event
detail and provenance tables to the core schema. Use a dedicated real-study DB.
`.env.example` is a template; the CLI does not automatically load `.env` files.
URL-encode special password characters. Never commit actual connection URLs.

The portable [window-function query](../sql/analysis.sql) works on both backends.
The optional forecast module runs with `python surprise_analysis.py --db mysql --no-plot`.
Its [summary query](../sql/surprise_summary.sql) uses the same joins, classifications,
window-based medians and conditional aggregation on SQLite and MySQL 8.
The MySQL schema is [schema_mysql.sql](../sql/schema_mysql.sql). UTC timestamps are
stored as canonical ISO text to preserve offset semantics shared with SQLite.

GitHub Actions provisions a disposable MySQL 8.4 service and tests repeated loads,
corrections, invalid batches, SQL returns, and event curves. Its password is an
ephemeral CI-only fixture, not an account credential. Local integration tests are
disabled unless `MYSQL_INTEGRATION_TEST=1`; use a fresh test database because the
test expects empty tables and writes synthetic data.
