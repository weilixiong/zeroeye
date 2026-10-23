#!/usr/bin/env python3
"""Regression tests for the recommended Prometheus alert expressions.

The HighMemoryUsage rule once divided ``process_resident_memory_bytes`` by
itself, which is always 1 for any non-zero sample, so the alert fired
permanently. These tests pin the corrected ratio and reject any future rule
that divides a metric by itself.
"""

import contextlib
import io
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import monitoring_setup


# A metric name with an optional label selector, e.g. ``up`` or
# ``node_filesystem_avail_bytes{mountpoint='/'}``.
METRIC = r"[A-Za-z_:][A-Za-z0-9_:]*(?:\{[^{}]*\})?"
SELF_DIVISION = re.compile(rf"(?P<metric>{METRIC})\s*/\s*(?P=metric)")
COMPARISON = re.compile(r"(?:>=|<=|==|!=|>|<)")


def alert_rules():
    return monitoring_setup.RECOMMENDED_ALERT_RULES


def expression(name):
    return next(rule["expr"] for rule in alert_rules() if rule["name"] == name)


class AlertExpressionTests(unittest.TestCase):
    def test_no_rule_divides_a_metric_by_itself(self):
        offenders = [
            rule["name"]
            for rule in alert_rules()
            if SELF_DIVISION.search(rule["expr"])
        ]
        self.assertEqual(offenders, [], f"self-dividing alert(s): {offenders}")

    def test_high_memory_usage_uses_machine_memory_as_denominator(self):
        expr = expression("HighMemoryUsage")
        self.assertIn("process_resident_memory_bytes", expr)
        self.assertIn("/ machine_memory_bytes", expr)
        self.assertNotIn(
            "process_resident_memory_bytes / process_resident_memory_bytes", expr
        )

    def test_every_alert_has_a_comparison(self):
        missing = [
            rule["name"]
            for rule in alert_rules()
            if not COMPARISON.search(rule["expr"])
        ]
        self.assertEqual(missing, [], f"alert(s) without a comparison: {missing}")

    def test_dry_run_renders_the_corrected_expression(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            ok = monitoring_setup.upload_prometheus_rules(
                alert_rules(), "http://localhost:9090", dry_run=True
            )
        self.assertTrue(ok)
        rendered = output.getvalue()
        self.assertIn(
            "expr: process_resident_memory_bytes / machine_memory_bytes > 0.9",
            rendered,
        )
        self.assertNotIn(
            "process_resident_memory_bytes / process_resident_memory_bytes",
            rendered,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
