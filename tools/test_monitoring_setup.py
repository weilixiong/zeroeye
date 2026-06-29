import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))

import monitoring_setup


class MonitoringRuleValidationTest(unittest.TestCase):
    def test_recommended_rules_do_not_self_divide(self):
        offenders = monitoring_setup.find_self_dividing_alerts(
            monitoring_setup.RECOMMENDED_ALERT_RULES
        )
        self.assertEqual(offenders, [])

    def test_self_dividing_alert_is_rejected(self):
        rules = [
            {
                "name": "BrokenMemoryAlert",
                "expr": "process_resident_memory_bytes / process_resident_memory_bytes > 0.9",
            }
        ]
        self.assertEqual(
            monitoring_setup.find_self_dividing_alerts(rules),
            ["BrokenMemoryAlert"],
        )


if __name__ == "__main__":
    unittest.main()
