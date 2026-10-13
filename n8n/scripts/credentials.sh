#!/usr/bin/env bash
# Create the credentials the workflows need (Postgres, Media, STT, LLM, Deepgram, SMTP) from infra/.env and
# record their ids in n8n/.credentials.json (gitignored). The public API cannot list credentials, so the map
# is the only link between names in workflows/*.json and ids in the instance.
# Usage: scripts/credentials.sh                 # first run on a fresh instance: create everything
#        scripts/credentials.sh --recreate      # delete every credential in the map and create all again
#        scripts/credentials.sh --only <key>    # (re)create one credential, the others stay untouched:
#                                               # keys: postgres media stt llm deepgram smtp turnstile
# --only is the point operation for a key rotation or a new provider: --recreate replaces all ids at once,
# and every workflow then needs a re-import.
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

header_cred() { # header_cred NAME HEADER VALUE
  api POST /credentials "$(python3 -c '
import json,sys
print(json.dumps({"name":sys.argv[1],"type":"httpHeaderAuth","data":{"name":sys.argv[2],"value":sys.argv[3]}}))' "$1" "$2" "$3")"
}

create_postgres() {
  api POST /credentials "$(python3 -c '
import json,sys
print(json.dumps({"name":"VideoDigest Postgres","type":"postgres","data":{"host":"postgres","port":5432,"database":sys.argv[1],"user":sys.argv[2],"password":sys.argv[3],"ssl":"disable"}}))' "$(env_value POSTGRES_DB)" "$(env_value POSTGRES_USER)" "$(env_value POSTGRES_PASSWORD)")"
}
create_media() { header_cred "Media Service API" "X-API-Key" "$(env_value MEDIA_API_KEY)"; }
create_stt() { header_cred "STT API" "Authorization" "Bearer $(env_value STT_API_KEY)"; }
create_llm() { header_cred "LLM API" "Authorization" "Bearer $(env_value LLM_API_KEY)"; }
# Deepgram authenticates with "Token <key>", not Bearer; its own credential keeps STT API on the OpenAI-compatible providers.
create_deepgram() { header_cred "Deepgram API" "Authorization" "Token $(env_value DEEPGRAM_API_KEY)"; }
create_smtp() {
  api POST /credentials "$(python3 -c '
import json,sys
print(json.dumps({"name":"SMTP","type":"smtp","data":{"host":sys.argv[1],"port":int(sys.argv[2] or 1025),"user":sys.argv[3],"password":sys.argv[4],"secure":sys.argv[5].lower()=="true"}}))' "$(env_value SMTP_HOST)" "$(env_value SMTP_PORT)" "$(env_value SMTP_USER)" "$(env_value SMTP_PASSWORD)" "$(env_value SMTP_SECURE)")"
}
# Turnstile: the secret goes into the siteverify POST body, not a header – a custom-auth credential whose json
# merges {"secret": …} into the request body (HttpRequest V3 merges customAuth.body). Never read from .env in a node.
create_turnstile() {
  api POST /credentials "$(python3 -c '
import json,sys
print(json.dumps({"name":"Turnstile","type":"httpCustomAuth","data":{"json":json.dumps({"body":{"secret":sys.argv[1]}})}}))' "$(env_value TURNSTILE_SECRET)")"
}
ALL_KEYS="postgres media stt llm deepgram smtp turnstile"

# merge_map CRED_JSON... : write name -> id into the map, replacing entries with the same name.
merge_map() {
  python3 - "$CRED_MAP" "$@" <<'PY'
import json, os, sys
out = sys.argv[1]
cur = json.load(open(out)) if os.path.exists(out) else {}
creds = [json.loads(a) for a in sys.argv[2:]]
for c in creds:
    cur[c["name"]] = c["id"]
json.dump(cur, open(out, "w"), indent=2)
print("wrote", out + ":", ", ".join(f"{c['name']} -> {c['id']}" for c in creds))
PY
}

if [ "${1:-}" = "--only" ]; then
  key="${2:-}"
  case " $ALL_KEYS " in *" $key "*) ;; *) echo "usage: $0 --only <${ALL_KEYS// /|}>" >&2; exit 1;; esac
  # The name the create function produces, to drop the old id from the instance and the map.
  name=$(python3 -c '
import sys
print({"postgres":"VideoDigest Postgres","media":"Media Service API","stt":"STT API","llm":"LLM API","deepgram":"Deepgram API","smtp":"SMTP","turnstile":"Turnstile"}[sys.argv[1]])' "$key")
  old=$(python3 -c 'import json,os,sys; m=json.load(open(sys.argv[1])) if os.path.exists(sys.argv[1]) else {}; print(m.get(sys.argv[2], ""))' "$CRED_MAP" "$name")
  if [ -n "$old" ]; then
    api DELETE "/credentials/$old" >/dev/null && echo "deleted credential $name ($old)" || echo "credential $old not found in the instance, map entry replaced" >&2
  fi
  merge_map "$(create_$key)"
  echo "re-import the workflows that use \"$name\" (scripts/import.sh) so the nodes pick up the new id"
  exit 0
fi

if [ -f "$CRED_MAP" ] && [ "${1:-}" != "--recreate" ]; then
  echo "$CRED_MAP exists; use --recreate to delete and create again, or --only <key> for one credential" >&2
  exit 0
fi
if [ -f "$CRED_MAP" ]; then
  for id in $(python3 -c 'import json,sys; print(" ".join(json.load(open(sys.argv[1])).values()))' "$CRED_MAP"); do
    api DELETE "/credentials/$id" >/dev/null && echo "deleted credential $id" || true
  done
  rm -f "$CRED_MAP"
fi

created=()
for key in $ALL_KEYS; do created+=("$(create_$key)"); done
merge_map "${created[@]}"
