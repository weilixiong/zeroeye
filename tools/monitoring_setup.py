# Fix for Issue #1: [$30 BOUNTY] [Python] Fix HighMemoryUsage alert ratio expression

#!/usr/bin/env python3
"""
Monitoring setup configuration for Prometheus alerts and rules.
"""

import re
import yaml
from typing import Dict, List, Any, Optional


class AlertValidationError(Exception):
    """Raised when alert expression validation fails."""
    pass


def validate_promql_expression(expr: str, alert_name: str = "unknown") -> List[str]:
    """
    Validate a PromQL expression for common issues.
    
    Args:
        expr: The PromQL expression to validate
        alert_name: Name of the alert for error messages
        
    Returns:
        List of validation warnings/errors found
    """
    issues = []
    
    # Check for self-dividing expressions (metric / metric pattern)
    # This regex matches patterns like: metric_name / metric_name
    self_div_pattern = r'(\b[a-zA-Z_:][a-zA-Z0-9_:]*\b)\s*/\s*\1(?!\s*[a-zA-Z0-9_])'
    matches = re.findall(self_div_pattern, expr)
    if matches:
        for match in matches:
            issues.append(
                f"Alert '{alert_name}' contains self-dividing expression: "
                f"'{match} / {match}' always equals 1 for non-zero values"
            )
    
    # Check for division by zero potential (literal zero in denominator)
    if re.search(r'/\s*0(?![0-9.])', expr):
        issues.append(f"Alert '{alert_name}' may divide by zero")
    
    return issues


def get_memory_usage_expression() -> str:
    """
    Get the PromQL expression for calculating memory usage ratio.
    
    Uses process_resident_memory_bytes compared against node_memory_MemTotal_bytes
    to calculate actual memory pressure as a percentage.
    
    Returns:
        Valid PromQL expression for memory usage ratio
    """
    return (
        "process_resident_memory_bytes / "
        "on(instance) group_left() node_memory_MemTotal_bytes"
    )


def create_high_memory_usage_alert(threshold: float = 0.9) -> Dict[str, Any]:
    """
    Create a HighMemoryUsage alert rule configuration.
    
    Args:
        threshold: Memory usage ratio threshold (0.0 to 1.0)
        
    Returns:
        Alert rule configuration dictionary
    """
    if not 0.0 < threshold <= 1.0:
        raise ValueError(f"Threshold must be between 0 and 1, got {threshold}")
    
    memory_expr = get_memory_usage_expression()
    expr = f"{memory_expr} > {threshold}"
    
    # Validate the expression
    issues = validate_promql_expression(expr, "HighMemoryUsage")
    if issues:
        raise AlertValidationError("; ".join(issues))
    
    return {
        "alert": "HighMemoryUsage",
        "expr": expr,
        "for": "5m",
        "labels": {
            "severity": "warning"
        },
        "annotations": {
            "summary": "High memory usage detected",
            "description": (
                "Process {{ $labels.instance }} is using "
                "{{ printf \"%.1f\" (mul $value 100) }}% of total memory "
                "for more than 5 minutes."
            )
        }
    }


def create_high_cpu_usage_alert(threshold: float = 0.8) -> Dict[str, Any]:
    """
    Create a HighCPUUsage alert rule configuration.
    
    Args:
        threshold: CPU usage ratio threshold (0.0 to 1.0)
        
    Returns:
        Alert rule configuration dictionary
    """
    if not 0.0 < threshold <= 1.0:
        raise ValueError(f"Threshold must be between 0 and 1, got {threshold}")
    
    expr = f"rate(process_cpu_seconds_total[5m]) > {threshold}"
    
    # Validate the expression
    issues = validate_promql_expression(expr, "HighCPUUsage")
    if issues:
        raise AlertValidationError("; ".join(issues))
    
    return {
        "alert": "HighCPUUsage",
        "expr": expr,
        "for": "5m",
        "labels": {
            "severity": "warning"
        },
        "annotations": {
            "summary": "High CPU usage detected",
            "description": (
                "Process {{ $labels.instance }} CPU usage is above "
                f"{int(threshold * 100)}% for more than 5 minutes."
            )
        }
    }


def create_instance_down_alert() -> Dict[str, Any]:
    """
    Create an InstanceDown alert rule configuration.
    
    Returns:
        Alert rule configuration dictionary
    """
    return {
        "alert": "InstanceDown",
        "expr": "up == 0",
        "for": "1m",
        "labels": {
            "severity": "critical"
        },
        "annotations": {
            "summary": "Instance {{ $labels.instance }} is down",
            "description": (
                "{{ $labels.instance }} of job {{ $labels.job }} "
                "has been down for more than 1 minute."
            )
        }
    }


def generate_alert_rules(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Generate complete Prometheus alert rules configuration.
    
    Args:
        config: Optional configuration overrides
        
    Returns:
        Complete alert rules configuration
    """
    config = config or {}
    
    memory_threshold = config.get("memory_threshold", 0.9)
    cpu_threshold = config.get("cpu_threshold", 0.8)
    
    alerts = [
        create_instance_down_alert(),
        create_high_memory_usage_alert(memory_threshold),
        create_high_cpu_usage_alert(cpu_threshold),
    ]
    
    # Validate all alerts
    all_issues = []
    for alert in alerts:
        issues = validate_promql_expression(alert["expr"], alert["alert"])
        all_issues.extend(issues)
    
    if all_issues:
        raise AlertValidationError(
            f"Alert validation failed: {'; '.join(all_issues)}"
        )
    
    return {
        "groups": [
            {
                "name": "zeroeye_alerts",
                "rules": alerts
            }
        ]
    }


def generate_monitoring_config(
    output_path: Optional[str] = None,
    dry_run: bool = False,
    config: Optional[Dict[str, Any]] = None
) -> str:
    """
    Generate monitoring configuration and optionally write to file.
    
    Args:
        output_path: Path to write the configuration file
        dry_run: If True, only return the config without writing
        config: Optional configuration overrides
        
    Returns:
        Generated YAML configuration string
    """
    alert_rules = generate_alert_rules(config)
    yaml_output = yaml.dump(alert_rules, default_flow_style=False, sort_keys=False)
    
    if dry_run:
        print("=== DRY RUN: Generated Alert Rules ===")
        print(yaml_output)
        print("=== END DRY RUN ===")
    elif output_path:
        with open(output_path, 'w') as f:
            f.write(yaml_output)
        print(f"Alert rules written to {output_path}")
    
    return yaml_output


def validate_existing_rules(rules_path: str) -> List[str]:
    """
    Validate existing alert rules file for common issues.
    
    Args:
        rules_path: Path to existing rules YAML file
        
    Returns:
        List of validation issues found
    """
    with open(rules_path, 'r') as f:
        rules = yaml.safe_load(f)
    
    all_issues = []
    
    for group in rules.get("groups", []):
        for rule in group.get("rules", []):
            if "alert" in rule and "expr" in rule:
                issues = validate_promql_expression(
                    rule["expr"], 
                    rule["alert"]
                )
                all_issues.extend(issues)
    
    return all_issues


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate monitoring configuration")
    parser.add_argument(
        "--output", "-o",
        help="Output file path for alert rules"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print configuration without writing to file"
    )
    parser.add_argument(
        "--validate",
        help="Validate existing rules file"
    )
    parser.add_argument(
        "--memory-threshold",
        type=float,
        default=0.9,
        help="Memory usage alert threshold (default: 0.9)"
    )
    parser.add_argument(
        "--cpu-threshold",
        type=float,
        default=0.8,
        help="CPU usage alert threshold (default: 0.8)"
    )
    
    args = parser.parse_args()
    
    if args.validate:
        issues = validate_existing_rules(args.validate)
        if issues:
            print("Validation issues found:")
            for issue in issues:
                print(f"  - {issue}")
            exit(1)
        else:
            print("All alert expressions validated successfully")
            exit(0)
    
    config = {
        "memory_threshold": args.memory_threshold,
        "cpu_threshold": args.cpu_threshold,
    }
    
    try:
        generate_monitoring_config(
            output_path=args.output,
            dry_run=args.dry_run,
            config=config
        )
    except AlertValidationError as e:
        print(f"Error: {e}")
        exit(1)