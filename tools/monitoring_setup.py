def setup_alerts():
    # ... (rest of the function remains the same)
    high_memory_usage = AlertRule('HighMemoryUsage',
        expr='process_resident_memory_bytes / (node_memory_MemAvailable / node_memory_MemTotal) > 0.9',
        for='node', labels={'severity': 'warning'}
    )