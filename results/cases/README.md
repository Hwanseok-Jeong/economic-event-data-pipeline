# Same release across three cash markets

Question: do markets share a direction, differ, or show larger moves at later
observation times around the same economic release?

`python build_case_report.py` calculates session-aware nominal +1h returns from
the real study database, materializes `session_responses_report`, then runs
[release_cases.sql](../../sql/release_cases.sql). Use `--db mysql` for MySQL 8;
the same query uses CTEs, conditional aggregation and `ROW_NUMBER()`.

The unit is **country + UTC release timestamp**, combining co-released indicators.
A representative event key is selected deterministically; its price windows are
identical to those of the other indicators in that cluster. Different countries
at the same timestamp remain separate and may still reflect shared news. These
are descriptive observations, not independent experimental samples.

124 event records → 85 clusters → 73 complete three-market comparisons. The 12
incomplete clusters are excluded, not assigned zero returns. Observation targets
are +1 clock hour after release when open, otherwise +1h after the next session
segment opening; the first completed hourly bar within the study's 60-minute
tolerance is used. Baselines and observation lags differ across markets. See the
[full alignment method](../../docs/real-study.md).

At the default threshold, positive means strictly above +0.1%, negative strictly
below −0.1%, and neutral includes both boundaries. Classification gives precedence
to mixed directions even if the third market is neutral. Remaining neutral cases
have no positive/negative pair. The threshold is a descriptive convention, not a
statistical significance test; sensitivity at 0%, 0.05%, 0.1% and 0.2% is exported.

Increasing magnitude requires all three non-neutral returns to share a sign,
three distinct observation times, and strictly increasing absolute returns in
that time order. Its frequency is 4/73 (5.5%), or 4/13 (30.8%) among same-direction
clusters. Different baseline lengths make this an observation about measured
returns, not proof of amplification or market-to-market transmission.

The figure selects the earliest qualifying release for each example class. Each
bar is a single market observation, ordered by actual observation time. The
[example CSV](example_observations.csv) includes indicator names, baseline age,
baseline timestamps, release/open state and observation timestamps for inspection.

![Release examples](release_examples.png)

The conclusion is descriptive: mixed directions are common in this sample, and
some later observed returns are larger. Overnight gaps, holidays, other news,
co-released indicators and index composition remain plausible explanations.
No event-surprise regression, control group or causal identification is applied.
The [manifest](manifest.json) records source provenance and artifact hashes.
