# syntax=docker/dockerfile:1
# Strata runner image: upstream's own image (github.com/Niko1221/Strata, its Dockerfile and docker-compose
# entrypoint) plus this repo's test gate and operator scripts. The `engine` context is upstream's image, built
# by the strata-engine service in docker-compose.yml from a pinned commit. No GPU needed to build.
#
#   docker compose build strata

FROM engine AS test
COPY scripts/benchmark.py scripts/test_benchmark.py scripts/smoke_test.py scripts/test_smoke_test.py \
     /opt/strata-runner/
# A portable build (STRATA_PORTABLE=1) must not put AVX-512 into the image encoder, which has no run-time CPU
# dispatch: it would crash with SIGILL on AVX2-only hosts. The engine is not checked this way, because its own
# AVX-512 kernels are intentional and picked at run time.
ARG STRATA_PORTABLE=1
RUN if [ "$STRATA_PORTABLE" = 1 ] && [ -e engine/strata-vision ]; then \
      zmm_count=$(objdump -d --no-show-raw-insn engine/strata-vision | grep -c '%zmm' || true); \
      echo "strata-vision AVX-512 instructions: $zmm_count"; \
      [ "$zmm_count" -eq 0 ] || { echo "strata-vision is not portable: rebuild with STRATA_PORTABLE=1"; exit 1; }; \
    fi
RUN .venv/bin/python -m unittest -v \
      serve.test_server serve.test_detok serve.test_mcp serve.test_security serve.test_lifecycle \
      tools.test_iq_pack tools.test_shards tools.test_calibrate \
  && cd /opt/strata-runner \
  && /opt/strata/.venv/bin/python -m unittest -v test_benchmark test_smoke_test \
  && touch /tests-passed

FROM engine
COPY --from=test /tests-passed /opt/strata-runner/tests-passed
COPY scripts/smoke_test.py scripts/benchmark.py /opt/strata-runner/
