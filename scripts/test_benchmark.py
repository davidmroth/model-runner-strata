"""Unit tests for benchmark.py; no server needed."""
import unittest

from benchmark import (CASES, BenchmarkCase, Measurement, MissingTimings, build_prompt, find_regressions,
                       measurement_from_reply, run_benchmark)

SHORT = BenchmarkCase("short", 2_000)


def reply(prompt_per_second=500.0, predicted_per_second=80.0, prompt_n=2_000):
    return {"timings": {"prompt_n": prompt_n, "prompt_per_second": prompt_per_second,
                        "predicted_per_second": predicted_per_second}}


class MeasurementFromReplyTest(unittest.TestCase):
    def test_it_reads_the_server_side_speeds(self):
        self.assertEqual(measurement_from_reply(SHORT, reply()), Measurement("short", 2_000, 500.0, 80.0))

    def test_it_rejects_a_reply_without_timings(self):
        with self.assertRaisesRegex(MissingTimings, "short: reply has no prompt_per_second, predicted_per_second"):
            measurement_from_reply(SHORT, {"usage": {}})

    def test_it_rejects_a_reply_without_a_decode_speed(self):
        with self.assertRaisesRegex(MissingTimings, "predicted_per_second"):
            measurement_from_reply(SHORT, reply(predicted_per_second=None))


class BuildPromptTest(unittest.TestCase):
    def test_each_run_gets_a_different_prompt(self):
        self.assertNotEqual(build_prompt(SHORT, 1), build_prompt(SHORT, 2))

    def test_the_long_case_is_about_ten_times_the_short_case(self):
        short, long = (len(build_prompt(case, 1)) for case in CASES)
        self.assertAlmostEqual(long / short, 10, delta=1)


class RunBenchmarkTest(unittest.TestCase):
    def test_it_warms_up_once_then_reports_the_median_per_case(self):
        speeds = iter([None, 400.0, 600.0, 500.0, None, 300.0, 100.0, 200.0])
        sent = []

        def send(prompt):
            sent.append(prompt)
            return reply(prompt_per_second=next(speeds) or 1.0)

        results = run_benchmark(send, runs=3)
        self.assertEqual(len(sent), 8)
        self.assertEqual([(m.case, m.prompt_per_second) for m in results], [("short", 500.0), ("long", 200.0)])


class FindRegressionsTest(unittest.TestCase):
    baseline = [Measurement("short", 2_000, 500.0, 80.0)]

    def test_a_drop_within_tolerance_is_not_a_regression(self):
        self.assertEqual(find_regressions(self.baseline, [Measurement("short", 2_000, 476.0, 76.5)]), [])

    def test_it_reports_each_speed_that_drops_past_tolerance(self):
        regressions = find_regressions(self.baseline, [Measurement("short", 2_000, 400.0, 80.0)])
        self.assertEqual([(r.case, r.metric) for r in regressions], [("short", "prompt_per_second")])
        self.assertAlmostEqual(regressions[0].change, -0.2)

    def test_it_rejects_a_candidate_missing_a_case(self):
        with self.assertRaisesRegex(ValueError, "'short'"):
            find_regressions(self.baseline, [])


if __name__ == "__main__":
    unittest.main()
