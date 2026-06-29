import unittest
import json
import tempfile
import os
from pathlib import Path
from log_aggregator import LogAggregator

class TestLogAggregatorParseErrors(unittest.TestCase):
    def setUp(self):
        self.aggregator = LogAggregator()

    def test_valid_json_log(self):
        line = '{"timestamp": 1600000000, "level": "info", "service": "backend", "message": "Success"}'
        res = self.aggregator._parse_line(line, "test.json", 1)
        self.assertTrue(res)
        self.assertEqual(len(self.aggregator.entries), 1)
        self.assertEqual(len(self.aggregator.parse_errors), 0)

    def test_malformed_json_log(self):
        # Starts with '{' but is malformed
        line = '{"timestamp": 1600000000, "level": "info", "service": "backend", "message": "Success", '
        res = self.aggregator._parse_line(line, "test.json", 1)
        # It gets parsed by TextLogParser as a fallback, so _parse_line returns True,
        # but we expect a parse error to be recorded for the JSON attempt.
        self.assertTrue(res)
        self.assertEqual(len(self.aggregator.parse_errors), 1)
        err = self.aggregator.parse_errors[0]
        self.assertEqual(err['parser_type'], 'json')
        self.assertEqual(err['file_path'], 'test.json')
        self.assertEqual(err['line_number'], 1)
        self.assertIn('char', err['error_message']) # standard JSONDecodeError text

    def test_parsed_json_not_dictionary(self):
        line = '[1, 2, 3]'
        # Starts with '[' or similar and expected to be JSON
        res = self.aggregator._parse_line(line, "test.json", 2)
        self.assertTrue(res)
        self.assertEqual(len(self.aggregator.parse_errors), 1)
        err = self.aggregator.parse_errors[0]
        self.assertEqual(err['parser_type'], 'json')
        self.assertEqual(err['error_message'], 'Parsed JSON is not a dictionary')

    def test_malformed_json_not_expected(self):
        # If it doesn't start with '{' and doesn't have json extension, we don't expect JSON
        line = 'some random text log'
        res = self.aggregator._parse_line(line, "test.log", 3)
        self.assertTrue(res)
        self.assertEqual(len(self.aggregator.parse_errors), 0)

    def test_nginx_log_malformed_when_expected(self):
        line = 'malformed nginx line'
        res = self.aggregator._parse_line(line, "nginx_access.log", 4)
        self.assertTrue(res)
        self.assertEqual(len(self.aggregator.parse_errors), 1)
        err = self.aggregator.parse_errors[0]
        self.assertEqual(err['parser_type'], 'nginx')
        self.assertEqual(err['error_message'], 'Line does not match Nginx log pattern')

    def test_parse_error_report_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "app.json"
            report_path = Path(tmpdir) / "report.json"
            
            with open(log_path, "w") as f:
                f.write('{"timestamp": 1600000000, "level": "info", "service": "backend", "message": "OK"}\n')
                f.write('{"timestamp": 1600000001, "level": "error", "message": "Broken", \n')
            
            self.aggregator.process_file(str(log_path))
            self.assertEqual(len(self.aggregator.parse_errors), 1)
            
            # Export report
            with open(report_path, "w") as f:
                json.dump({
                    'parse_errors': self.aggregator.parse_errors,
                    'total_errors': len(self.aggregator.parse_errors)
                }, f, indent=2)
                
            # Verify report contents
            with open(report_path, "r") as f:
                report = json.load(f)
                
            self.assertEqual(report['total_errors'], 1)
            self.assertEqual(len(report['parse_errors']), 1)
            err = report['parse_errors'][0]
            self.assertEqual(err['parser_type'], 'json')
            self.assertEqual(err['file_path'], str(log_path))
            self.assertEqual(err['line_number'], 2)
            # Ensure no secret-looking/raw log leakage
            self.assertNotIn("Broken", err['error_message'])

if __name__ == '__main__':
    unittest.main()
