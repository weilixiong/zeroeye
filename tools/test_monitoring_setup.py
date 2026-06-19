import unittest

from tools import monitoring_setup


class AlertRuleValidationTests(unittest.TestCase):
    def test_recommended_alert_rules_do_not_self_divide(self):
        errors = monitoring_setup.validate_alert_rule_expressions(
            monitoring_setup.RECOMMENDED_ALERT_RULES
        )

        self.assertEqual([], errors)

    def test_high_memory_usage_uses_machine_memory_denominator(self):
        rule = next(
            rule
            for rule in monitoring_setup.RECOMMENDED_ALERT_RULES
            if rule["name"] == "HighMemoryUsage"
        )

        self.assertIn("process_resident_memory_bytes", rule["expr"])
        self.assertIn("machine_memory_bytes", rule["expr"])

    def test_self_dividing_expression_is_rejected(self):
        errors = monitoring_setup.validate_alert_rule_expressions(
            [
                {
                    "name": "BrokenMemoryUsage",
                    "expr": "process_resident_memory_bytes / process_resident_memory_bytes > 0.9",
                }
            ]
        )

        self.assertEqual(1, len(errors))
        self.assertIn("BrokenMemoryUsage", errors[0])
        self.assertIn("process_resident_memory_bytes", errors[0])


if __name__ == "__main__":
    unittest.main()
