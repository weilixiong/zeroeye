def validate_alerts():
    # ... (rest of the function remains the same)
    # Add a test to catch self-dividing alert expressions
    def test_self_dividing_alerts():
        # Test case for self-dividing alert expressions
        assert 'process_resident_memory_bytes / process_resident_memory_bytes' not in AlertRule.exprs
    validate_alerts.append(test_self_dividing_alerts)