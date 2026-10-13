#!/usr/bin/env bash
# Save recorded executions of one workflow with their data, for scripts/validator_harness.js.
# Usage: scripts/fetch_executions.sh <workflow name> [limit] > executions.json   (default limit 40)
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
name="${1:?workflow name, e.g. llm-call}"; limit="${2:-40}"
wid=$(api GET "/workflows?limit=250" | python3 -c 'import json,sys; d=json.load(sys.stdin)["data"]; print(next((w["id"] for w in d if w["name"]==sys.argv[1]), ""))' "$name")
[ -n "$wid" ] || { echo "workflow '$name' not found" >&2; exit 1; }
api GET "/executions?workflowId=$wid&status=success&limit=$limit&includeData=true"
