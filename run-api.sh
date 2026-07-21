#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

export API_JWT_SECRET="${API_JWT_SECRET:-dev-local-nao-usar-em-producao-troque-isso}"

exec python3 -m uvicorn api.main:app --port "${API_PORT:-8001}"
