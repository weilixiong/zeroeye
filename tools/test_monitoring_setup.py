#!/usr/bin/env python3
"""
Tests for monitoring_setup.py — alert expression validation.

Verifies that PromQL alert rule expressions:
- Do NOT self-divide (x / x)
- Use a meaningful denominator (not equal to the numerator metric name)
"""
import sys
import os

# Add parent dir so imports resolve
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.monitoring_setup import RECOMMENDED_ALERT_RULES


def _extract_alert_expr(expr: str) -> tuple[str, str]:
    """Parse a simple PromQL ratio expression and return (lhs, rhs)."""
    for op in [">=", "<=", ">", "<", "=", "!="]:
        if f" {op} " in expr:
            expr = expr.split(f" {op} ")[0]
            break
    parts = expr.split("/")
    if len(parts) != 2:
        return (expr, "")
    return (parts[0].strip(), parts[1].strip())


def _strip_wrapper(s: str) -> str:
    """Strip a function wrapper like sum(...) or avg(...)."""
    for wrapper in ["sum(", "avg(", "rate(", "min(", "max("]:
        if s.startswith(wrapper) and s.endswith(")"):
            return s[len(wrapper):-1]
    return s


def _is_self_dividing(expr: str) -> bool:
    """Check if a PromQL expression is self-dividing (x / x)."""
    lhs, rhs = _extract_alert_expr(expr)
    if not rhs:
        return False
    return _strip_wrapper(lhs) == _strip_wrapper(rhs)


def test_no_self_dividing_rules() -> int:
    """No alert rule should use a self-dividing expression."""
    errors = 0
    for rule in RECOMMENDED_ALERT_RULES:
        if _is_self_dividing(rule["expr"]):
            print(f"FAIL: Rule '{rule['name']}' has self-dividing expression: {rule['expr']}")
            errors += 1
    return errors


def test_high_memory_usage_uses_memtotal() -> int:
    """HighMemoryUsage should divide by node_memory_MemTotal_bytes."""
    rule = next(
        (r for r in RECOMMENDED_ALERT_RULES if r["name"] == "HighMemoryUsage"),
        None,
    )
    if rule is None:
        print("FAIL: HighMemoryUsage rule not found")
        return 1
    lhs, rhs = _extract_alert_expr(rule["expr"])
    errors = 0
    if "process_resident_memory_bytes" not in lhs:
        print(f"FAIL: Expected process_resident_memory_bytes on LHS, got: {lhs}")
        errors += 1
    if "node_memory_MemTotal_bytes" not in rhs:
        print(f"FAIL: Expected node_memory_MemTotal_bytes on RHS, got: {rhs}")
        errors += 1
    return errors


def test_all_rules_have_valid_promql_shape() -> int:
    """All alert rules should have a non-empty expr with a comparison operator."""
    errors = 0
    for rule in RECOMMENDED_ALERT_RULES:
        expr = rule["expr"]
        if not expr or len(expr) <= 5:
            print(f"FAIL: Rule '{rule['name']}' has empty/trivial expression")
            errors += 1
            continue
        if not any(op in expr for op in [">", "<", "=", "!"]):
            print(f"FAIL: Rule '{rule['name']}' lacks comparison operator: {expr}")
            errors += 1
    return errors


def run_all() -> int:
    """Run all tests and return the total error count."""
    total = 0
    for test_fn in [test_no_self_dividing_rules, test_high_memory_usage_uses_memtotal,
                    test_all_rules_have_valid_promql_shape]:
        errors = test_fn()
        total += errors
        fn_name = test_fn.__name__
        if errors == 0:
            print(f"OK:   {fn_name}")
        else:
            print(f"FAIL: {fn_name} — {errors} error(s)")
    return total


if __name__ == "__main__":
    rc = run_all()
    sys.exit(rc)
