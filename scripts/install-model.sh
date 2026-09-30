#!/bin/sh
# Download and prepare a model onto the /data volume without serving it, so a running engine keeps serving while
# the next model installs (docker compose --profile install run --rm strata-install). Upstream's entrypoint has no
# setup-only mode (it always starts the server afterwards); this is its setup branch with the start left out.
# Switching to the installed model is then a .env change (STRATA_FAMILY / STRATA_MODEL) and a restart.
set -e
cd /opt/strata || exit 1

STRATA_DATA="${STRATA_DATA:-/data}"
: "${FAMILY:?set STRATA_INSTALL_FAMILY (qwen, swift, coder, unsloth)}"
: "${MODEL:?set STRATA_INSTALL_MODEL (e.g. IQ3_XXS)}"

# The config name the entrypoint looks for at start: strata-<family>-<model>.json, no family tag for qwen.
case "$FAMILY" in qwen) prefix="" ;; *) prefix="${FAMILY}-" ;; esac
tag="${prefix}$(printf '%s' "$MODEL" | tr '[:upper:]' '[:lower:]')"
mkdir -p "$STRATA_DATA/config"

set -- --family "$FAMILY" --model "$MODEL" --context "${CONTEXT:-32768}" --vision "${VISION:-no}" \
  --data-dir "$STRATA_DATA" --host "${HOST:-0.0.0.0}" --api-key "${API_KEY:-}" \
  --port "${PORT:-8080}" --no-start --low-ram "${LOW_RAM:-auto}"
if [ -n "${KV:-}" ]; then set -- "$@" --kv "$KV"; fi
if [ -n "${GPUS:-}" ]; then set -- "$@" --gpus "$GPUS"; fi
.venv/bin/python setup.py --setup --yes "$@"

cp -f "/opt/strata/strata-$tag.json" "$STRATA_DATA/config/strata-$tag.json"
echo "Installed $tag: $STRATA_DATA/config/strata-$tag.json"
