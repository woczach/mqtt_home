#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

if ! docker compose version >/dev/null 2>&1; then
    echo "ERROR: docker compose v2.20+ required (include: support)" >&2
    exit 1
fi

if [[ "${1:-}" == "logs" ]]; then
    docker compose logs -f --tail=100 watcher controller frontend
    exit 0
fi

docker compose pull watcher controller frontend
docker compose up -d --remove-orphans
docker compose ps

echo
echo "Stack up. Watch logs with: ./deploy.sh logs"
