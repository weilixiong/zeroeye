import prometheus_client

# ... other imports ...

# Define the HighMemoryUsage alert
HIGH_MEMORY_USAGE_ALERT = "
  ALERT HighMemoryUsage
  IF process_resident_memory_bytes / (node_memory_MemTotal_bytes - node_memory_MemFree_bytes) > 0.9
  LABELS {
    severity = \"critical\"
  }
  ANNOTATIONS {
    summary = \"High memory usage detected\",
    description = \"The process is using more than 90% of the available memory.\"
  }
"

# ... rest of the file content ...
