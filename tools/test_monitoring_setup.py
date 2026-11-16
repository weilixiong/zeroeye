#!/usr/bin/env python3
"""Focused validation for the recommended Prometheus alert rules.

Regression guard for the ``HighMemoryUsage`` alert, which used to compare
``process_resident_memory_bytes`` against itself (``a / a``).  That expression
evaluates to a constant ``1`` for every non-zero sample, so the alert could
never reflect real memory pressure.  These tests fail if any recommended rule
ever divides a metric by itself again.

Run with:
    python tools/test_monitoring_setup.py
"""

import contextlib
import io
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import monitoring_setup  # noqa: E402

DIVISION_RE = re.compile(r"([A-Za-z_:][A-Za-z0-9_:]*)\s*/\s*([A-Za-z_:][A-Za-z0-9_:]*)")
PAREN_DIVISION_RE = re.compile(
    r"\(\s*([A-Za-z_:][A-Za-z0-9_:]*)\s*\)\s*/\s*\(\s*([A-Za-z_:][A-Za-z0-9_:]*)\s*\)"
)


def self_dividing_metrics(expr: str):
    """Return every metric that appears as both sides of a division."""
    found = []
    for pattern in (DIVISION_RE, PAREN_DIVISION_RE):
        for match in pattern.finditer(expr):
            if match.group(1) == match.group(2):
                found.append(match.group(1))
    return found


def alert_rule(name: str):
    for rule in monitoring_setup.RECOMMENDED_ALERT_RULES:
        if rule["name"] == name:
            return rule
    raise AssertionError("recommended alert rule %r not found" % name)


class HighMemoryUsageExpression(unittest.TestCase):
    def test_high_memory_usage_does_not_divide_a_metric_by_itself(self):
        expr = alert_rule("HighMemoryUsage")["expr"]
        self.assertEqual(
            [],
            self_dividing_metrics(expr),
            "HighMemoryUsage must not divide a metric by itself: %r" % expr,
        )

    def test_no_recommended_alert_rule_self_divides(self):
        for rule in monitoring_setup.RECOMMENDED_ALERT_RULES:
            with self.subTest(rule=rule["name"]):
                self.assertEqual(
                    [],
                    self_dividing_metrics(rule["expr"]),
                    "alert %r contains a self-dividing expression: %r"
                    % (rule["name"], rule["expr"]),
                )

    def test_high_memory_usage_uses_a_meaningful_denominator(self):
        expr = alert_rule("HighMemoryUsage")["expr"]
        self.assertIn("process_resident_memory_bytes", expr)
        self.assertIn("machine_memory_bytes", expr)
        self.assertIn(">", expr)

    def test_high_memory_usage_threshold_is_preserved(self):
        expr = alert_rule("HighMemoryUsage")["expr"]
        self.assertTrue(
            expr.endswith("> 0.9"),
            "the 90%% memory threshold must stay unchanged: %r" % expr,
        )

    def test_alert_rule_shape_is_unchanged(self):
        for rule in monitoring_setup.RECOMMENDED_ALERT_RULES:
            with self.subTest(rule=rule["name"]):
                for key in ("name", "expr", "duration", "severity", "summary", "description"):
                    self.assertIn(key, rule)
                self.assertTrue(rule["expr"].strip())

    def test_expressions_are_syntactically_sane(self):
        for rule in monitoring_setup.RECOMMENDED_ALERT_RULES:
            expr = rule["expr"]
            with self.subTest(rule=rule["name"]):
                self.assertEqual(expr.count("("), expr.count(")"))
                self.assertEqual(expr.count("{"), expr.count("}"))
                self.assertEqual(expr.count("["), expr.count("]"))
                self.assertNotIn("//", expr)
                self.assertNotIn("> >", expr)


class MonitoringSetupCompatibility(unittest.TestCase):
    def test_memory_recording_rule_is_unchanged(self):
        recording = {r["name"]: r["expr"] for r in monitoring_setup.RECOMMENDED_RECORDING_RULES}
        self.assertIn("instance:memory_usage:ratio", recording)
        self.assertEqual(
            "process_resident_memory_bytes / machine_memory_bytes",
            recording["instance:memory_usage:ratio"],
        )

    def test_dry_run_output_stays_compatible(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            ok = monitoring_setup.upload_prometheus_rules(
                monitoring_setup.RECOMMENDED_ALERT_RULES,
                "http://localhost:9090",
                dry_run=True,
            )
        out = buffer.getvalue()
        self.assertTrue(ok)
        self.assertIn("Would upload", out)
        self.assertIn("groups:", out)
        self.assertIn("- name: tent_alerts", out)
        self.assertEqual(len(monitoring_setup.RECOMMENDED_ALERT_RULES), out.count("expr: "))
        for rule in monitoring_setup.RECOMMENDED_ALERT_RULES:
            self.assertIn("alert: %s" % rule["name"], out)


if __name__ == "__main__":
    unittest.main(verbosity=2)