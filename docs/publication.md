# Publication boundary

The root .gitignore uses an allowlist. Only maintained code, SQL, tests, workflow,
README, configuration example, these documents, and the curated synthetic
`results/` bundle and derived empirical summaries in `results/real/` are publication candidates.

Excluded: CV PDFs, original presentations and scripts, coursework notebooks (including
saved outputs), legacy Python scripts, memo.txt, original CSV datasets, generated
databases/working results, local tools, and credentials. Originals remain on disk.
`docs/presentation_public.pdf` is a revised three-page portfolio presentation:
the research question, corrected trading-session chart and SQL workflow are
described, while result plots use actual cash-index study summaries. It does not contain the
original provider screenshots, private CV, or old uncorrected result plots.
`docs/presentation_synthetic.pdf` is a separate synthetic example.

The public demo is generated from synthetic data. Historical coursework results
are not evidence for the maintained pipeline's correctness or market performance.
Do not publish provider data without checking its redistribution terms.

Before first publication, inspect `git ls-files`, staged diffs, and secret scans.
Never force-add the CV, original notebook, or excluded coursework scripts.

## Changes from coursework

- MySQL coursework is preserved locally; the maintained project supports both
  a portable SQLite demo and a MySQL/SQLAlchemy execution path.
- Credentials and personal filesystem paths are absent from maintained code.
- SQL window functions partition returns by instrument and order observations.
- Offset-aware timestamps normalize to UTC; naive timestamps fail validation.
- The event study uses completed hourly bars and rejects distant observations.
- Original Bollinger backtests are excluded. Costs, overlap, intrabar execution,
  and out-of-sample evaluation were insufficient for performance claims.
- `investpy` acquisition is historical context, not a supported current connector.
  Events enter through an explicit CSV contract; Yahoo prices have an optional connector.
