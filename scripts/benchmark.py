"""Repeatable speed benchmark for a running Strata server, and a comparison between two runs.

Speeds come from the server's own `timings` (llama.cpp's field names), so network and client time don't count.
Standard library only, so `run` works inside the engine container:

    docker exec -i model-runner-strata /opt/strata/.venv/bin/python - run < scripts/benchmark.py > before.json
    python3 scripts/benchmark.py compare before.json after.json     # exit 1 when any speed drops > 5 %

Tunables (env): STRATA_BASE_URL, STRATA_API_KEY.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

BASE_URL = os.environ.get("STRATA_BASE_URL", "http://127.0.0.1:8080")
REQUEST_TIMEOUT_SECONDS = 600
MAX_ANSWER_TOKENS = 256
DEFAULT_TOLERANCE = 0.05
SPEED_METRICS = ("prompt_per_second", "predicted_per_second")
# Roughly 60 tokens per block; the server reports the exact prompt size.
FILLER_BLOCK = ("def step_{n}(values):\n    total = sum(v * {n} for v in values if v % 3 != {m})\n"
                "    return total // max(1, len(values))\n\n")


class MissingTimings(RuntimeError):
    """The server's reply has no `timings`, so its speed can't be read."""


@dataclass(frozen=True)
class BenchmarkCase:
    name: str
    approx_prompt_tokens: int


@dataclass(frozen=True)
class Measurement:
    case: str
    prompt_tokens: int
    prompt_per_second: float
    predicted_per_second: float


@dataclass(frozen=True)
class Regression:
    case: str
    metric: str
    baseline: float
    candidate: float

    @property
    def change(self) -> float:
        return self.candidate / self.baseline - 1


CASES = (BenchmarkCase("short", 2_000), BenchmarkCase("long", 20_000))


def build_prompt(case: BenchmarkCase, run: int) -> str:
    """A code-review prompt of about `approx_prompt_tokens`; `run` makes each prompt unique so no cache helps."""
    blocks = max(1, case.approx_prompt_tokens // 60)
    code = "".join(FILLER_BLOCK.format(n=n + run * blocks, m=n % 3) for n in range(blocks))
    return f"Run {run}. Summarise what this module does in five bullet points.\n\n{code}"


def measurement_from_reply(case: BenchmarkCase, reply: dict) -> Measurement:
    """Read one reply's server-side speeds.

    Raises:
        MissingTimings: when the reply lacks the prompt or decode speed.
    """
    timings = reply.get("timings") or {}
    missing = [metric for metric in SPEED_METRICS if not timings.get(metric)]
    if missing:
        raise MissingTimings(f"{case.name}: reply has no {', '.join(missing)} in timings={timings!r}")
    return Measurement(case.name, int(timings.get("prompt_n") or 0),
                       float(timings["prompt_per_second"]), float(timings["predicted_per_second"]))


def median_measurement(samples: list[Measurement]) -> Measurement:
    return Measurement(samples[0].case, int(statistics.median(s.prompt_tokens for s in samples)),
                       statistics.median(s.prompt_per_second for s in samples),
                       statistics.median(s.predicted_per_second for s in samples))


def post_chat(prompt: str) -> dict:
    payload = {"model": "strata", "max_tokens": MAX_ANSWER_TOKENS, "temperature": 0, "reasoning_effort": "off",
               "messages": [{"role": "user", "content": prompt}]}
    headers = {"Content-Type": "application/json"}
    if os.environ.get("STRATA_API_KEY"):
        headers["Authorization"] = f"Bearer {os.environ['STRATA_API_KEY']}"
    req = urllib.request.Request(BASE_URL + "/v1/chat/completions", data=json.dumps(payload).encode(),
                                 headers=headers)
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read())


def run_benchmark(send: Callable[[str], dict], runs: int) -> list[Measurement]:
    """One warm-up request, then the median of `runs` requests, per case."""
    results = []
    for case in CASES:
        send(build_prompt(case, run=0))
        samples = [measurement_from_reply(case, send(build_prompt(case, run))) for run in range(1, runs + 1)]
        results.append(median_measurement(samples))
    return results


def find_regressions(baseline: list[Measurement], candidate: list[Measurement],
                     tolerance: float = DEFAULT_TOLERANCE) -> list[Regression]:
    """Every speed in `candidate` more than `tolerance` below the same case's speed in `baseline`."""
    by_case = {m.case: m for m in candidate}
    regressions = []
    for before in baseline:
        after = by_case.get(before.case)
        if after is None:
            raise ValueError(f"candidate has no {before.case!r} case")
        for metric in SPEED_METRICS:
            old, new = getattr(before, metric), getattr(after, metric)
            if new < old * (1 - tolerance):
                regressions.append(Regression(before.case, metric, old, new))
    return regressions


def load_measurements(path: Path) -> list[Measurement]:
    return [Measurement(**entry) for entry in json.loads(path.read_text())]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="benchmark the server and print JSON")
    run.add_argument("--runs", type=int, default=3)
    compare = commands.add_parser("compare", help="exit 1 when the candidate is slower than the baseline")
    compare.add_argument("baseline", type=Path)
    compare.add_argument("candidate", type=Path)
    compare.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "run":
        print(json.dumps([asdict(m) for m in run_benchmark(post_chat, args.runs)], indent=2))
        return 0
    baseline, candidate = load_measurements(args.baseline), load_measurements(args.candidate)
    for before, after in zip(baseline, candidate):
        for metric in SPEED_METRICS:
            print(f"{before.case:>5} {metric:<21} {getattr(before, metric):7.1f} -> {getattr(after, metric):7.1f}")
    regressions = find_regressions(baseline, candidate, args.tolerance)
    for r in regressions:
        print(f"SLOWER: {r.case} {r.metric} {r.change:+.1%}")
    print("result: " + ("FAIL" if regressions else "PASS"))
    return 1 if regressions else 0


if __name__ == "__main__":
    sys.exit(main())
