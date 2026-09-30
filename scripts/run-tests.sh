#!/bin/sh
# Test gate for the image this repo runs: upstream's own server tests, then this repo's tests.
# No GPU is needed - both are plain Python. Run it before switching a live engine to a new version.
#
#   STRATA_VERSION=0.2.9 ./scripts/run-tests.sh
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="ghcr.io/niko1221/strata:${STRATA_VERSION:-0.2.9}-cuda13"
PY=/opt/strata/terminal/python/bin/python3

echo "== upstream server tests =="
docker run --rm -e PYTHONPATH=/opt/strata/terminal "$IMAGE" \
  sh -c "cd /opt/strata/terminal && $PY -m unittest discover -s serve -p 'test_*.py'"

echo "== this repo's tests =="
docker run --rm -v "$ROOT/scripts:/scripts:ro" -e PYTHONPATH=/scripts "$IMAGE" \
  sh -c "$PY -m unittest test_smoke_test test_benchmark"
