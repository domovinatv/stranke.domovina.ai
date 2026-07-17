#!/usr/bin/env bash
# Upload standardized party square icons to R2 bucket p-ff-hr (https://p.ff.hr).
#
# Layout (mirrors c.ff.hr club_square for klubovi):
#   party_square/{slug}.png            1024 opaque icon (iOS/general)
#   party_square/maskable/{slug}.png   Android adaptive safe zone
#
# Idempotent overwrite (icons are deterministic renders). Run after 15 + 16.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
export CLOUDFLARE_ACCOUNT_ID="${CLOUDFLARE_ACCOUNT_ID:-3fa39143e7155266b2ee5b9cb06e755f}"
BUCKET="p-ff-hr"
CACHE="public, max-age=2592000"
JOBS=4

cd "$REPO_ROOT"

put_one() { # "key|file"
  local key file
  IFS="|" read -r key file <<< "$1"
  npx --yes wrangler r2 object put "$BUCKET/$key" --file "$file" --remote \
    --content-type "image/png" --cache-control "$CACHE" >/dev/null \
    && echo "put $key" || echo "FAIL $key" >&2
}
export -f put_one
export BUCKET CACHE

emit() {
  for f in data/export/party_square/*.png; do
    [ -f "$f" ] || continue
    echo "party_square/$(basename "$f")|$f"
  done
  for f in data/export/party_square/maskable/*.png; do
    [ -f "$f" ] || continue
    echo "party_square/maskable/$(basename "$f")|$f"
  done
}

emit | xargs -P "$JOBS" -I {} bash -c 'put_one "$@"' _ {}
echo "done."
