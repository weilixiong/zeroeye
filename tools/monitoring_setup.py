#!/usr/bin/env python3
import re
import sys

# Prometheus Alert Rules Configuration
ALERT_RULES = {
    "HighMemoryUsage": {
        "expr": "process_resident_memory_bytes / node_memory_MemTotal_bytes > 0.9",
        "description": "Process resident memory usage is above 90% of total system memory"
    },
    "HighCPUUsage": {
        "expr": "rate(process_cpu_seconds_total[5m]) > 0.8",
        "description": "Process CPU usage is above 80% over a 5m window"
    }
}

def validate_alert_expressions(rules):
    """
    Validates Prometheus expressions to catch common regressions,
    specifically self-dividing expressions (e.g., x / x).
    """
    for name, data in rules.items():
        expr = data.get("expr", "")
        
        # Regex to detect self-division: matches 'metric_name / metric_name'
        # Handles optional spaces around the slash
        self_division_pattern = r"(\w+)\s*/\s*\1(?!\w)"
        
        if re.search(self_division_pattern, expr):
            print(f"ERROR: Validation failed for alert '{name}'")
            print(f"Expression '{expr}' contains a self-dividing ratio.")
            return False
            
    return True

def run_setup():
    print("Starting monitoring setup...")
    
    if not validate_alert_expressions(ALERT_RULES):
        print("Setup failed: Invalid alert expressions detected.")
        sys.exit(1)
        
    # Logic for generating Prometheus config files would go here
    print("Alert rules validated successfully.")
    for name, data in ALERT_RULES.items():
        print(f"  - {name}: {data['expr']}")
    
    print("Monitoring setup completed.")

if __name__ == "__main__":
    run_setup()
