"""Scored end-to-end check of a running Strata server: health, a real chat reply, and server-side decode speed.

Runs with the standard library only, so it works inside the engine container:

    docker exec -i model-runner-strata /opt/strata/.venv/bin/python - < scripts/smoke_test.py

Exit code 0 only when every check passes.  Tunables (env): STRATA_BASE_URL, STRATA_MIN_TOKENS_PER_SECOND,
STRATA_HEALTH_TIMEOUT_SECONDS.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

BASE_URL = os.environ.get("STRATA_BASE_URL", "http://127.0.0.1:8080")
MIN_TOKENS_PER_SECOND = float(os.environ.get("STRATA_MIN_TOKENS_PER_SECOND", "20"))
HEALTH_TIMEOUT_SECONDS = float(os.environ.get("STRATA_HEALTH_TIMEOUT_SECONDS", "10"))
CHAT_TIMEOUT_SECONDS = 300
CODING_PROMPT = "Write a Python function add(a, b) that returns the sum of two numbers. Reply with code only."


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def request_json(path: str, payload: dict | None, timeout: float) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE_URL + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read() or b"{}")


def check_health() -> CheckResult:
    started = time.monotonic()
    try:
        request_json("/health", None, HEALTH_TIMEOUT_SECONDS)
    except (urllib.error.URLError, OSError, ValueError) as err:
        return CheckResult("health", False, f"/health failed: {err}")
    return CheckResult("health", True, f"/health answered in {(time.monotonic() - started) * 1000:.0f} ms")


def check_reply_content(reply: dict) -> CheckResult:
    content = ((reply.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    has_function = "def add" in content
    return CheckResult("chat", has_function, f"{len(content)} chars, contains 'def add': {has_function}")


def check_decode_speed(reply: dict, minimum: float = MIN_TOKENS_PER_SECOND) -> CheckResult:
    """Decode speed from the server's own `timings`, so time spent queued behind live traffic doesn't count."""
    timings = reply.get("timings") or {}
    tokens_per_second = timings.get("predicted_per_second")
    if not tokens_per_second:
        return CheckResult("speed", False, f"reply has no predicted_per_second in timings={timings!r}")
    return CheckResult("speed", tokens_per_second >= minimum,
                       f"{timings.get('predicted_n', '?')} tokens at {tokens_per_second:.1f} tok/s "
                       f"(minimum {minimum:.0f}, server-side decode only)")


def check_chat_and_speed() -> list[CheckResult]:
    payload = {"model": "strata", "max_tokens": 256, "temperature": 0, "reasoning_effort": "off",
               "messages": [{"role": "user", "content": CODING_PROMPT}]}
    try:
        reply = request_json("/v1/chat/completions", payload, CHAT_TIMEOUT_SECONDS)
    except (urllib.error.URLError, OSError, ValueError) as err:
        return [CheckResult("chat", False, f"chat request failed: {err}")]
    return [check_reply_content(reply), check_decode_speed(reply)]


def main() -> int:
    health = check_health()
    results = [health] + (check_chat_and_speed() if health.passed else [])
    for result in results:
        print(f"[{'PASS' if result.passed else 'FAIL'}] {result.name}: {result.detail}")
    passed = sum(r.passed for r in results)
    print(f"score: {passed}/3")
    return 0 if passed == 3 else 1


if __name__ == "__main__":
    sys.exit(main())
