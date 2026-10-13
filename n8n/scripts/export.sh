#!/usr/bin/env bash
# Export workflows from the instance into n8n/workflows/<name>.json without instance-specific
# data: ids, timestamps, credential ids, sub-workflow ids. Names are the stable keys.
# Usage: scripts/export.sh [name ...]   (default: every workflow in the instance)
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

python3 - "$N8N_DIR/workflows" "$@" <<'PY'
import json, os, re, subprocess, sys
out_dir, wanted = sys.argv[1], set(sys.argv[2:])
url, key = os.environ["N8N_URL"], os.environ["N8N_API_KEY"]
listing = json.loads(subprocess.check_output(["curl", "-fsS", f"{url}/api/v1/workflows?limit=250", "-H", f"X-N8N-API-KEY: {key}"]))["data"]

# n8n 2.x also returns activeVersion (a full copy of the nodes, credential ids included), nodeGroups,
# sourceWorkflowId and description: instance state, not workflow source.
STRIP_TOP = {"id", "versionId", "createdAt", "updatedAt", "staticData", "pinData", "shared", "homeProject",
             "tags", "meta", "isArchived", "activeVersionId", "versionCounter", "triggerCount", "active",
             "activeVersion", "nodeGroups", "sourceWorkflowId", "description"}

def fetch(wid):
    return json.loads(subprocess.check_output(["curl", "-fsS", f"{url}/api/v1/workflows/{wid}", "-H", f"X-N8N-API-KEY: {key}"]))

def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

# Test flows live in the instance (inactive) but not in workflows/: n8n/testing/ holds their source.
SKIP_NAMES = {"provider-stub"}

for w in listing:
    if wanted and w["name"] not in wanted:
        continue
    if w["name"] in SKIP_NAMES and not wanted:
        continue
    full = fetch(w["id"])
    clean = {k: v for k, v in full.items() if k not in STRIP_TOP}
    for node in clean.get("nodes", []):
        for cred in (node.get("credentials") or {}).values():
            cred.pop("id", None)                       # keep the name only
        params = node.get("parameters", {})
        wf = params.get("workflowId")
        if isinstance(wf, dict) and wf.get("__rl"):    # Execute Workflow: keep the name only
            wf["value"] = ""
            wf["mode"] = "list"
    clean["settings"] = clean.get("settings") or {}
    ew = clean["settings"].get("errorWorkflow")             # Error Workflow: keep the name, not the instance id
    if ew:
        clean["settings"]["errorWorkflow"] = next((w2["name"] for w2 in listing if w2["id"] == ew), ew)
    path = os.path.join(out_dir, f"{slug(w['name'])}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(clean, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"exported {w['name']} -> {os.path.relpath(path)}")
PY
