#!/bin/bash
# Run on the EC2 host, inside the checkout. Pass 'real' after supplying archives.
set -euo pipefail
mode="${1:-demo}"
cd /opt/economic-event-pipeline
if [ "$mode" = demo ]; then
    compose=(docker compose)
    smoke=()
elif [ "$mode" = real ]; then
    export EVENT_TIMEZONE="${EVENT_TIMEZONE:-UTC}"
    export DASHBOARD_PORT=8502
    compose=(docker compose -p economic-events-real -f compose.yaml -f compose.real.yaml)
    smoke=(--real)
else
    echo 'Usage: verify_server.sh demo|real' >&2
    exit 2
fi
"${compose[@]}" up -d --wait --wait-timeout 300
"${compose[@]}" run --rm --no-deps pipeline python docker_smoke.py "${smoke[@]}" --save-state outputs/validation-state.json
"${compose[@]}" down
"${compose[@]}" up -d --wait --wait-timeout 300
"${compose[@]}" run --rm --no-deps pipeline python docker_smoke.py "${smoke[@]}" --check-state outputs/validation-state.json
curl --fail --silent --show-error "http://127.0.0.1:${DASHBOARD_PORT:-8501}/_stcore/health"
mkdir -p "outputs/server-validation/$mode"
"${compose[@]}" cp pipeline:/app/outputs/. "./outputs/server-validation/$mode"
printf '\nSERVER_VALIDATION_PASSED mode=%s\n' "$mode"
