# Fix for Issue #1: [$30 BOUNTY] [Python] Fix HighMemoryUsage alert ratio expression

# tools/monitoring_setup.py
"""
Monitoring setup module for Prometheus alerting configuration.
Provides alert rule generation and validation for system monitoring.
"""

import re
import json
import os
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AlertRule:
    """Represents a Prometheus alert rule."""
    name: str
    expr: str
    for_duration: str = "5m"
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)


class AlertExpressionValidator:
    """Validates Prometheus alert expressions for common issues."""
    
    # Pattern to detect self-dividing expressions like "metric / metric"
    SELF_DIVIDING_PATTERN = re.compile(
        r'\b(\w+)\s*/\s*\1\b'
    )
    
    @classmethod
    def validate_expression(cls, expr: str, alert_name: str) -> List[str]:
        """
        Validate a PromQL expression for common issues.
        
        Args:
            expr: The PromQL expression to validate
            alert_name: Name of the alert (for error messages)
            
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        # Check for self-dividing expressions
        if cls._is_self_dividing(expr):
            errors.append(
                f"Alert '{alert_name}' contains self-dividing expression: {expr}. "
                "This will always evaluate to 1 for non-zero values."
            )
        
        # Check for empty expression
        if not expr or not expr.strip():
            errors.append(f"Alert '{alert_name}' has empty expression.")
        
        return errors
    
    @classmethod
    def _is_self_dividing(cls, expr: str) -> bool:
        """
        Check if expression contains self-dividing patterns.
        
        Args:
            expr: PromQL expression to check
            
        Returns:
            True if self-dividing pattern detected
        """
        # Remove string literals to avoid false positives
        cleaned_expr = re.sub(r'"[^"]*"', '', expr)
        cleaned_expr = re.sub(r"'[^']*'", '', cleaned_expr)
        
        return bool(cls.SELF_DIVIDING_PATTERN.search(cleaned_expr))


class MonitoringSetup:
    """
    Handles Prometheus monitoring configuration and alert rule generation.
    """
    
    DEFAULT_ALERTS = {
        "HighCPUUsage": {
            "expr": "rate(process_cpu_seconds_total[5m]) * 100 > 80",
            "for": "5m",
            "labels": {"severity": "warning"},
            "annotations": {
                "summary": "High CPU usage detected",
                "description": "CPU usage is above 80% for more than 5 minutes."
            }
        },
        "HighMemoryUsage": {
            "expr": "process_resident_memory_bytes / node_memory_MemTotal_bytes * 100 > 90",
            "for": "5m",
            "labels": {"severity": "critical"},
            "annotations": {
                "summary": "High memory usage detected",
                "description": "Process memory usage is above 90% of total system memory for more than 5 minutes."
            }
        },
        "HighErrorRate": {
            "expr": "rate(http_requests_total{status=~\"5..\"}[5m]) / rate(http_requests_total[5m]) * 100 > 5",
            "for": "2m",
            "labels": {"severity": "critical"},
            "annotations": {
                "summary": "High error rate detected",
                "description": "Error rate is above 5% for more than 2 minutes."
            }
        },
        "ServiceDown": {
            "expr": "up == 0",
            "for": "1m",
            "labels": {"severity": "critical"},
            "annotations": {
                "summary": "Service is down",
                "description": "The service has been down for more than 1 minute."
            }
        }
    }
    
    def __init__(self, config: Optional[Dict[str, Any]] = None, dry_run: bool = False):
        """
        Initialize monitoring setup.
        
        Args:
            config: Optional configuration overrides
            dry_run: If True, don't write files, just validate
        """
        self.config = config or {}
        self.dry_run = dry_run
        self.alerts = self._load_alerts()
        self.validator = AlertExpressionValidator()
        self._validation_errors: List[str] = []
    
    def _load_alerts(self) -> Dict[str, Dict[str, Any]]:
        """Load alert configurations, applying any overrides."""
        alerts = self.DEFAULT_ALERTS.copy()
        
        if "alerts" in self.config:
            for alert_name, alert_config in self.config["alerts"].items():
                if alert_name in alerts:
                    alerts[alert_name].update(alert_config)
                else:
                    alerts[alert_name] = alert_config
        
        return alerts
    
    def validate_all_alerts(self) -> List[str]:
        """
        Validate all configured alert expressions.
        
        Returns:
            List of validation error messages
        """
        errors = []
        
        for alert_name, alert_config in self.alerts.items():
            expr = alert_config.get("expr", "")
            alert_errors = self.validator.validate_expression(expr, alert_name)
            errors.extend(alert_errors)
        
        self._validation_errors = errors
        return errors
    
    def generate_alert_rules(self) -> Dict[str, Any]:
        """
        Generate Prometheus alert rules configuration.
        
        Returns:
            Dictionary containing alert rules in Prometheus format
        """
        # Validate before generating
        errors = self.validate_all_alerts()
        if errors:
            raise ValueError(f"Alert validation failed: {'; '.join(errors)}")
        
        rules = []
        for alert_name, alert_config in self.alerts.items():
            rule = {
                "alert": alert_name,
                "expr": alert_config["expr"],
                "for": alert_config.get("for", "5m"),
                "labels": alert_config.get("labels", {}),
                "annotations": alert_config.get("annotations", {})
            }
            rules.append(rule)
        
        return {
            "groups": [
                {
                    "name": "zeroeye_alerts",
                    "rules": rules
                }
            ]
        }
    
    def generate_prometheus_config(self) -> str:
        """
        Generate Prometheus alerting rules in YAML format.
        
        Returns:
            YAML string of alert rules
        """
        rules = self.generate_alert_rules()
        
        # Simple YAML generation without external dependencies
        lines = ["groups:"]
        for group in rules["groups"]:
            lines.append(f"  - name: {group['name']}")
            lines.append("    rules:")
            for rule in group["rules"]:
                lines.append(f"      - alert: {rule['alert']}")
                lines.append(f"        expr: {rule['expr']}")
                lines.append(f"        for: {rule['for']}")
                if rule.get("labels"):
                    lines.append("        labels:")
                    for k, v in rule["labels"].items():
                        lines.append(f"          {k}: {v}")
                if rule.get("annotations"):
                    lines.append("        annotations:")
                    for k, v in rule["annotations"].items():
                        lines.append(f"          {k}: \"{v}\"")
        
        return "\n".join(lines)
    
    def setup(self, output_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Run the monitoring setup process.
        
        Args:
            output_path: Optional path to write configuration
            
        Returns:
            Setup result dictionary
        """
        result = {
            "status": "success",
            "dry_run": self.dry_run,
            "alerts_configured": list(self.alerts.keys()),
            "validation_errors": [],
            "output_path": output_path,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        try:
            # Validate all alerts
            errors = self.validate_all_alerts()
            if errors:
                result["status"] = "failed"
                result["validation_errors"] = errors
                return result
            
            # Generate configuration
            config_yaml = self.generate_prometheus_config()
            result["config_preview"] = config_yaml[:500] + "..." if len(config_yaml) > 500 else config_yaml
            
            # Write if not dry run and output path provided
            if not self.dry_run and output_path:
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, 'w') as f:
                    f.write(config_yaml)
                result["written"] = True
            else:
                result["written"] = False
            
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
        
        return result
    
    def get_alert_expression(self, alert_name: str) -> Optional[str]:
        """
        Get the expression for a specific alert.
        
        Args:
            alert_name: Name of the alert
            
        Returns:
            Alert expression or None if not found
        """
        alert = self.alerts.get(alert_name)
        return alert.get("expr") if alert else None


def create_monitoring_setup(config: Optional[Dict[str, Any]] = None, 
                            dry_run: bool = False) -> MonitoringSetup:
    """
    Factory function to create a MonitoringSetup instance.
    
    Args:
        config: Optional configuration dictionary
        dry_run: If True, validation only mode
        
    Returns:
        Configured MonitoringSetup instance
    """
    return MonitoringSetup(config=config, dry_run=dry_run)


# CLI interface for direct execution
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Monitoring Setup Tool")
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing")
    parser.add_argument("--output", "-o", help="Output path for configuration")
    parser.add_argument("--validate-only", action="store_true", help="Only validate expressions")
    
    args = parser.parse_args()
    
    setup = MonitoringSetup(dry_run=args.dry_run)
    
    if args.validate_only:
        errors = setup.validate_all_alerts()
        if errors:
            print("Validation errors found:")
            for error in errors:
                print(f"  - {error}")
            exit(1)
        else:
            print("All alert expressions validated successfully.")
            exit(0)
    
    result = setup.setup(output_path=args.output)
    print(json.dumps(result, indent=2))
    exit(0 if result["status"] == "success" else 1)