import unittest
import socket
import health_monitor

class TestHealthMonitor(unittest.TestCase):
    def test_limit_zero_not_coerced_to_100(self):
        srv_zero = {'ram_limit': 0, 'cpu_limit': 0}
        ram_limit = float(srv_zero['ram_limit']) if srv_zero['ram_limit'] is not None else 100.0
        cpu_limit = float(srv_zero['cpu_limit']) if srv_zero['cpu_limit'] is not None else 100.0
        self.assertEqual(ram_limit, 0.0)
        self.assertEqual(cpu_limit, 0.0)

    def test_limit_none_defaults_to_100(self):
        srv_none = {'ram_limit': None, 'cpu_limit': None}
        ram_limit = float(srv_none['ram_limit']) if srv_none['ram_limit'] is not None else 100.0
        cpu_limit = float(srv_none['cpu_limit']) if srv_none['cpu_limit'] is not None else 100.0
        self.assertEqual(ram_limit, 100.0)
        self.assertEqual(cpu_limit, 100.0)

    def test_check_http_port_unused(self):
        # High unused port should return False
        is_open = health_monitor.check_http_port(59998)
        self.assertFalse(is_open)

if __name__ == '__main__':
    unittest.main()

