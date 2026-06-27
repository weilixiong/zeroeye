import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.monitoring_setup import RECOMMENDED_ALERT_RULES


def test_high_memory_usage_alert_uses_real_denominator():
    high_memory_rule = next(
        rule for rule in RECOMMENDED_ALERT_RULES if rule["name"] == "HighMemoryUsage"
    )

    expr = high_memory_rule["expr"]

    assert "process_resident_memory_bytes / process_resident_memory_bytes" not in expr
    assert "process_resident_memory_bytes" in expr
    assert "machine_memory_bytes" in expr


if __name__ == "__main__":
    test_high_memory_usage_alert_uses_real_denominator()
