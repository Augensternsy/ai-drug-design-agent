#!/usr/bin/env bash
set -Eeuo pipefail

BASE_URL="${1:-${BASE_URL:-http://127.0.0.1:8000}}"
BASE_URL="${BASE_URL%/}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

echo "Testing ${BASE_URL}/api/health"
curl --fail --silent --show-error --max-time 30 \
  "${BASE_URL}/api/health" \
  -o "${TMP_DIR}/health.json"

python -c 'import json, sys; payload=json.load(open(sys.argv[1], encoding="utf-8")); assert payload.get("status") == "ok", payload; assert payload.get("cuda_available") is True, payload; assert payload.get("rdkit_available") is True, payload; assert payload.get("vina_available") is True, payload; print(json.dumps(payload, indent=2, ensure_ascii=False))' "${TMP_DIR}/health.json"

echo "Testing ${BASE_URL}/api/generate"
curl --fail --silent --show-error --max-time 30 \
  -X POST "${BASE_URL}/api/generate" \
  -H 'Content-Type: application/json' \
  -d '{"target":"ESR1","num_samples":1,"run_docking":false}' \
  -o "${TMP_DIR}/generate.json"

TASK_ID="$(python -c 'import json, sys; payload=json.load(open(sys.argv[1], encoding="utf-8")); assert payload.get("status") == "queued", payload; assert payload.get("task_id"), payload; print(payload["task_id"])' "${TMP_DIR}/generate.json")"

cat "${TMP_DIR}/generate.json"
echo
echo "Generation queued successfully. Task ID: ${TASK_ID}"
echo "Check progress: curl --fail --silent --show-error ${BASE_URL}/api/tasks/${TASK_ID}"
