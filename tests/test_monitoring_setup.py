"""Offline regressions for default monitoring rules and safe dry-run output."""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("monitoring_setup", ROOT / "tools/monitoring_setup.py")
monitoring = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitoring)


class MemoryAlertTests(unittest.TestCase):
    def test_memory_capacity_is_an_independent_positive_denominator(self):
        rule = next(r for r in monitoring.RECOMMENDED_ALERT_RULES if r["name"] == "HighMemoryUsage")
        self.assertNotRegex(rule["expr"], r"process_resident_memory_bytes\s*/\s*process_resident_memory_bytes")
        self.assertRegex(rule["expr"], r"machine_memory_bytes\s*>\s*0")
        self.assertEqual(rule["duration"], "10m")
        self.assertEqual(rule["severity"], "warning")

    def test_dry_run_renders_defaults_without_network_or_file_writes(self):
        output = io.StringIO()
        with mock.patch.object(monitoring, "http_request", side_effect=AssertionError("network")), mock.patch("builtins.open", side_effect=AssertionError("write")), contextlib.redirect_stdout(output):
            self.assertTrue(monitoring.upload_prometheus_rules(monitoring.RECOMMENDED_ALERT_RULES, "http://unused.invalid", dry_run=True))
        text = output.getvalue()
        self.assertIn("Would upload 12 rules", text)
        self.assertEqual(text.count("      - alert:"), 12)
        for rule in monitoring.RECOMMENDED_ALERT_RULES:
            self.assertIn("        expr: " + rule["expr"], text)
        self.assertIn("        for: 10m", text)

    def test_alerts_cli_preserves_offline_dry_run(self):
        result = subprocess.run([sys.executable, str(ROOT / "tools/monitoring_setup.py"), "--alerts", "--dry-run"], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Would upload 12 rules", result.stdout)
        self.assertIn("HighMemoryUsage", result.stdout)
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
