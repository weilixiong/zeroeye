#!/usr/bin/env python3
"""Validation test for monitoring alert expressions."""

import sys
sys.path.insert(0, '/home/pista/zeroeye-fix/tools')
from monitoring_setup import RECOMMENDED_ALERT_RULES


def test_no_self_dividing_expressions():
    """Alert expressions must not divide a metric by itself."""
    for alert in RECOMMENDED_ALERT_RULES:
        expr = alert.get("expr", "")
        # Check for self-dividing pattern: metric / metric
        parts = expr.split("/")
        if len(parts) == 2:
            left = parts[0].strip().split("{")[0].strip()
            right = parts[1].strip().split("{")[0].strip()
            # Remove comparison operators
            left = left.replace(">0.9", "").replace("<0.1", "").replace(">0.05", "").replace(">0.8", "").replace(">2", "").replace("==0", "").strip()
            right = right.replace(">0.9", "").replace("<0.1", "").replace(">0.05", "").replace(">0.8", "").replace(">2", "").replace("==0", "").strip()
            if left == right and left:
                print(f"FAIL: {alert['name']} has self-dividing expression: {expr}")
                return False
    print("PASS: No self-dividing expressions found")
    return True


if __name__ == "__main__":
    success = test_no_self_dividing_expressions()
    sys.exit(0 if success else 1)
