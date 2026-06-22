# Fix for Issue #1: [$30 BOUNTY] [Python] Fix HighMemoryUsage alert ratio expression

#!/usr/bin/env python3
"""
Monitoring setup utility for ZeroEye.
Generates Prometheus alert rules and monitoring configurations.
"""

import json
import os
import re
from typing import Dict, List, Any, Optional


class AlertRule:
    """Represents a Prometheus alert rule."""
    
    def __init__(self, name: str, expr: str, duration: str = "5m", 
                 severity: str = "warning", summary: str = "", description: str = ""):
        self.name = name
        self.expr = expr
        self.duration = duration
        self.severity = severity
        self.summary = summary
        self.description = description
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert alert rule to dictionary format."""
        return {
            "alert": self.name,
            "expr": self.expr,
            "for": self.duration,
            "labels": {
                "severity": self.severity
            },
            "annotations": {
                "summary": self.summary,
                "description": self.description
            }
        }


class AlertExpressionValidator:
    """Validates Prometheus alert expressions for common issues."""
    
    @staticmethod
    def is_self_dividing(expr: str) -> bool:
        """
        Check if an expression contains self-dividing metrics.
        
        A self-dividing expression divides a metric by itself, which always
        evaluates to 1 for any nonzero value and is typically a bug.
        
        Examples of self-dividing:
            - process_resident_memory_bytes / process_resident_memory_bytes
            - node_cpu_seconds_total / node_cpu_seconds_total
        """
        # Pattern to match metric_name / metric_name (with optional whitespace)
        # Captures metric names and checks if they're identical
        division_pattern = r'(\b[a-zA-Z_:][a-zA-Z0-9_:]*(?:\{[^}]*\})?)\s*/\s*(\b[a-zA-Z_:][a-zA-Z0-9_:]*(?:\{[^}]*\})?)'
        
        matches = re.findall(division_pattern, expr)
        for left, right in matches:
            # Extract just the metric name without labels for comparison
            left_metric = re.match(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)', left)
            right_metric = re.match(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)', right)
            
            if left_metric and right_metric:
                if left_metric.group(1) == right_metric.group(1):
                    return True
        
        return False
    
    @staticmethod
    def validate_expression(expr: str, rule_name: str = "") -> List[str]:
        """
        Validate a PromQL expression and return list of issues found.
        
        Args:
            expr: The PromQL expression to validate
            rule_name: Optional rule name for better error messages
            
        Returns:
            List of validation error messages (empty if valid)
        """
        issues = []
        context = f" in rule '{rule_name}'" if rule_name else ""
        
        if AlertExpressionValidator.is_self_dividing(expr):
            issues.append(f"Self-dividing expression detected{context}: {expr}")
        
        # Check for empty expressions
        if not expr or not expr.strip():
            issues.append(f"Empty expression{context}")
        
        # Check for unbalanced parentheses
        if expr.count('(') != expr.count(')'):
            issues.append(f"Unbalanced parentheses{context}: {expr}")
        
        # Check for unbalanced braces (label matchers)
        if expr.count('{') != expr.count('}'):
            issues.append(f"Unbalanced braces{context}: {expr}")
        
        return issues


class MonitoringSetup:
    """Main monitoring setup class for generating alert configurations."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.validator = AlertExpressionValidator()
        self.alerts: List[AlertRule] = []
        self._setup_default_alerts()
    
    def _setup_default_alerts(self):
        """Set up default alert rules."""
        
        # High CPU Usage Alert
        self.alerts.append(AlertRule(
            name="HighCPUUsage",
            expr='100 - (avg by(instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 80',
            duration="5m",
            severity="warning",
            summary="High CPU usage detected",
            description="CPU usage is above 80% for more than 5 minutes on {{ $labels.instance }}"
        ))
        
        # High Memory Usage Alert - FIXED: No longer self-dividing
        # Uses process_resident_memory_bytes compared against node_memory_MemTotal_bytes
        # This gives a meaningful ratio of process memory to total system memory
        self.alerts.append(AlertRule(
            name="HighMemoryUsage",
            expr='(process_resident_memory_bytes / node_memory_MemTotal_bytes) > 0.9',
            duration="5m",
            severity="critical",
            summary="High memory usage detected",
            description="Process memory usage is above 90% of total system memory on {{ $labels.instance }}"
        ))
        
        # Alternative memory alert using available memory
        self.alerts.append(AlertRule(
            name="LowAvailableMemory",
            expr='(node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) < 0.1',
            duration="5m",
            severity="critical",
            summary="Low available memory",
            description="Less than 10% of memory is available on {{ $labels.instance }}"
        ))
        
        # High Disk Usage Alert
        self.alerts.append(AlertRule(
            name="HighDiskUsage",
            expr='(node_filesystem_size_bytes - node_filesystem_avail_bytes) / node_filesystem_size_bytes > 0.85',
            duration="10m",
            severity="warning",
            summary="High disk usage detected",
            description="Disk usage is above 85% on {{ $labels.instance }} mount {{ $labels.mountpoint }}"
        ))
        
        # Service Down Alert
        self.alerts.append(AlertRule(
            name="ServiceDown",
            expr='up == 0',
            duration="1m",
            severity="critical",
            summary="Service is down",
            description="Service {{ $labels.job }} on {{ $labels.instance }} is down"
        ))
    
    def add_alert(self, alert: AlertRule) -> None:
        """Add a custom alert rule."""
        self.alerts.append(alert)
    
    def validate_all_alerts(self) -> List[str]:
        """
        Validate all alert expressions.
        
        Returns:
            List of validation issues found (empty if all valid)
        """
        all_issues = []
        for alert in self.alerts:
            issues = self.validator.validate_expression(alert.expr, alert.name)
            all_issues.extend(issues)
        return all_issues
    
    def generate_prometheus_rules(self) -> Dict[str, Any]:
        """Generate Prometheus alerting rules configuration."""
        # Validate all alerts first
        issues = self.validate_all_alerts()
        if issues:
            raise ValueError(f"Alert validation failed: {'; '.join(issues)}")
        
        return {
            "groups": [
                {
                    "name": "zeroeye-alerts",
                    "rules": [alert.to_dict() for alert in self.alerts]
                }
            ]
        }
    
    def generate_yaml_output(self) -> str:
        """Generate YAML-formatted alert rules."""
        rules = self.generate_prometheus_rules()
        
        # Simple YAML generation without external dependencies
        lines = ["groups:"]
        for group in rules["groups"]:
            lines.append(f"  - name: {group['name']}")
            lines.append("    rules:")
            for rule in group["rules"]:
                lines.append(f"      - alert: {rule['alert']}")
                lines.append(f"        expr: {rule['expr']}")
                lines.append(f"        for: {rule['for']}")
                lines.append("        labels:")
                for key, value in rule["labels"].items():
                    lines.append(f"          {key}: {value}")
                lines.append("        annotations:")
                for key, value in rule["annotations"].items():
                    lines.append(f'          {key}: "{value}"')
        
        return "\n".join(lines)
    
    def dry_run(self) -> Dict[str, Any]:
        """
        Perform a dry run of the monitoring setup.
        
        Returns:
            Dictionary containing validation results and generated config preview
        """
        validation_issues = self.validate_all_alerts()
        
        result = {
            "status": "valid" if not validation_issues else "invalid",
            "validation_issues": validation_issues,
            "alert_count": len(self.alerts),
            "alerts_summary": [
                {
                    "name": alert.name,
                    "severity": alert.severity,
                    "expression": alert.expr
                }
                for alert in self.alerts
            ]
        }
        
        if not validation_issues:
            result["config_preview"] = self.generate_prometheus_rules()
        
        return result
    
    def setup(self, output_path: Optional[str] = None, dry_run: bool = False) -> Dict[str, Any]:
        """
        Run the monitoring setup.
        
        Args:
            output_path: Optional path to write the configuration file
            dry_run: If True, only validate and show preview without writing
            
        Returns:
            Setup result dictionary
        """
        if dry_run:
            return self.dry_run()
        
        # Validate first
        issues = self.validate_all_alerts()
        if issues:
            return {
                "status": "error",
                "message": "Validation failed",
                "issues": issues
            }
        
        rules = self.generate_prometheus_rules()
        
        result = {
            "status": "success",
            "alert_count": len(self.alerts),
            "rules": rules
        }
        
        if output_path:
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            with open(output_path, 'w') as f:
                if output_path.endswith('.json'):
                    json.dump(rules, f, indent=2)
                else:
                    f.write(self.generate_yaml_output())
            
            result["output_file"] = output_path
        
        return result


def main():
    """Main entry point for monitoring setup."""
    import argparse
    
    parser = argparse.ArgumentParser(description="ZeroEye Monitoring Setup")
    parser.add_argument("--output", "-o", help="Output file path for alert rules")
    parser.add_argument("--dry-run", action="store_true", help="Validate only, don't write files")
    parser.add_argument("--format", choices=["yaml", "json"], default="yaml", help="Output format")
    
    args = parser.parse_args()
    
    setup = MonitoringSetup()
    
    output_path = args.output
    if output_path and args.format == "json" and not output_path.endswith('.json'):
        output_path += '.json'
    
    result = setup.setup(output_path=output_path, dry_run=args.dry_run)
    
    print(json.dumps(result, indent=2))
    
    return 0 if result.get("status") in ("success", "valid") else 1


if __name__ == "__main__":
    exit(main())