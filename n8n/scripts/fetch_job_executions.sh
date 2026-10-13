#!/usr/bin/env bash
# Dump the llm-call executions of one job, with data, in the shape of fetch_executions.sh ({"data": [...]}) so
# scripts/validator_harness.js reads the file as is. The job's window comes from the service's own
# GET /webhook/job-status (created_at .. finished_at); llm-call executions carry no job id, only their time.
# Response headers of the LLM calls are dropped, and the dump is refused if anything key-shaped or any
# value of infra/.env survives in it – these files are meant to be committed as calibration fixtures.
# Usage: scripts/fetch_job_executions.sh <job_id> [kind] > n8n/fixtures/clean-calibration/<name>.json
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
job="${1:?job id, e.g. j_4ac6yf}"; kind="${2:-}"
python3 - "$job" "$kind" "$ENV_FILE" <<'PY'
import json, os, re, subprocess, sys, urllib.parse
from datetime import datetime, timedelta, timezone
job, kind, env_file = sys.argv[1], sys.argv[2], sys.argv[3]
url, key = os.environ["N8N_URL"], os.environ["N8N_API_KEY"]
def api(path):
    return json.loads(subprocess.check_output(["curl", "-fsS", f"{url}/api/v1{path}", "-H", f"X-N8N-API-KEY: {key}"]))
status = json.loads(subprocess.check_output(["curl", "-fsS", f"{url}/webhook/job-status?job_id={urllib.parse.quote(job)}"]))
if not status.get("created_at"):
    sys.exit(f"job {job} not found: {json.dumps(status)[:200]}")
title = (status.get("source") or {}).get("title")
if not title:
    print(f"warning: {job} has no title (expired?) – executions of concurrent jobs may be included", file=sys.stderr)
ts = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
lo = ts(status["created_at"]) - timedelta(seconds=5)
hi = (ts(status["finished_at"]) if status.get("finished_at") else datetime.now(timezone.utc)) + timedelta(seconds=60)
wid = next((w["id"] for w in api("/workflows?limit=250")["data"] if w["name"] == "llm-call"), None)
if not wid:
    sys.exit("workflow llm-call not found in the instance")
ids, cursor = [], None
while True:
    page = api(f"/executions?workflowId={wid}&limit=250" + (f"&cursor={cursor}" if cursor else ""))
    items = page.get("data", [])
    for e in items:
        if lo <= ts(e["startedAt"]) <= hi:
            ids.append(e["id"])
    cursor = page.get("nextCursor")
    if not cursor or not items or min(ts(e["startedAt"]) for e in items) < lo:
        break
executions = []
for eid in ids:
    e = api(f"/executions/{eid}?includeData=true")
    run = ((e.get("data") or {}).get("resultData") or {}).get("runData") or {}
    try:
        state = run["Prepare"][0]["data"]["main"][0][0]["json"]
    except (KeyError, IndexError, TypeError):
        continue
    if kind and state.get("kind") != kind:
        continue
    # Concurrent jobs share the time window (MAX_CONCURRENT_JOBS = 2): keep only the calls whose prompt names
    # this job's video – the clean/map/reduce prompts carry "Video title: `...`". An expired job has no title
    # any more; then the window is all there is, and the caller is warned.
    if title and f"Video title: `{title}`" not in str(state.get("system", "")):
        continue
    # Response headers carry request ids and organisation ids, nothing the harness needs: drop them.
    for name, runs in run.items():
        for r in runs:
            for out in ((r.get("data") or {}).get("main") or []):
                for item in out or []:
                    j = item.get("json") if isinstance(item, dict) else None
                    if isinstance(j, dict) and "headers" in j and "statusCode" in j:
                        del j["headers"]
    executions.append(e)
executions.sort(key=lambda e: e["startedAt"])
dump = json.dumps({"data": executions}, ensure_ascii=False)
# Secret scan: key shapes and every non-trivial value of infra/.env.
leaks = set(re.findall(r"\b(?:sk|gsk|rk|xai)[-_][A-Za-z0-9_-]{6,}|Bearer [A-Za-z0-9._-]{8,}|Token [A-Za-z0-9._-]{8,}", dump))
# Only credential-like variables: model names and the public URL legitimately appear in the state.
SECRET_VARS = re.compile(r"(KEY|SECRET|PASSWORD|TOKEN|DATABASE_URL|SMTP_USER)", re.I)
for line in open(env_file, encoding="utf-8"):
    if "=" in line and not line.startswith("#"):
        name, v = line.split("=", 1); v = v.strip().strip('"')
        if SECRET_VARS.search(name) and len(v) >= 8 and v in dump:
            leaks.add(f"env value of {name}")
if leaks:
    sys.exit(f"refusing to dump {job}: secrets found: {sorted(leaks)}")
if not executions:
    sys.exit(f"no llm-call executions with kind={kind or 'any'} in the window of {job} ({status['created_at']} .. {status.get('finished_at')}): pruned?")
sys.stdout.write(dump + "\n")
print(f"{job}: {len(executions)} execution(s), kind={kind or 'any'}, window {status['created_at']} .. {status.get('finished_at')}", file=sys.stderr)
PY
