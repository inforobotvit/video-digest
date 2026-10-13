#!/usr/bin/env bash
# Import n8n/workflows/*.json into the instance: create or update by name, resolve credential
# ids from n8n/.credentials.json and sub-workflow ids by name, then activate.
# Usage: scripts/import.sh [file ...]   (default: every file in n8n/workflows, pipeline first)
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
[ -f "$CRED_MAP" ] || { echo "$CRED_MAP missing: run scripts/credentials.sh first" >&2; exit 1; }

files=("$@")
if [ ${#files[@]} -eq 0 ]; then
  files=()
  # Sub-workflows before their callers: llm-call and log-events are called by pipeline, pipeline by jobs-api.
  for f in "$N8N_DIR"/workflows/llm-call.json "$N8N_DIR"/workflows/log-events.json "$N8N_DIR"/workflows/on-error.json "$N8N_DIR"/workflows/pipeline.json "$N8N_DIR"/workflows/*.json; do
    [ -f "$f" ] || continue
    case " ${files[*]:-} " in *" $f "*) ;; *) files+=("$f");; esac
  done
fi

python3 - "$CRED_MAP" "${files[@]:-}" <<'PY'
import json, os, subprocess, sys
cred_map = json.load(open(sys.argv[1]))
files = sys.argv[2:]
url, key = os.environ["N8N_URL"], os.environ["N8N_API_KEY"]
def curl(method, path, body=None, fail=False):
    # Errors are reported by method, path and exit status only: the raised CalledProcessError would otherwise
    # echo the whole command line, API key header included. fail=True maps HTTP errors to exit 22 (curl -f);
    # writes keep the body so n8n's own error message can be shown by call().
    # The body goes through stdin (-d @-), not the command line: Linux caps one argument at 128 KiB and
    # pipeline.json with the embedded schema is bigger – on the server the PUT failed with "Argument list too
    # long" (2026-10-04, step G), while macOS with its larger limit never showed it.
    cmd = ["curl", "-sS"] + (["-f"] if fail else []) + ["-X", method, f"{url}/api/v1{path}", "-H", f"X-N8N-API-KEY: {key}", "-H", "content-type: application/json"]
    data = None
    if body is not None:
        cmd += ["-d", "@-"]
        data = json.dumps(body).encode()
    try:
        return subprocess.check_output(cmd, input=data)
    except subprocess.CalledProcessError as e:
        raise SystemExit(f"{method} {path}: curl exited with {e.returncode}") from None

existing = {w["name"]: w["id"] for w in json.loads(curl("GET", "/workflows?limit=250", fail=True))["data"]}

def call(method, path, body=None):
    out = curl(method, path, body)
    data = json.loads(out) if out else {}
    if isinstance(data, dict) and data.get("message") and "id" not in data:
        raise SystemExit(f"{method} {path}: {data['message']}")
    return data

for path in files:
    wf = json.load(open(path, encoding="utf-8"))
    for node in wf.get("nodes", []):
        for ctype, cred in (node.get("credentials") or {}).items():
            if cred.get("name") not in cred_map:
                raise SystemExit(f"{path}: credential '{cred.get('name')}' not in {sys.argv[1]}")
            cred["id"] = cred_map[cred["name"]]
        ref = node.get("parameters", {}).get("workflowId")
        if isinstance(ref, dict) and ref.get("__rl"):
            target = ref.get("cachedResultName")
            if target not in existing:
                raise SystemExit(f"{path}: sub-workflow '{target}' not found; import it first")
            ref["value"] = existing[target]
            ref["mode"] = "list"
    settings = dict(wf.get("settings") or {})
    # settings.errorWorkflow is an instance id; the export keeps the workflow's name (see export.sh), resolved here.
    ew = settings.get("errorWorkflow")
    if ew and ew not in existing.values():
        if ew not in existing:
            raise SystemExit(f"{path}: error workflow '{ew}' not found; import it first")
        settings["errorWorkflow"] = existing[ew]
    body = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"], "settings": settings}
    if wf["name"] in existing:
        wid = existing[wf["name"]]
        call("PUT", f"/workflows/{wid}", body)
        action = "updated"
    else:
        wid = call("POST", "/workflows", body)["id"]
        existing[wf["name"]] = wid
        action = "created"
    call("POST", f"/workflows/{wid}/activate")
    print(f"{action} + activated {wf['name']} ({wid}) from {os.path.relpath(path)}")
PY
