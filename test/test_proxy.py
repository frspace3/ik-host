import os
import unittest
os.environ['NEHOST_TESTING'] = 'true'

from app import create_app
import helpers

class TestProxyRoute(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

        db = helpers.get_db()
        db.execute("INSERT OR REPLACE INTO users (id, fname, lname, username, email, password) VALUES (8888, 'Proxy', 'User', 'proxyuser', 'proxy@example.com', 'pass')")
        db.execute("INSERT OR REPLACE INTO servers (user_id, name, folder, status, assigned_port, server_status) VALUES (8888, 'Proxy Server', 'proxy_srv_folder', 'Running', 5999, 'active')")
        db.commit()
        db.close()

    def test_proxy_query_string_decoding(self):
        # Pass non-UTF8 bytes in query string to verify errors='replace' prevents UnicodeDecodeError crash
        response = self.client.get('/instance/proxy_srv_folder?invalid=\xff\xfe\xfa', follow_redirects=True)
        # Since 127.0.0.1:5999 has no server running, it will catch connection error and return 502 (not 500 UnicodeDecodeError)
        self.assertEqual(response.status_code, 502)
        self.assertIn(b"Reverse Proxy connection error", response.data)

    def test_proxy_non_existent_folder(self):
        response = self.client.get('/instance/non_existent_proxy_folder', follow_redirects=True)
        self.assertEqual(response.status_code, 404)
        self.assertIn(b"Instance not found", response.data)

if __name__ == '__main__':
    unittest.main()
