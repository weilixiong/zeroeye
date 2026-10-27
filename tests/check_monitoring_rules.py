#!/usr/bin/env python3
"""Validate rendered default rules and offline memory-alert scenarios with promtool."""
import argparse
import contextlib
import importlib.util
import io
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("promtool", help="Path to a Prometheus promtool executable")
    args = parser.parse_args()
    tool = shutil.which(args.promtool)
    if tool is None:
        parser.error("promtool executable not found: " + args.promtool)
    spec = importlib.util.spec_from_file_location("monitoring_setup", ROOT / "tools/monitoring_setup.py")
    monitoring = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitoring)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        monitoring.upload_prometheus_rules(monitoring.RECOMMENDED_ALERT_RULES, "http://unused.invalid", dry_run=True)
    with tempfile.TemporaryDirectory(prefix="memory-alert-") as directory:
        path = Path(directory)
        # The first dry-run line is the human status, followed by complete rule YAML.
        (path / "generated-rules.yml").write_text(output.getvalue().split("\n", 1)[1], encoding="utf-8")
        shutil.copyfile(ROOT / "tests/monitoring/high_memory_usage.test.yml", path / "high_memory_usage.test.yml")
        try:
            for command in (["check", "rules", "generated-rules.yml"], ["test", "rules", "high_memory_usage.test.yml"]):
                subprocess.run([tool, *command], cwd=path, check=True)
        except (OSError, subprocess.CalledProcessError) as error:
            print("Prometheus rule validation failed:", error)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
