#!/usr/bin/env python3
"""
Unit tests for monitoring_setup.py and alert rule validations.
"""

import io
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Add tools directory to path
TOOLS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

import monitoring_setup
from monitoring_setup import (
    RECOMMENDED_ALERT_RULES,
    RECOMMENDED_RECORDING_RULES,
    validate_self_dividing_expressions,
    upload_prometheus_rules,
)


class TestMonitoringSetup(unittest.TestCase):
    """Test suite for monitoring setup alert rules and validation."""

    def test_high_memory_usage_rule_not_self_dividing(self):
        """Verify HighMemoryUsage does not divide process_resident_memory_bytes by itself."""
        memory_rules = [r for r in RECOMMENDED_ALERT_RULES if r.get("name") == "HighMemoryUsage"]
        self.assertEqual(len(memory_rules), 1, "HighMemoryUsage rule must exist")

        rule = memory_rules[0]
        expr = rule.get("expr", "")

        # Must not be self-dividing
        self.assertNotIn(
            "process_resident_memory_bytes / process_resident_memory_bytes",
            expr,
            "HighMemoryUsage must not divide process_resident_memory_bytes by itself",
        )

        # Must use node_memory_MemTotal_bytes as the denominator
        self.assertIn("node_memory_MemTotal_bytes", expr)
        self.assertEqual(
            expr,
            "process_resident_memory_bytes / node_memory_MemTotal_bytes > 0.9",
        )

    def test_all_recommended_alert_rules_pass_validation(self):
        """Verify all default RECOMMENDED_ALERT_RULES pass self-dividing validation cleanly."""
        errors = validate_self_dividing_expressions(RECOMMENDED_ALERT_RULES)
        self.assertEqual(errors, [], f"Expected 0 validation errors, got: {errors}")

    def test_validate_detects_self_dividing_metric(self):
        """Verify validate_self_dividing_expressions catches metric / metric."""
        bad_rules = [
            {
                "name": "HighMemoryUsageRegression",
                "expr": "process_resident_memory_bytes / process_resident_memory_bytes > 0.9",
            }
        ]
        errors = validate_self_dividing_expressions(bad_rules)
        self.assertEqual(len(errors), 1)
        self.assertIn("HighMemoryUsageRegression", errors[0])
        self.assertIn("self-dividing expression", errors[0])

    def test_validate_detects_self_dividing_with_labels(self):
        """Verify validate_self_dividing_expressions catches metric{...} / metric{...}."""
        bad_rules = [
            {
                "name": "BadLabelDivision",
                "expr": 'node_cpu_seconds{mode="idle"} / node_cpu_seconds{mode="idle"} > 0.5',
            }
        ]
        errors = validate_self_dividing_expressions(bad_rules)
        self.assertEqual(len(errors), 1)
        self.assertIn("BadLabelDivision", errors[0])

    def test_validate_detects_self_dividing_rate_expression(self):
        """Verify validate_self_dividing_expressions catches rate(...) / rate(...) identical operands."""
        bad_rules = [
            {
                "name": "BadRateRatio",
                "expr": "sum(rate(errors_total[5m])) / sum(rate(errors_total[5m])) > 0.1",
            }
        ]
        errors = validate_self_dividing_expressions(bad_rules)
        self.assertEqual(len(errors), 1)
        self.assertIn("BadRateRatio", errors[0])

    def test_validate_allows_valid_ratio_expressions(self):
        """Verify validate_self_dividing_expressions does not flag legitimate ratios."""
        valid_rules = [
            {
                "name": "LegitMemoryRatio",
                "expr": "process_resident_memory_bytes / node_memory_MemTotal_bytes > 0.9",
            },
            {
                "name": "LegitDiskRatio",
                "expr": "node_filesystem_avail_bytes{mountpoint='/'} / node_filesystem_size_bytes{mountpoint='/'} < 0.1",
            },
            {
                "name": "LegitErrorRate",
                "expr": "sum(rate(http_errors_total[5m])) / sum(rate(http_requests_total[5m])) > 0.05",
            },
            {
                "name": "LegitRecordingMemoryRatio",
                "expr": "process_resident_memory_bytes / machine_memory_bytes",
            },
        ]
        errors = validate_self_dividing_expressions(valid_rules)
        self.assertEqual(errors, [])

    def test_upload_prometheus_rules_dry_run(self):
        """Verify upload_prometheus_rules works in dry-run mode and prints updated rules."""
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            result = upload_prometheus_rules(
                RECOMMENDED_ALERT_RULES, "http://localhost:9090", dry_run=True
            )
        self.assertTrue(result)
        output = buf.getvalue()
        self.assertIn("HighMemoryUsage", output)
        self.assertIn(
            "process_resident_memory_bytes / node_memory_MemTotal_bytes > 0.9",
            output,
        )

    @patch("monitoring_setup.http_request")
    def test_validate_cli_flag_integration(self, mock_http):
        """Verify --validate flag runs expression validation and checks services."""
        mock_http.return_value = {"status": "success"}

        test_args = ["monitoring_setup.py", "--validate"]
        with patch.object(sys, "argv", test_args):
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                exit_code = monitoring_setup.main()

            self.assertEqual(exit_code, 0)
            output = buf.getvalue()
            self.assertIn("Alert rules expression validation: OK", output)

    @patch("monitoring_setup.http_request")
    def test_validate_cli_flag_fails_on_regression(self, mock_http):
        """Verify --validate flag fails when a self-dividing expression is present."""
        mock_http.return_value = {"status": "success"}

        buggy_rules = [
            {
                "name": "HighMemoryUsage",
                "expr": "process_resident_memory_bytes / process_resident_memory_bytes > 0.9",
            }
        ]
        with patch.object(monitoring_setup, "RECOMMENDED_ALERT_RULES", buggy_rules):
            test_args = ["monitoring_setup.py", "--validate"]
            with patch.object(sys, "argv", test_args):
                buf = io.StringIO()
                with patch("sys.stdout", buf):
                    exit_code = monitoring_setup.main()

                self.assertEqual(exit_code, 1)
                output = buf.getvalue()
                self.assertIn("EXPRESSION ERROR", output)


if __name__ == "__main__":
    unittest.main()
