#!/usr/bin/env bash
# Start or roll back to already built local images of one commit (docs/self-hosting.md, «Обновление и откат»).
# Installed by hand as /opt/video-digest/activate-image.sh; this file in the repo is the source of that copy.
# Usage: activate-image.sh <full 40-character commit SHA>
# Never builds. Uses the compose file of the release being activated, so a rollback runs with its own
# compose, prompts and sql. After a healthy start the n8n workflows of that release are imported.
set -Eeuo pipefail

APP_ROOT="${APP_ROOT:-/opt/video-digest}"
CURRENT_FILE="$APP_ROOT/current.env"
N8N_URL="http://127.0.0.1:5679"   # editor port from compose.server.yml, loopback only
SHA="${1:-}"

if [[ ! "$SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Expected a full 40-character commit SHA" >&2
  exit 2
fi

release_dir() { echo "$APP_ROOT/releases/$1"; }
compose_file() { echo "$(release_dir "$1")/infra/deploy/compose.server.yml"; }

compose_up() { # compose_up SHA -> `docker compose up` for that release, waits for running/healthy
  local sha="$1"
  # --pull missing: our SHA images are checked to exist below, so the registry is touched only for
  # third-party images (postgres, n8n, gotenberg) that are not on the host yet.
  MEDIA_IMAGE="video-digest-media:$sha" WEB_IMAGE="video-digest-web:$sha" RELEASE_DIR="$(release_dir "$sha")" \
    docker compose --project-directory "$APP_ROOT" -f "$(compose_file "$sha")" \
      up -d --no-build --pull missing --remove-orphans --wait --wait-timeout 240
}

import_workflows() { # import_workflows SHA -> n8n/scripts/import.sh of that release against the local n8n
  local sha="$1" release api_key
  release="$(release_dir "$sha")"
  api_key="$(sed -n 's/^N8N_API_KEY=//p' "$APP_ROOT/.env" | head -n 1)"
  if [[ -z "$api_key" || ! -f "$APP_ROOT/n8n-credentials.json" ]]; then
    echo "WARNING: N8N_API_KEY in .env or $APP_ROOT/n8n-credentials.json is missing;" >&2
    echo "         workflows were NOT imported. Finish the n8n first-run setup, then rerun activate-image.sh $sha" >&2
    return 0
  fi
  # /healthz turns green before the public API is mounted (n8n rebuilds its workflow index first), so wait for it.
  local i
  for i in $(seq 1 30); do
    if [[ "$(curl -s -o /dev/null -w '%{http_code}' -H "X-N8N-API-KEY: $api_key" "$N8N_URL/api/v1/workflows?limit=1")" == "200" ]]; then
      break
    fi
    if [[ "$i" -eq 30 ]]; then echo "n8n public API at $N8N_URL did not answer 200 within 60s" >&2; return 1; fi
    sleep 2
  done
  # import.sh expects the credential map next to the workflows; the release is a fresh snapshot, so copy it in.
  cp "$APP_ROOT/n8n-credentials.json" "$release/n8n/.credentials.json"
  ENV_FILE="$APP_ROOT/.env" N8N_URL="$N8N_URL" bash "$release/n8n/scripts/import.sh"
}

[[ -f "$(compose_file "$SHA")" ]] || { echo "No compose file for $SHA: $(compose_file "$SHA")" >&2; exit 2; }
docker image inspect "video-digest-media:$SHA" "video-digest-web:$SHA" >/dev/null

PREVIOUS_SHA=""
if [[ -f "$CURRENT_FILE" ]]; then
  PREVIOUS_SHA="$(sed -n 's/^SHA=//p' "$CURRENT_FILE" | head -n 1)"
fi

if ! compose_up "$SHA"; then
  echo "New release failed its container health check" >&2
  # By project name only: the compose file needs the image/release variables to even parse.
  docker compose -p video-digest ps --all >&2 || true

  if [[ "$PREVIOUS_SHA" =~ ^[0-9a-f]{40}$ && "$PREVIOUS_SHA" != "$SHA" && -f "$(compose_file "$PREVIOUS_SHA")" ]] \
     && docker image inspect "video-digest-media:$PREVIOUS_SHA" "video-digest-web:$PREVIOUS_SHA" >/dev/null 2>&1; then
    echo "Restoring $PREVIOUS_SHA" >&2
    compose_up "$PREVIOUS_SHA"
  fi

  exit 4
fi

{
  printf 'SHA=%s\n' "$SHA"
  printf 'MEDIA_IMAGE=video-digest-media:%s\n' "$SHA"
  printf 'WEB_IMAGE=video-digest-web:%s\n' "$SHA"
  printf 'RELEASE_DIR=%s\n' "$(release_dir "$SHA")"
} > "$CURRENT_FILE.tmp"
mv "$CURRENT_FILE.tmp" "$CURRENT_FILE"
echo "Activated $SHA"

# Workflows are instance state, not part of an image: sync them to the activated release.
if ! import_workflows "$SHA"; then
  echo "Containers of $SHA are running, but the n8n workflow import failed; see above" >&2
  exit 5
fi
