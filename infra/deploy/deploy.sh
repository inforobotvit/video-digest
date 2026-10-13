#!/usr/bin/env bash
# Server-side deploy for Video Digest (docs/self-hosting.md, «Обновление и откат»).
# Installed by hand as /opt/video-digest/deploy.sh; this file in the repo is the source of that copy.
# Usage: deploy.sh <full 40-character commit SHA>
# Builds video-digest-media:<sha> and video-digest-web:<sha> from a clean `git archive` snapshot of the commit,
# then hands over to activate-image.sh.
set -Eeuo pipefail

APP_ROOT="${APP_ROOT:-/opt/video-digest}"
REPO_DIR="$APP_ROOT/repo"
RELEASES_DIR="$APP_ROOT/releases"
SHA="${1:-}"

if [[ ! "$SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Expected a full 40-character commit SHA" >&2
  exit 2
fi

git -C "$REPO_DIR" fetch --prune origin '+refs/heads/main:refs/remotes/origin/main'
git -C "$REPO_DIR" cat-file -e "${SHA}^{commit}"

if ! git -C "$REPO_DIR" merge-base --is-ancestor "$SHA" origin/main; then
  echo "Refusing to deploy a commit outside origin/main" >&2
  exit 3
fi

RELEASE_DIR="$RELEASES_DIR/$SHA"

if [[ ! -d "$RELEASE_DIR" ]]; then
  TEMP_RELEASE="${RELEASE_DIR}.tmp.$$"
  mkdir -p "$TEMP_RELEASE"
  git -C "$REPO_DIR" archive "$SHA" | tar -x -C "$TEMP_RELEASE"
  mv "$TEMP_RELEASE" "$RELEASE_DIR"
fi

# Build on the VPS, but always from the clean snapshot of the exact commit.
echo "Building video-digest-media:$SHA"
docker build --pull --tag "video-digest-media:$SHA" "$RELEASE_DIR/media-service"
echo "Building video-digest-web:$SHA"
# The Turnstile site key is inlined into the bundle at build time (infra/web.Dockerfile): taken from the server .env,
# never from the repository. An empty value builds a front without the widget – deploy refuses that loudly.
SITE_KEY="$(sed -n 's/^VITE_TURNSTILE_SITE_KEY=//p' "$APP_ROOT/.env" | head -n 1)"
[[ -n "$SITE_KEY" ]] || { echo "VITE_TURNSTILE_SITE_KEY is not set in $APP_ROOT/.env; the front would ship without the Turnstile widget" >&2; exit 6; }
docker build --pull --tag "video-digest-web:$SHA" --file "$RELEASE_DIR/infra/web.Dockerfile" \
  --build-arg "VITE_TURNSTILE_SITE_KEY=$SITE_KEY" "$RELEASE_DIR"

exec "$APP_ROOT/activate-image.sh" "$SHA"
