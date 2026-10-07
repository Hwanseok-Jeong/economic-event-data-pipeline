#!/bin/bash
# Ubuntu 24.04 EC2 user data. Runs as root; contains no AWS credentials.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

# Bound this one-off validation run. Stopping does not remove the EBS volume.
shutdown -h "+${STOP_AFTER_MINUTES}"
. /etc/os-release
test "$ID" = ubuntu
test "$VERSION_ID" = 24.04
apt-get update
apt-get install -y ca-certificates curl git python3
install -m 0755 -d /etc/apt/keyrings
curl --fail --show-error --silent --location https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
usermod -aG docker ubuntu

# A small validation host uses swap while building / generating reports.
if ! swapon --show=NAME --noheadings | grep -q '^/swapfile$'; then
    if [ ! -f /swapfile ]; then
        fallocate -l 2G /swapfile
        chmod 600 /swapfile
        mkswap /swapfile
    fi
    swapon /swapfile
fi

if [ ! -d /opt/economic-event-pipeline/.git ]; then
    git clone https://github.com/Hwanseok-Jeong/economic-event-data-pipeline.git /opt/economic-event-pipeline
fi
cd /opt/economic-event-pipeline
git checkout "$SOURCE_REF"
if [ ! -f .env ]; then
    python3 - <<'PY'
import secrets
from pathlib import Path
Path('.env').write_text('MYSQL_PASSWORD='+secrets.token_hex(24)+'\nMYSQL_ROOT_PASSWORD='+secrets.token_hex(24)+'\n')
PY
    chmod 600 .env
fi
chown -R ubuntu:ubuntu /opt/economic-event-pipeline
docker compose up --build -d --wait --wait-timeout 300
bash /opt/verify-economic-events.sh demo
