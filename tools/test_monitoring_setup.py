"""Focused regression tests for monitoring alert rules.

Covers issue: HighMemoryUsage must not divide a metric by itself.
Run: python3 -m unittest tools.test_monitoring_setup -v
"""
import unittest

from tools.monitoring_setup import (
    RECOMMENDED_ALERT_RULES,
    find_self_dividing_alerts,
    validate_alert_rules,
)


class TestAlertRules(unittest.TestCase):
    def test_high_memory_usage_not_self_dividing(self):
        rule = next(
            r for r in RECOMMENDED_ALERT_RULES if r["name"] == "HighMemoryUsage"
        )
        expr = rule["expr"]
        self.assertNotIn(
            "process_resident_memory_bytes / process_resident_memory_bytes",
            expr,
        )
        self.assertIn("process_resident_memory_bytes", expr)
        self.assertIn("machine_memory_bytes", expr)

    def test_no_self_dividing_rules_in_defaults(self):
        self.assertEqual(find_self_dividing_alerts(RECOMMENDED_ALERT_RULES), [])
        self.assertTrue(validate_alert_rules(RECOMMENDED_ALERT_RULES))

    def test_detector_catches_self_division(self):
        bad = [{"name": "Bad", "expr": "foo_bytes / foo_bytes > 0.9"}]
        self.assertEqual(find_self_dividing_alerts(bad), ["Bad"])
        self.assertFalse(validate_alert_rules(bad))


if __name__ == "__main__":
    unittest.main()
