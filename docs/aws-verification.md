# AWS EC2 verification — 2026-10-07

The existing pipeline ran successfully on a temporary Ubuntu 24.04 x86_64
`t3.small` EC2 host in `eu-west-1`, using Docker Compose, MySQL 8.4 and Streamlit.
The application checkout was pinned to
`0b2b67b962c9d088b84f525b16c783972f961057`. The host used a verified active AWS
Free plan with credits; this was credit-funded validation, not a permanently
free deployment. No AWS email, account ID, access key, private key or host IP is
included in this record.

| Check | Observed result |
| --- | --- |
| Synthetic ingestion | 288 prices, 3 events, 216 valid curve observations |
| Synthetic repeated ingestion | No duplicate source rows; audit history retained |
| Actual archive import | 1,024 accepted cash-session bars and 124 timed events |
| Actual response analysis | 8,928 attempted responses; 2,380 valid |
| Cross-market SQL comparisons | 85 release clusters; 73 complete comparisons |
| Optional forecast module | 41 repeated families; 105 comparable event records |
| Actual dashboard | Streamlit script rendering passed in open/closed modes |
| HTTP health | Both demo and actual dashboard endpoints responded successfully |
| Restart persistence | Both configurations passed stop/start and audit-history checks |
| Export integrity | 20 generated artifact hashes verified after retrieval |

Both server verification commands printed `SERVER_VALIDATION_PASSED` for their
respective `demo` and `real` modes. The initial bootstrap reached the successful
application checks but failed at export because the host output directory was
absent. The export script was corrected to create the directory, then verification
was rerun successfully and exports were retrieved into ignored local working files.

## Comparison with the local study

The three price-source SHA-256 hashes matched the local snapshot exactly.
Cross-market classification counts and forecast-module coverage matched exactly.
All 212 forecast-summary groups matched on grouping keys and counts; means and
medians matched within `1e-12`. Direction percentages matched within `0.0001`
percentage points because MySQL decimal division rounds these exports differently
from SQLite floating-point division. No change in classification was observed.

The server kept dashboards on localhost and allowed SSH only from the configured
client IPv4 `/32`. Only four supplied archives were transferred to its private
input folder; raw source files and authentication data were not published.

The [deployment guide](../deploy/README.md) and scripts reproduce the workflow.
They generate a template with resource placeholders, check an active Free plan
before deployment, configure a bounded validation runtime and run the existing
application checks. Production monitoring, backup automation, public HTTPS,
scheduling and managed database/storage services were not part of this run.

## Resource lifecycle

Reports were retrieved before cleanup. CloudFormation stack deletion completed;
the EC2 instance, root volume and security group were removed. The dedicated AWS
SSH key pair was also deleted and its absence confirmed. The run does not provide
a lasting public endpoint. Local authentication and audit files remain excluded
by Git.
