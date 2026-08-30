--- /dev/null
+++ b/tools/test_monitoring_setup.py
@@ -0,0 +1,38 @@
+import pytest
+from tools.monitoring_setup import (
+    ALERTS,
+    generate_monitoring_config,
+    validate_alert_expressions,
+)
+
+def test_high_memory_usage_not_self_dividing():
+    expr = ALERTS["HighMemoryUsage"]["expr"]
+    assert "process_resident_memory_bytes / process_resident_memory_bytes" not in expr
+    assert "node_memory_MemTotal_bytes" in expr
+
+def test_validate_catches_self_divide():
+    bad = {
+        "BadAlert": {
+            "expr": "process_resident_memory_bytes / process_resident_memory_bytes > 0.5"
+        }
+    }
+    with pytest.raises(ValueError, match="self-dividing"):
+        validate_alert_expressions(bad)
+
+def test_validate_passes_valid_expression():
+    validate_alert_expressions(ALERTS)  # should not raise
+
+def test_generate_monitoring_config_dry_run(tmp_path):
+    result = generate_monitoring_config(str(tmp_path), dry_run=True)
+    assert result["dry_run"] is True
+    assert not (tmp_path / "alerts.json").exists()
+
+def test_generate_monitoring_config_writes_file(tmp_path):
+    result = generate_monitoring_config(str(tmp_path), dry_run=False)
+    out_file = tmp_path / "alerts.json"
+    assert out_file.exists()
+    import json
+    written = json.loads(out_file.read_text())
+    assert written == ALERTS
