import os
import unittest
os.environ['NEHOST_TESTING'] = 'true'

from app import create_app
import helpers

class TestServersRoute(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        db = helpers.get_db()
        db.execute("DELETE FROM servers WHERE user_id = 777")
        db.execute("DELETE FROM users WHERE id = 777")
        db.execute("INSERT INTO users (id, fname, lname, username, email, password, server_limit, role) VALUES (777, 'Srv', 'User', 'srv_test_user', 'srv_test@example.com', 'pass', 5, 'free')")
        db.commit()
        db.close()

    def tearDown(self):
        db = helpers.get_db()
        db.execute("DELETE FROM servers WHERE user_id = 777")
        db.execute("DELETE FROM users WHERE id = 777")
        db.commit()
        db.close()

    def test_add_srv_user_none(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = 999999  # Non-existent user ID

        response = self.client.post(
            '/api/v1/servers',
            json={'name': 'my_server'}
        )
        self.assertEqual(response.status_code, 404)
        data = response.get_json()
        self.assertEqual(data.get('status'), 'error')
        self.assertIn('User not found', data.get('msg', ''))

    def test_add_srv_valid_user(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = 777

        response = self.client.post(
            '/api/v1/servers',
            json={'name': 'valid_server'}
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data.get('status'), 'success')
        folder = data.get('folder')
        self.assertTrue(folder.startswith('valid_server_'))

if __name__ == '__main__':
    unittest.main()
