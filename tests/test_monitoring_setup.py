import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import monitoring_setup


class MonitoringSetupRuleTests(unittest.TestCase):
    def test_recommended_alert_rules_do_not_self_divide(self):
        self.assertEqual(
            monitoring_setup.validate_alert_rules(
                monitoring_setup.RECOMMENDED_ALERT_RULES
            ),
            [],
        )

    def test_high_memory_alert_uses_machine_memory_denominator(self):
        high_memory_rule = next(
            rule for rule in monitoring_setup.RECOMMENDED_ALERT_RULES
            if rule["name"] == "HighMemoryUsage"
        )

        self.assertIn("process_resident_memory_bytes", high_memory_rule["expr"])
        self.assertIn("machine_memory_bytes", high_memory_rule["expr"])
        self.assertNotIn(
            "process_resident_memory_bytes / process_resident_memory_bytes",
            high_memory_rule["expr"],
        )

    def test_validation_rejects_self_dividing_alert_expression(self):
        invalid_rules = [{
            "name": "BadMemoryUsage",
            "expr": (
                "process_resident_memory_bytes{job='api'} / "
                "process_resident_memory_bytes{job='api'} > 0.9"
            ),
        }]

        self.assertEqual(
            monitoring_setup.validate_alert_rules(invalid_rules),
            [
                "BadMemoryUsage: expression divides "
                "process_resident_memory_bytes by itself"
            ],
        )

    def test_dry_run_rejects_invalid_self_dividing_rule(self):
        invalid_rules = [{
            "name": "BadMemoryUsage",
            "expr": "process_resident_memory_bytes / process_resident_memory_bytes > 0.9",
        }]

        self.assertFalse(
            monitoring_setup.upload_prometheus_rules(
                invalid_rules,
                monitoring_setup.DEFAULT_PROMETHEUS_URL,
                dry_run=True,
            )
        )


if __name__ == "__main__":
    unittest.main()
