# Optional AWS EC2 validation

Status: **demo and actual sourced-study verification passed on AWS EC2 on
2026-10-07**. See the [verification record](../docs/aws-verification.md).

This extension runs the existing Compose stack on one Ubuntu 24.04 x86_64 EC2
host. CloudFormation manages the instance and SSH security group. There is no
AWS account email, password, access key or account ID in the published settings.

## Local settings and authentication

Copy `aws-config.example.json` to `aws-config.local.json` and fill the resource
settings. The local file is ignored by Git. `outputs/aws/` holds generated
templates, authentication caches and resource state and is also ignored.

Use AWS CLI v2 browser authentication (`aws login --profile economic-events`),
which uses temporary credentials. The CLI's [official installation guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
and [login reference](https://docs.aws.amazon.com/cli/latest/reference/login/)
describe setup. This project's optional portable Windows CLI is detected under
`.cloud-tools/aws-cli/Amazon/AWSCLIV2/aws.exe`; that directory is not published.

The local prepared profile uses `outputs/aws/auth/config`,
`outputs/aws/auth/credentials` and `outputs/aws/auth/login-cache`. To sign in with
that profile from PowerShell in the repository:

```powershell
$env:AWS_CONFIG_FILE = "$PWD\outputs\aws\auth\config"
$env:AWS_SHARED_CREDENTIALS_FILE = "$PWD\outputs\aws\auth\credentials"
$env:AWS_LOGIN_CACHE_DIRECTORY = "$PWD\outputs\aws\auth\login-cache"
& '.\.cloud-tools\aws-cli\Amazon\AWSCLIV2\aws.exe' login --profile economic-events --region eu-west-1
```

The deployment helper uses that cache if present, or your normal AWS CLI profile
otherwise. It never prints the signed-in identity or credentials.

## Resource settings

Choose these values from the EC2/VPC console in the configured region, or read
them with AWS CLI after authentication:

| Setting | What to supply |
| --- | --- |
| `image_id` | Current Canonical Ubuntu Server **24.04, x86_64** AMI in the region |
| `vpc_id` | VPC containing the chosen subnet |
| `subnet_id` | Public subnet with an internet-gateway route; enough free IPv4 addresses |
| `key_name` | EC2 SSH key-pair name; keep its private key only on your own PC |
| `ssh_cidr` | Your current public IPv4 with `/32`; no public dashboard/DB ingress |
| `repository_ref` | Full public Git commit hash, pinned for repeatability |
| `instance_type` | `t3.small` (2 GiB RAM + temporary swap) or `t3.medium` |
| `stop_after_minutes` | Automatic host shutdown after 30–180 minutes; default 120 |

Account email is not an input. The app needs no AWS API credentials and no
instance role because sources are supplied via SSH, not fetched from AWS storage.

## Preflight and deployment

From the repository, with Python available:

```sh
python deploy/aws_ec2.py template
python deploy/aws_ec2.py preflight
python deploy/aws_ec2.py deploy
python deploy/aws_ec2.py status
```

`template` is offline and creates no resources. `preflight` checks authentication,
the [Free Tier account-plan API](https://docs.aws.amazon.com/cli/latest/reference/freetier/get-account-plan-state.html),
an active **FREE** plan and positive remaining credits. `deploy` repeats those
checks, validates resource settings and the template with AWS, then creates the
CloudFormation stack. An unavailable API, insufficient permissions or a paid plan
blocks deployment; the script does not upgrade plans.

This is **credit-funded usage**, not a permanently free server. EC2, storage and
public IPv4 can consume credits. Shutdown bounds the running instance time but
does not remove EBS storage. A stack update can replace resources; use this
dedicated validation stack rather than an existing production stack.

## Actual verification

The bootstrap installs Docker using its [official Ubuntu repository instructions](https://docs.docker.com/engine/install/ubuntu/),
checks out the pinned application, generates random database passwords on the
server, starts the synthetic stack and checks SQL, dashboard rendering, HTTP
health and persistence across stop/start. CloudFormation completion alone does
not prove that the application passed; check cloud-init and application logs.

Use the instance IP recorded only in `outputs/aws/stack-state.json`:

```sh
ssh -i /path/to/private-key ubuntu@SERVER_IP
sudo cloud-init status --wait
sudo tail -n 80 /var/log/cloud-init-output.log
cd /opt/economic-event-pipeline
sudo bash /opt/verify-economic-events.sh demo
```

A successful run prints `SERVER_VALIDATION_PASSED mode=demo`. View Streamlit
through an SSH tunnel from your PC:

```sh
ssh -i /path/to/private-key -N -L 8503:127.0.0.1:8501 ubuntu@SERVER_IP
```

Open <http://localhost:8503>. The server exposes only SSH to your `/32` address.

For the actual historical study, transfer only the four source archives from the
[Docker guide](../docs/docker.md) into
`/opt/economic-event-pipeline/data/container-input/` using `scp`. Ensure the
container's application user can read them. Then run on the server:

```sh
cd /opt/economic-event-pipeline
sudo env EVENT_TIMEZONE=UTC bash /opt/verify-economic-events.sh real
```

The real check verifies the session-aware analysis, optional surprises, report
exports and dashboard. Tunnel to server port 8502 to view that dashboard. Copy
results back before cleanup; publish only reviewed aggregate results and a short
verification record, never authentication files or raw provider datasets.

## Stop and cleanup

The scheduled OS shutdown stops the instance. After saving desired outputs,
delete this dedicated CloudFormation stack in the AWS console to remove its
instance, root volume and security group. Stack deletion removes the server data.
An independently created SSH key pair remains separate; delete it separately if
it was made solely for this validation. Confirm resource deletion in the console.
