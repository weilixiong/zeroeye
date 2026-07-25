"""Tests for monitoring_setup.py alert expression validation."""

import re
import sys
from pathlib import Path

# Import the alert rules from monitoring_setup
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tools.monitoring_setup import RECOMMENDED_ALERT_RULES


def _find_self_dividing(rules):
    """Return names of alerts whose expr divides a metric by itself."""
    bad = []
    for rule in rules:
        expr = rule.get("expr", "")
        # Match patterns like <metric> / <metric> where both sides are identical
        m = re.match(r"^(\S+)\s*/\s*\1\s*(?:>|<|>=|<=|==|!=|=)\s*[\d.]+$", expr)
        if m:
            bad.append((rule["name"], expr))
    return bad


def test_no_self_dividing_memory_expr():
    """HighMemoryUsage must not divide process_resident_memory_bytes by itself."""
    bad = _find_self_dividing(RECOMMENDED_ALERT_RULES)
    names = [name for name, _ in bad]
    assert "HighMemoryUsage" not in names, (
        f"HighMemoryUsage still uses a self-dividing expression: "
        f"{dict(bad).get('HighMemoryUsage')}"
    )


def test_high_memory_usage_uses_meaningful_denominator():
    """HighMemoryUsage expr should use machine_memory_bytes as denominator."""
    for rule in RECOMMENDED_ALERT_RULES:
        if rule["name"] == "HighMemoryUsage":
            expr = rule["expr"]
            assert "machine_memory_bytes" in expr, (
                f"HighMemoryUsage should use machine_memory_bytes as denominator, got: {expr}"
            )
            assert "process_resident_memory_bytes / process_resident_memory_bytes" not in expr, (
                f"HighMemoryUsage must not self-divide, got: {expr}"
            )
            return
    assert False, "HighMemoryUsage rule not found in RECOMMENDED_ALERT_RULES"


def test_all_alert_expressions_valid():
    """No alert rule should contain a self-dividing expression."""
    bad = _find_self_dividing(RECOMMENDED_ALERT_RULES)
    assert bad == [], f"Self-dividing alert expressions found: {bad}"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
