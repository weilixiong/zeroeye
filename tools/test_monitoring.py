"""
Unit tests for monitoring configuration and alert rule validations.
"""

import sys
import os
import unittest

# Add parent directory to path so we can import tools.monitoring_setup
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools import monitoring_setup

class TestMonitoringValidation(unittest.TestCase):
    """
    Test suite for checking monitoring alert rule expressions and validation helper.
    """

    def test_self_dividing_detection(self):
        """
        Verify that self-dividing PromQL expressions are flagged and correct ones pass.
        """
        # Self-dividing expression (should fail validation)
        invalid_rules = [
            {
                "name": "InvalidMemoryRule",
                "expr": "process_resident_memory_bytes / process_resident_memory_bytes > 0.9"
            }
        ]
        
        # Valid expression (should pass validation)
        valid_rules = [
            {
                "name": "ValidMemoryRule",
                "expr": "process_resident_memory_bytes / machine_memory_bytes > 0.9"
            },
            {
                "name": "ValidCpuRule",
                "expr": "avg by(instance) (rate(process_cpu_seconds_total[5m])) > 0.8"
            }
        ]
        
        # Check validation outcomes
        self.assertFalse(monitoring_setup.validate_alert_expressions(invalid_rules))
        self.assertTrue(monitoring_setup.validate_alert_expressions(valid_rules))

    def test_recommended_rules_valid(self):
        """
        Ensure all production alert rules defined in monitoring_setup are valid.
        """
        # Run validation on the actual recommended alert rules in the codebase
        rules = monitoring_setup.RECOMMENDED_ALERT_RULES
        self.assertTrue(monitoring_setup.validate_alert_expressions(rules))

if __name__ == '__main__':
    unittest.main()
