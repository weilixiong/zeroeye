#!/usr/bin/env python3
"""Regression tests for monitoring_setup alert rules.

Ensures the HighMemoryUsage alert expresses a real memory ratio
(resident memory vs total machine memory) and never self-divides.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import monitoring_setup as ms


class TestAlertExpressions(unittest.TestCase):

    def _find_rule(self, name):
        for rule in ms.RECOMMENDED_ALERT_RULES:
            if rule.get("name") == name:
                return rule
        self.fail(f"alert rule '{name}' not found")

    def test_high_memory_usage_not_self_dividing(self):
        rule = self._find_rule("HighMemoryUsage")
        expr = rule["expr"]
        # Must compare two distinct metrics; must NOT divide a metric by itself.
        self.assertNotIn(
            "process_resident_memory_bytes / process_resident_memory_bytes",
            expr,
            "HighMemoryUsage must not self-divide",
        )
        # Should compare resident memory against a total/available memory metric.
        self.assertIn("machine_memory_bytes", expr)
        self.assertIn("/", expr)

    def test_high_memory_usage_threshold(self):
        rule = self._find_rule("HighMemoryUsage")
        self.assertIn("> 0.9", rule["expr"])


if __name__ == "__main__":
    unittest.main()
