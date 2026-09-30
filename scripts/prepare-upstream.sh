#!/bin/sh
# Checks out upstream Strata at STRATA_REF into upstream/ and applies patches/*.patch on top; the strata-engine
# service in docker-compose.yml builds upstream's Dockerfile from that folder. A patch that no longer applies
# stops the script, so a new STRATA_REF can't silently drop a fix. Needs only git (runs in alpine/git):
#
#   docker run --rm -v "$PWD:/w" -w /w --entrypoint sh alpine/git scripts/prepare-upstream.sh
set -eu

STRATA_REF="${STRATA_REF:-99f3dbd0b21d1401b3769e0c0d963913607f380b}"
UPSTREAM_URL="${UPSTREAM_URL:-https://github.com/Niko1221/Strata.git}"

repo_dir=$(cd "$(dirname "$0")/.." && pwd)
source_dir="$repo_dir/upstream"
git config --global --add safe.directory "$source_dir"

[ -d "$source_dir/.git" ] || git clone --quiet "$UPSTREAM_URL" "$source_dir"
git -C "$source_dir" fetch --quiet origin "$STRATA_REF"
git -C "$source_dir" checkout --quiet --force --detach "$STRATA_REF"
git -C "$source_dir" clean --quiet -fdx

for patch in "$repo_dir"/patches/*.patch; do
  [ -e "$patch" ] || continue
  git -C "$source_dir" apply "$patch"
  echo "applied $(basename "$patch")"
done
echo "upstream/ is at $(git -C "$source_dir" rev-parse --short HEAD) plus local patches"
