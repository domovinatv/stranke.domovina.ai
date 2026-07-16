#!/usr/bin/env bash
# Upload the party logo catalog to R2 bucket p-ff-hr (served at https://p.ff.hr).
#
# Layout (mirrors c.ff.hr for klubovi):
#   logos/{slug}.png           web default (<=512, quantized)
#   logos/{size}/{slug}.png    size ladder 192/256/512/1024
#   originals/{slug}.{ext}     source of truth (SVG kept as vector)
#   index.json                 machine index (logo, original, svg, sizes, brand_color)
#
# Additive: skips keys already in the remote index.json unless --force.
# Uses the wrangler OAuth login; CLOUDFLARE_ACCOUNT_ID is the ff.hr account.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
export CLOUDFLARE_ACCOUNT_ID="${CLOUDFLARE_ACCOUNT_ID:-3fa39143e7155266b2ee5b9cb06e755f}"
export BUCKET="p-ff-hr"
FORCE="${1:-}"
export CACHE="public, max-age=2592000"
JOBS=4

cd "$REPO_ROOT"

SKIP_FILE="$(mktemp)"
if [ "$FORCE" != "--force" ]; then
  npx --yes wrangler r2 object get "$BUCKET/index.json" --pipe 2>/dev/null \
    | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for slug, e in d.items():
    print(e['logo']); print(e['original'])
    for s in e.get('sizes', []):
        print(f'logos/{s}/{slug}.png')
" > "$SKIP_FILE" || true
fi

put_one() { # "key|file|content_type"
  local key file ct
  IFS="|" read -r key file ct <<< "$1"
  npx --yes wrangler r2 object put "$BUCKET/$key" --file "$file" --remote \
    --content-type "$ct" --cache-control "$CACHE" >/dev/null \
    && echo "put $key" || echo "FAIL $key" >&2
}
export -f put_one

emit() {
  for f in data/logos/*.png; do
    echo "logos/$(basename "$f")|$f|image/png"
  done
  for size in 192 256 512 1024; do
    [ -d "data/logos_sized/$size" ] || continue
    for f in data/logos_sized/$size/*.png; do
      [ -e "$f" ] || continue
      echo "logos/$size/$(basename "$f")|$f|image/png"
    done
  done
  for f in data/logos_orig/*; do
    case "$f" in
      *.svg) ct="image/svg+xml" ;;
      *.png) ct="image/png" ;;
      *.jpg) ct="image/jpeg" ;;
      *.gif) ct="image/gif" ;;
      *.webp) ct="image/webp" ;;
      *) continue ;;
    esac
    echo "originals/$(basename "$f")|$f|$ct"
  done
}

# Filter out keys already uploaded (done in THIS shell — bash arrays/functions
# don't survive into xargs subshells) and upload the rest in parallel.
emit | { grep -vFf "$SKIP_FILE" || true; } \
  | xargs -P "$JOBS" -I{} bash -c 'put_one "$@"' _ {}

npx --yes wrangler r2 object put "$BUCKET/index.json" --file data/logos_index.json \
  --remote --content-type "application/json" \
  --cache-control "public, max-age=3600" >/dev/null && echo "put index.json"

rm -f "$SKIP_FILE"
echo "✓ done — verify at https://p.ff.hr/index.json"
