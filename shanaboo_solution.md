 ```diff
--- /dev/null
+++ b/tools/verify_diagnostics.py
@@ -0,0 +1,268 @@
+#!/usr/bin/env python3
+
+import argparse
+import json
+import os
+import subprocess
+import sys
+from pathlib import Path
+from typing import Any, Optional
+
+ROOT = Path(__file__).resolve().parent.parent
+DIAGNOSTIC_DIR = ROOT / "diagnostic"
+
+
+def parse_args() -> argparse.Namespace:
+    parser = argparse.ArgumentParser(
+        description="Verify build diagnostics and report results.",
+        formatter_class=argparse.RawDescriptionHelpFormatter,
+    )
+    parser.add_argument(
+        "--verbose",
+        action="store_true",
+        help="Enable verbose output.",
+    )
+    parser.add_argument(
+        "--json",
+        action="store_true",
+        help="Output results in JSON format for machine consumption.",
+    )
+    parser.add_argument(
+        "--threshold",
+        type=int,
+        default=0,
+        help="Minimum number of passing modules required (default: 0).",
+    )
+    return parser.parse_args()
+
+
+def find_diagnostic_files() -> tuple[list[Path], list[Path]]:
+    """Find all .logd and .json diagnostic files in the diagnostic directory."""
+    logd_files: list[Path] = []
+    json_files: list[Path] = []
+
+    if not DIAGNOSTIC_DIR.exists():
+        return logd_files, json_files
+
+    for path in DIAGNOSTIC_DIR.iterdir():
+        if path.is_file():
+            if path.suffix == ".logd":
+                logd_files.append(path)
+            elif path.suffix == ".json":
+                json_files.append(path)
+
+    return logd_files, json_files
+
+
+def validate_json_schema(data: Any) -> list[str]:
+    """Validate the structure of diagnostic metadata JSON and return list of errors."""
+    errors: list[str] = []
+
+    if not isinstance(data, dict):
+        errors.append("Root JSON must be an object")
+        return errors
+
+    required_keys = ["commit_id", "timestamp", "modules"]
+    for key in required_keys:
+        if key not in data:
+            errors.append(f"Missing required key: '{key}'")
+
+    if "modules" in data:
+        if not isinstance(data["modules"], list):
+            errors.append("'modules' must be a list")
+        else:
+            for i, module in enumerate(data["modules"]):
+                if not isinstance(module, dict):
+                    errors.append(f"Module at index {i} must be an object")
+                    continue
+                if "name" not in module:
+                    errors.append(f"Module at index {i} missing 'name'")
+                if "status" not in module:
+                    errors.append(f"Module at index {i} missing 'status'")
+
+    return errors
+
+
+def run_build(verbose: bool) -> tuple[bool, str]:
+    """Run the build script and return (success, error_message)."""
+    try:
+        cmd = [sys.executable, str(ROOT / "build.py")]
+        if verbose:
+            print(f"Running: {' '.join(cmd)}")
+
+        result = subprocess.run(
+            cmd,
+            cwd=str(ROOT),
+            capture_output=True,
+            text=True,
+            timeout=300,
+        )
+
+        if result.returncode != 0:
+            error_msg = f"Build failed with exit code {result.returncode}"
+            if result.stderr:
+                error_msg += f"\nStderr: {result.stderr.strip()}"
+            return False, error_msg
+
+        return True, ""
+
+    except subprocess.TimeoutExpired:
+        return False, "Build timed out after 300 seconds"
+    except FileNotFoundError:
+        return False, f"Build script not found: {ROOT / 'build.py'}"
+    except PermissionError:
+        return False, f"Permission denied executing: {ROOT / 'build.py'}"
+    except Exception as e:
+        return False, f"Unexpected error running build: {type(e).__name__}: {e}"
+
+
+def verify_diagnostics(args: argparse.Namespace) -> dict[str, Any]:
+    """Run diagnostics verification and return results."""
+    results: dict[str, Any] = {
+        "success": False,
+        "build_success": False,
+        "logd_files": [],
+        "json_files": [],
+        "schema_errors": [],
+        "passing_modules": 0,
+        "threshold_met": False,
+        "messages": [],
+    }
+
+    # Run build
+    build_success, build_error = run_build(args.verbose)
+    results["build_success"] = build_success
+
+    if not build_success:
+        results["messages"].append(f"Build failed: {build_error}")
+        if args.verbose:
+            print(f"ERROR: {build_error}")
+
+    # Find diagnostic files
+    logd_files, json_files = find_diagnostic_files()
+    results["logd_files"] = [str(f.name) for f in logd_files]
+    results["json_files"] = [str(f.name) for f in json_files]
+
+    # Validate JSON schema for each metadata file
+    for json_file in json_files:
+        try:
+            with open(json_file, "r", encoding="utf-8") as f:
+                data = json.load(f)
+
+            schema_errors = validate_json_schema(data)
+            if schema_errors:
+                for error in schema_errors:
+                    msg = f"Schema error in {json_file.name}: {error}"
+                    results["schema_errors"].append(msg)
+                    if args.verbose:
+                        print(f"ERROR: {msg}")
+            else:
+                if "modules" in data and isinstance(data["modules"], list):
+                    for module in data["modules"]:
+                        if isinstance(module, dict) and module.get("status") == "pass":
+                            results["passing_modules"] += 1
+        except json.JSONDecodeError as e:
+            msg = f"Invalid JSON in {json_file.name}: {e}"
+            results["schema_errors"].append(msg)
+            if args.verbose:
+                print(f"ERROR: {msg}")
+        except Exception as e:
+            msg = f"Error reading {json_file.name}: {type(e).__name__}: {e}"
+            results["schema_errors"].append(msg)
+            if args.verbose:
+                print(f"ERROR: {msg}")
+
+    # Check threshold
+    results["threshold_met"] = results["passing_modules"] >= args.threshold
+    results["success"] = build_success and results["threshold_met"]