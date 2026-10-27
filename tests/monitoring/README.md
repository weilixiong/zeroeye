# Monitoring rule regression checks

Run the standard-library setup and offline CLI tests:

```sh
python3 -B -m unittest discover -s tests -p 'test_monitoring_setup.py' -v
```

Install Prometheus `promtool`, then validate the complete generated default rule
file and run the memory-alert scenarios with the actual PromQL evaluator:

```sh
python3 -B tests/check_monitoring_rules.py /path/to/promtool
```

Validated with Prometheus/promtool 3.5.0. The helper renders rules from the real
`--alerts --dry-run` implementation into a temporary directory; the fixture
contains input series and independent expected alert states, not a copy of the
production expression. It needs no live Prometheus service or credentials.
The `.yml` fixture uses JSON syntax, a YAML-compatible subset.

`HighMemoryUsage` compares **process RSS with total machine memory**, using
`machine_memory_bytes`, already used by the recommended memory recording rule.
Both metrics must be exported for the same target with matching labels. The
rule deliberately does not join unrelated jobs/instances or sum processes: it
is neither total host usage nor a container/cgroup-limit alert. Configure a
separate rule with the appropriate exporter metrics for those requirements.
The exporter must supply machine capacity; missing/mismatched/zero/negative
capacity does not establish memory pressure and must not produce an infinite
ratio. Missing metrics require separate monitoring coverage in deployment.

The 11 scenarios cover below/exactly/above 90%, the ten-minute pending duration,
zero RSS, invalid or absent capacity, label isolation, multiple targets and a
short peak that clears before the pending period elapses. The Python checks
also assert that dry run keeps all 12 default rules and performs no network
requests or file writes.

Reference: https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/
