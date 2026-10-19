#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${ROOT_DIR}/logs"
APP_SERVICE="${APP_SERVICE:-web}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_DIR}/cvlac_enrichment_${TIMESTAMP}.log"

mkdir -p "${LOG_DIR}"

if command -v docker-compose >/dev/null 2>&1; then
	COMPOSE_CMD=(docker-compose)
else
	COMPOSE_CMD=(docker compose)
fi

cd "${ROOT_DIR}"

nohup "${COMPOSE_CMD[@]}" exec -T "${APP_SERVICE}" python manage.py enrich_researchers --cvlac-only >"${LOG_FILE}" 2>&1 < /dev/null &
PID=$!

echo "background_pid=${PID}"
echo "log_file=${LOG_FILE}"
echo "service=${APP_SERVICE}"
echo "command=python manage.py enrich_researchers --cvlac-only"
