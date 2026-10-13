# Shared helpers for n8n sync scripts. Source, do not run.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
N8N_DIR="$ROOT/n8n"
ENV_FILE="${ENV_FILE:-$ROOT/infra/.env}"
N8N_URL="${N8N_URL:-http://localhost:5678}"
CRED_MAP="$N8N_DIR/.credentials.json"

env_value() { grep -E "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2- ; }

N8N_API_KEY="${N8N_API_KEY:-$(env_value N8N_API_KEY)}"
export N8N_API_KEY N8N_URL
[ -n "$N8N_API_KEY" ] || { echo "N8N_API_KEY not found in $ENV_FILE" >&2; exit 1; }

api() { # api METHOD PATH [JSON_BODY]
  local method="$1" path="$2" body="${3:-}"
  if [ -n "$body" ]; then
    curl -fsS -X "$method" "$N8N_URL/api/v1$path" -H "X-N8N-API-KEY: $N8N_API_KEY" -H "content-type: application/json" -d "$body"
  else
    curl -fsS -X "$method" "$N8N_URL/api/v1$path" -H "X-N8N-API-KEY: $N8N_API_KEY"
  fi
}
