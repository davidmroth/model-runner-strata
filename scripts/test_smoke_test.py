"""Unit tests for smoke_test.py's scoring; no server needed."""
import unittest

from smoke_test import check_decode_speed, check_reply_content


def reply(content="def add(a, b):\n    return a + b", predicted_per_second=55.0, predicted_n=20):
    return {"choices": [{"message": {"content": content}}],
            "timings": {"predicted_n": predicted_n, "predicted_per_second": predicted_per_second}}


class CheckReplyContentTest(unittest.TestCase):
    def test_it_passes_a_reply_that_defines_the_function(self):
        self.assertTrue(check_reply_content(reply()).passed)

    def test_it_fails_a_reply_without_the_function(self):
        self.assertFalse(check_reply_content(reply(content="I can't help with that.")).passed)

    def test_it_fails_a_reply_without_choices(self):
        self.assertFalse(check_reply_content({}).passed)


class CheckDecodeSpeedTest(unittest.TestCase):
    def test_it_passes_at_or_above_the_minimum(self):
        self.assertTrue(check_decode_speed(reply(predicted_per_second=20.0), minimum=20).passed)

    def test_it_fails_below_the_minimum(self):
        result = check_decode_speed(reply(predicted_per_second=19.9), minimum=20)
        self.assertFalse(result.passed)
        self.assertIn("19.9 tok/s", result.detail)

    def test_it_fails_a_reply_without_timings(self):
        result = check_decode_speed({"usage": {"completion_tokens": 20}})
        self.assertFalse(result.passed)
        self.assertIn("no predicted_per_second", result.detail)


if __name__ == "__main__":
    unittest.main()
