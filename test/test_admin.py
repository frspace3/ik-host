import os
import unittest
os.environ['NEHOST_TESTING'] = 'true'

from app import create_app
import helpers

class TestAdminRoute(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        db = helpers.get_db()
        db.execute("INSERT OR IGNORE INTO users (id, fname, lname, username, email, password, server_limit, ram_limit, cpu_limit) VALUES (888, 'Admin', 'User', 'admin_test_user', 'admin_test@example.com', 'pass', 5, 100, 100)")
        db.commit()
        db.close()

    def test_update_user_handles_none_values(self):
        with self.client.session_transaction() as sess:
            sess['admin_logged'] = True

        # Send JSON with None values for limits
        response = self.client.post(
            '/api/v1/admin/users/update',
            json={'user_id': 888, 'limit': None, 'ram_limit': None, 'cpu_limit': None, 'role': 'free', 'status': 'active'}
        )
        self.assertEqual(response.status_code, 200)

        db = helpers.get_db()
        user = db.execute("SELECT * FROM users WHERE id = 888").fetchone()
        db.close()
        self.assertIsNotNone(user)
        self.assertEqual(user['server_limit'], 5)

    def test_bulk_limit_handles_none_values(self):
        with self.client.session_transaction() as sess:
            sess['admin_logged'] = True

        response = self.client.post(
            '/api/v1/admin/users/bulk-limit',
            json={'ram_limit': None, 'cpu_limit': None}
        )
        self.assertEqual(response.status_code, 200)

if __name__ == '__main__':
    unittest.main()
