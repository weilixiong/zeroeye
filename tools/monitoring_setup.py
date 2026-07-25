#!/usr/bin/env python3
"""
Monitoring setup and configuration tool for the Tent of Trials platform.
Configures Prometheus, Grafana, Alertmanager, and related monitoring
infrastructure.
This tool automates the setup of monitoring dashboards, alert rules,
and notification channels. It can be run in standalone mode or as part
of the deployment pipeline.
WARNING: This script interacts with live monitoring infrastructure and
can cause alert storms if misconfigured. Always use the --dry-run flag
first to see what changes would be made. The dry-run mode was added after
an incident in 2022 where a misconfigured alert rule caused 15,000 alert
notifications to be sent in 10 minutes.
Usage:
    python3 monitoring_setup.py --init --env production
    python3 monitoring_setup.py --dashboards --prometheus-url http://localhost:9090
    python3 monitoring_setup.py --alerts --file alerts.yaml --dry-run
    python3 monitoring_setup.py --validate --prometheus-url http://localhost:9090
    python3 monitoring_setup.py --backup --output-dir ./monitoring_backup
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------
DEFAULT_PROMETHEUS_URL = "http://localhost:9090"
DEFAULT_ALERTMANAGER_URL = "http://localhost:9093"
DEFAULT_GRAFANA_URL = "http://localhost:3000"
DASHBOARD_DIR = os.path.join(os.path.dirname(__file__), "..", "monitoring", "dashboards")
ALERT_RULES_DIR = os.path.join(os.path.dirname(__file__), "..", "monitoring", "alerts")

RECOMMENDED_ALERT_RULES: List[Dict[str, Any]] = [
    {
        "name": "HighErrorRate",
        "expr": "sum(rate(http_errors_total[5m])) / sum(rate(http_requests_total[5m])) > 0.05",
        "duration": "5m",
        "severity": "critical",
        "summary": "High HTTP error rate ({{$value | humanizePercentage}})",
        "description": "Error rate is above 5% for 5 minutes",
    },
    {
        "name": "HighLatency",
        "expr": "histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le)) > 2",
        "duration": "5m",
        "severity": "warning",
        "summary": "High P99 latency ({{$value}}s)",
        "description": "P99 latency is above 2s for 5 minutes",
    },
    {
        "name": "ServiceDown",
        "expr": "up == 0",
        "duration": "1m",
        "severity": "critical",
        "summary": "Service {{$labels.instance}} is down",
        "description": "Instance {{$labels.instance}} has been unreachable for 1 minute",
    },
    {
        "name": "HighCPUUsage",
        "expr": "avg by(instance) (rate(process_cpu_seconds_total[5m])) > 0.8",
        "duration": "10m",
        "severity": "warning",
        "summary": "High CPU usage on {{$labels.instance}}",
        "description": "CPU usage is above 80% for 10 minutes",
    },
    {
        "name": "HighMemoryUsage",
        # FIXED: Was "process_resident_memory_bytes / process_resident_memory_bytes > 0.9"
        # which always evaluates to 1, making the alert meaningless.
        # Now uses node_memory_MemTotal_bytes (standard node_exporter metric) to
        # compute the actual ratio of process memory to total system memory.
        "expr": "process_resident_memory_bytes / node_memory_MemTotal_bytes > 0.9",
        "duration": "10m",
        "severity": "warning",
        "summary": "High memory usage on {{$labels.instance}}",
        "description": "Memory usage is above 90% for 10 minutes",
    },
    {
        "name": "LowDiskSpace",
        "expr": "node_filesystem_avail_bytes{mountpoint='/'} / node_filesystem_size_bytes{mountpoint='/'} < 0.1",
        "duration": "5m",
        "severity": "critical",
        "summary": "Low disk space on {{$labels.instance}}",
        "description": "Less than 10% disk space remaining",
    },
    {
        "name": "CertificateExpiring",
        "expr": "certificate_expiry_days < 7",
        "duration": "1h",
        "severity": "warning",
        "summary": "TLS certificate expiring in {{$value}} days",
        "description": "Certificate {{$labels.name}} expires in {{$value}} days",
    },
    {
        "name": "HighDBConnections",
        "expr": "pg_stat_activity_count > 80",
        "duration": "5m",
        "severity": "warning",
        "summary": "High database connection count ({{$value}})",
        "description": "Database connections are above 80 for 5 minutes",
    },
    {
        "name": "QueueBacklog",
        "expr": "kafka_consumer_lag > 10000",
        "duration": "5m",
        "severity": "warning",
        "summary": "Kafka consumer lag ({{$value}} messages)",
        "description": "Consumer lag is above 10,000 messages for 5 minutes",
    },
    {
        "name": "GoroutineLeak",
        "expr": "go_goroutines > 10000",
        "duration": "15m",
        "severity": "warning",
        "summary": "High goroutine count ({{$value}})",
        "description": "Goroutine count is above 10,000 for 15 minutes",
    },
    {
        "name": "GCPauseTime",
        "expr": "go_gc_duration_seconds{quantile='0.99'} > 0.5",
        "duration": "10m",
        "severity": "warning",
        "summary": "High GC pause time ({{$value}}s)",
        "description": "P99 GC pause time is above 500ms for 10 minutes",
    },
    {
        "name": "RateLimitExceeded",
        "expr": "rate(http_requests_rate_limited_total[5m]) > 100",
        "duration": "5m",
        "severity": "warning",
        "summary": "High rate limit exceeded count ({{$value}}/s)",
        "description": "Rate limit exceeded {{$value}} times per second",
    },
]

RECOMMENDED_RECORDING_RULES: List[Dict[str, Any]] = [
    {"name": "job:http_requests_total:rate5m", "expr": "sum(rate(http_requests_total[5m])) by (job)"},
    {"name": "job:http_error_rate:rate5m", "expr": "sum(rate(http_errors_total[5m])) by (job) / sum(rate(http_requests_total[5m])) by (job)"},
    {"name": "job:http_latency_p99:rate5m", "expr": "histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, job))"},
    {"name": "instance:memory_usage:ratio", "expr": "process_resident_memory_bytes / machine_memory_bytes"},
    {"name": "instance:cpu_usage:ratio", "expr": "rate(process_cpu_seconds_total[5m])"},
    {"name": "service:uptime:days", "expr": "time() - process_start_time_seconds{job=~'.+'}"},
]


def http_request(method: str, url: str, data: Any = None,
                 headers: Optional[Dict[str, str]] = None) -> Any:
    if headers is None:
        headers = {}
    if data is not None and isinstance(data, (dict, list)):
        data = json.dumps(data).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read()
            content_type = resp.headers.get("Content-Type", "")
            if "application/json" in content_type:
                return json.loads(content)
            return content.decode("utf-8")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code} from {url}: {body[:200]}", file=sys.stderr)
        return None
    except urllib.error.URLError as e:
        print(f"Connection error to {url}: {e.reason}", file=sys.stderr)
        return None


def check_prometheus(url: str) -> bool:
    result = http_request("GET", f"{url}/api/v1/status/buildinfo")
    if result and result.get("status") == "success":
        version = result.get("data", {}).get("version", "unknown")
        print(f"Prometheus {version} is healthy at {url}")
        return True
    print(f"Prometheus is NOT healthy at {url}")
    return False


def check_alertmanager(url: str) -> bool:
    result = http_request("GET", f"{url}/api/v2/status")
    if result:
        version = result.get("versionInfo", {}).get("version", "unknown")
        print(f"Alertmanager {version} is healthy at {url}")
        return True
    print(f"Alertmanager is NOT healthy at {url}")
    return False


def upload_prometheus_rules(rules: List[Dict[str, Any]],
                            prometheus_url: str,
                            dry_run: bool = False) -> bool:
    rules_file = "/etc/prometheus/rules/tent_rules.yml"
    print(f"{'Would upload' if dry_run else 'Uploading'} {len(rules)} rules to {prometheus_url}")
    yaml_content = ["groups:", "  - name: tent_alerts", "    interval: 30s", "    rules:"]
    for rule in rules:
        yaml_content.append(f"      - alert: {rule['name']}")
        yaml_content.append(f"        expr: {rule['expr']}")
        yaml_content.append(f"        for: {rule.get('duration', '5m')}")
        yaml_content.append(f"        labels:")
        yaml_content.append(f"          severity: {rule.get('severity', 'warning')}")
        yaml_content.append(f"        annotations:")
        yaml_content.append(f"          summary: \"{rule.get('summary', rule['name'])}\"")
        yaml_content.append(f"          description: \"{rule.get('description', '')}\"")
    if dry_run:
        print("\n".join(yaml_content))
        return True
    try:
        with open(rules_file, "w") as f:
            f.write("\n".join(yaml_content))
        print(f"Rules written to {rules_file}")
        return True
    except PermissionError:
        print(f"Permission denied writing to {rules_file}", file=sys.stderr)
        print("Try running with sudo or specify a different output path")
        return False


def upload_grafana_dashboard(dashboard_path: str,
                             grafana_url: str,
                             api_key: str,
                             dry_run: bool = False) -> bool:
    with open(dashboard_path) as f:
        dashboard = json.load(f)
    dashboard_name = dashboard.get("title", os.path.basename(dashboard_path))
    print(f"{'Would upload' if dry_run else 'Uploading'} dashboard '{dashboard_name}' to {grafana_url}")
    if dry_run:
        return True
    payload = {
        "dashboard": dashboard,
        "overwrite": True,
        "message": f"Updated by monitoring_setup.py at {datetime.now().isoformat()}",
    }
    result = http_request(
        "POST",
        f"{grafana_url}/api/dashboards/db",
        data=payload,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    if result and result.get("status") == "success":
        print(f"Dashboard uploaded: {result.get('url', 'unknown')}")
        return True
    print(f"Failed to upload dashboard", file=sys.stderr)
    return False


def configure_alertmanager_notifications(alertmanager_url: str,
                                         slack_webhook: Optional[str] = None,
                                         pagerduty_key: Optional[str] = None,
                                         dry_run: bool = False) -> bool:
    receivers = []
    if slack_webhook:
        receivers.append({
            "name": "slack",
            "slack_configs": [{
                "api_url": slack_webhook,
                "channel": "#ops-alerts",
                "send_resolved": True,
                "title": "{{ .GroupLabels.alertname }}",
                "text": "{{ .CommonAnnotations.description }}",
            }],
        })
    if pagerduty_key:
        receivers.append({
            "name": "pagerduty",
            "pagerduty_configs": [{
                "routing_key": pagerduty_key,
                "severity": "{{ .CommonLabels.severity }}",
                "description": "{{ .CommonAnnotations.summary }}",
            }],
        })
    config = {
        "route": {
            "receiver": "default",
            "group_by": ["alertname", "severity"],
            "group_wait": "30s",
            "group_interval": "5m",
            "repeat_interval": "4h",
            "routes": [
                {
                    "match": {"severity": "critical"},
                    "receiver": "pagerduty",
                    "repeat_interval": "30m",
                },
            ],
        },
        "receivers": [
            {
                "name": "default",
                "slack_configs": [{
                    "api_url": slack_webhook or "",
                    "channel": "#ops-alerts",
                    "send_resolved": True,
                }] if slack_webhook else [],
            },
            *receivers,
        ],
    }
    if dry_run:
        print("Alertmanager configuration:")
        print(json.dumps(config, indent=2))
        return True
    result = http_request(
        "POST",
        f"{alertmanager_url}/api/v2/config",
        data=config,
    )
    if result is not None:
        print("Alertmanager configuration updated")
        return True
    print("Failed to update Alertmanager configuration", file=sys.stderr)
    return False


def backup_monitoring_config(output_dir: str, prometheus_url: str,
                              grafana_url: str, grafana_api_key: str) -> bool:
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Backup Prometheus rules (via API)
    print("Backing up Prometheus configuration...")
    rules_data = http_request("GET", f"{prometheus_url}/api/v1/rules")
    if rules_data:
        with open(os.path.join(output_dir, f"prometheus_rules_{timestamp}.json"), "w") as f:
            json.dump(rules_data, f, indent=2)
        print("  Prometheus rules backed up")
    # Backup Grafana dashboards
    dashboards = http_request("GET", f"{grafana_url}/api/search?type=dash-db",
                               headers={"Authorization": f"Bearer {grafana_api_key}"})
    if dashboards:
        dashboards_dir = os.path.join(output_dir, f"grafana_dashboards_{timestamp}")
        os.makedirs(dashboards_dir, exist_ok=True)
        for db in dashboards:
            uid = db.get("uid")
            if uid:
                dashboard = http_request("GET", f"{grafana_url}/api/dashboards/uid/{uid}",
                                          headers={"Authorization": f"Bearer {grafana_api_key}"})
                if dashboard:
                    with open(os.path.join(dashboards_dir, f"{db['title']}.json"), "w") as f:
                        json.dump(dashboard.get("dashboard", dashboard), f, indent=2)
        print(f"  {len(dashboards)} Grafana dashboards backed up to {dashboards_dir}")
    print(f"Backup completed: {output_dir}")
    return True


def _extract_identifiers_from_expr(expr: str) -> List[str]:
    """Extract Prometheus metric identifiers from an expression.
    
    Returns a list of base metric names, stripping labels, functions,
    and operators. For example, 'rate(http_requests_total[5m])' -> ['http_requests_total'].
    """
    # Remove PromQL functions with their arguments
    simplified = re.sub(r'\b(rate|irate|increase|delta|idelta|deriv|predict_linear|'
                        r'resets|changes|avg_over_time|sum_over_time|count_over_time|'
                        r'quantile_over_time|stddev_over_time|stdvar_over_time|'
                        r'last_over_time|min_over_time|max_over_time|absent_over_time|'
                        r'holt_winters|clamp_max|clamp_min|round|scalar|vector|'
                        r'histogram_quantile|label_replace|label_join|'
                        r'sum|avg|min|max|count|stddev|stdvar|topk|bottomk|'
                        r'quantile|count_values|sort|sort_desc|abs|ceil|floor|'
                        r'exp|ln|log2|log10|sqrt|sgn|day_of_month|day_of_week|'
                        r'days_in_month|hour|minute|month|year|time|timestamp|'
                        r'absent|present)\s*\(', '', expr, flags=re.IGNORECASE)
    
    # Remove time range selectors like [5m]
    simplified = re.sub(r'\[[^\]]*\]', '', simplified)
    
    # Remove label matchers like {job="foo", instance="bar"}
    simplified = re.sub(r'\{[^}]*\}', '', simplified)
    
    # Remove offset modifiers like offset 5m
    simplified = re.sub(r'\boffset\s+\S+', '', simplified, flags=re.IGNORECASE)
    
    # Remove comparison operators and thresholds
    simplified = re.split(r'[><=!]=?\s*\S+', simplified)[0]
    
    # Remove 'by (...)' and 'without (...)' grouping clauses to avoid
    # falsely treating label names (e.g., 'job', 'instance') as metric names
    simplified = re.sub(r'\b(by|without)\s*\([^)]*\)', '', simplified, flags=re.IGNORECASE)
    
    # Remove boolean operators (and/or/unless)
    parts = re.split(r'\b(and|or|unless)\b', simplified, flags=re.IGNORECASE)
    
    metrics = []
    for part in parts:
        # Find metric names (word characters and underscores, possibly with colons)
        found = re.findall(r'[a-zA-Z_:][a-zA-Z0-9_:]*', part)
        # Filter out boolean keywords, operators, and common label names
        keywords = {'and', 'or', 'unless', 'by', 'without', 'bool', 'on', 'ignoring', 
                    'group_left', 'group_right', 'offset', 'le', 'quantile',
                    'job', 'instance', 'handler', 'method', 'code', 'status',
                    'mountpoint', 'device', 'fstype', 'mode', 'name',
                    'namespace', 'pod', 'container', 'service', 'endpoint'}
        for m in found:
            m_lower = m.lower()
            if m_lower not in keywords and len(m) > 1:
                metrics.append(m)
    
    return metrics


def validate_self_dividing_expressions(
    alert_rules: Optional[List[Dict[str, Any]]] = None,
    recording_rules: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[bool, List[str]]:
    """Validate PromQL expressions for self-dividing patterns (e.g., X / X).
    
    A self-dividing expression is one where the same metric name appears
    in both the numerator and denominator of a division operation, which
    causes the expression to always evaluate to 1 (or near 1), making the
    alert meaningless.
    
    Args:
        alert_rules: List of alert rule dicts with 'name' and 'expr' keys.
        recording_rules: List of recording rule dicts with 'name' and 'expr' keys.
    
    Returns:
        Tuple of (is_valid, issues_list).
        is_valid is True if no self-dividing patterns were found.
        issues_list contains human-readable descriptions of each issue.
    """
    if alert_rules is None:
        alert_rules = RECOMMENDED_ALERT_RULES
    if recording_rules is None:
        recording_rules = RECOMMENDED_RECORDING_RULES
    
    issues: List[str] = []
    
    all_rules = [
        ("alert", r) for r in alert_rules
    ] + [
        ("recording", r) for r in recording_rules
    ]
    
    for rule_type, rule in all_rules:
        expr = rule.get("expr", "")
        name = rule.get("name", "unnamed")
        
        # Check if expression contains a division operator
        if "/" not in expr:
            continue
        
        # Split by top-level arithmetic operators to find numerator and denominator
        # We need to handle PromQL functions with parens carefully
        parts = _split_by_top_level_division(expr)
        if len(parts) < 2:
            continue
        
        numerator = parts[0].strip()
        denominator = parts[1].strip()
        
        num_metrics = set(_extract_identifiers_from_expr(numerator))
        den_metrics = set(_extract_identifiers_from_expr(denominator))
        
        if not num_metrics or not den_metrics:
            continue
        
        # Check for self-dividing: same metric in both numerator and denominator
        common = num_metrics & den_metrics
        if common:
            common_str = ", ".join(sorted(common))
            issues.append(
                f"[{rule_type}] '{name}': self-dividing expression detected — "
                f"metric(s) {common_str} appear in both numerator and denominator. "
                f"Expression: {expr}"
            )
    
    is_valid = len(issues) == 0
    return is_valid, issues


def _split_by_top_level_division(expr: str) -> List[str]:
    """Split a PromQL expression by the top-level division operator.
    
    Handles nested parentheses, function calls, and label matchers.
    Only splits on '/' that is not inside parentheses or braces.
    """
    depth = 0
    brace_depth = 0
    split_positions = []
    
    for i, ch in enumerate(expr):
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        elif ch == '{':
            brace_depth += 1
        elif ch == '}':
            brace_depth -= 1
        elif ch == '/' and depth == 0 and brace_depth == 0:
            split_positions.append(i)
    
    if not split_positions:
        return [expr]
    
    # Take the first top-level division
    pos = split_positions[0]
    return [expr[:pos], expr[pos + 1:]]


def parse_args():
    parser = argparse.ArgumentParser(description="Monitoring setup tool")
    parser.add_argument("--prometheus-url", default=DEFAULT_PROMETHEUS_URL)
    parser.add_argument("--alertmanager-url", default=DEFAULT_ALERTMANAGER_URL)
    parser.add_argument("--grafana-url", default=DEFAULT_GRAFANA_URL)
    parser.add_argument("--grafana-api-key", default=os.environ.get("GRAFANA_API_KEY", ""))
    parser.add_argument("--slack-webhook", default=os.environ.get("SLACK_WEBHOOK", ""))
    parser.add_argument("--pagerduty-key", default=os.environ.get("PAGERDUTY_KEY", ""))
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument("--init", action="store_true", help="Initialize monitoring setup")
    parser.add_argument("--check", action="store_true", help="Check monitoring health")
    parser.add_argument("--alerts", action="store_true", help="Upload alert rules")
    parser.add_argument("--dashboards", action="store_true", help="Upload Grafana dashboards")
    parser.add_argument("--backup", action="store_true", help="Backup monitoring config")
    parser.add_argument("--output-dir", default="./monitoring_backup", help="Backup output directory")
    parser.add_argument("--validate", action="store_true", help="Validate monitoring configuration")
    parser.add_argument("--env", default="development", help="Target environment")
    return parser.parse_args()


def main():
    args = parse_args()

    if args.validate:
        print("Validating monitoring configuration...")
        print(f"  Checking {len(RECOMMENDED_ALERT_RULES)} alert rules and "
              f"{len(RECOMMENDED_RECORDING_RULES)} recording rules...")
        
        is_valid, issues = validate_self_dividing_expressions(
            RECOMMENDED_ALERT_RULES, RECOMMENDED_RECORDING_RULES
        )
        
        if is_valid:
            print("  PASS: No self-dividing expressions found.")
        else:
            print(f"  FAIL: {len(issues)} self-dividing expression(s) detected:")
            for issue in issues:
                print(f"    - {issue}")
        
        # Also check Prometheus connectivity
        prom_ok = check_prometheus(args.prometheus_url)
        if prom_ok:
            print("  PASS: Prometheus is reachable.")
        else:
            print("  WARN: Prometheus is not reachable (skipped connectivity check).")
        
        if is_valid and prom_ok:
            print("\nValidation complete: all checks passed.")
        else:
            print("\nValidation complete: issues found. See details above.")
            if not is_valid:
                sys.exit(1)
        return

    if args.check:
        print("Checking monitoring infrastructure...")
        prom_ok = check_prometheus(args.prometheus_url)
        am_ok = check_alertmanager(args.alertmanager_url)
        if prom_ok and am_ok:
            print("All monitoring services are healthy.")
        else:
            print("Some monitoring services are unhealthy.", file=sys.stderr)
            sys.exit(1)
        return

    if args.alerts:
        success = upload_prometheus_rules(
            RECOMMENDED_ALERT_RULES, args.prometheus_url, dry_run=args.dry_run
        )
        if not success:
            sys.exit(1)
        return

    if args.dashboards:
        if not args.grafana_api_key:
            print("Grafana API key is required for dashboard upload.", file=sys.stderr)
            sys.exit(1)
        for fname in os.listdir(DASHBOARD_DIR):
            if fname.endswith(".json"):
                upload_grafana_dashboard(
                    os.path.join(DASHBOARD_DIR, fname),
                    args.grafana_url,
                    args.grafana_api_key,
                    dry_run=args.dry_run,
                )
        return

    if args.backup:
        backup_monitoring_config(
            args.output_dir, args.prometheus_url,
            args.grafana_url, args.grafana_api_key,
        )
        return

    if args.init:
        print("Initializing monitoring setup...")
        print(f"  Environment: {args.env}")
        print(f"  Prometheus: {args.prometheus_url}")
        print(f"  Alertmanager: {args.alertmanager_url}")
        print(f"  Grafana: {args.grafana_url}")
        # Full init would include all steps in sequence
        upload_prometheus_rules(
            RECOMMENDED_ALERT_RULES, args.prometheus_url, dry_run=args.dry_run
        )
        configure_alertmanager_notifications(
            args.alertmanager_url,
            slack_webhook=args.slack_webhook or None,
            pagerduty_key=args.pagerduty_key or None,
            dry_run=args.dry_run,
        )
        return

    print("No action specified. Use --help for usage information.")
    sys.exit(1)


if __name__ == "__main__":
    main()