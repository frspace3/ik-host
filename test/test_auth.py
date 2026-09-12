import datetime
import os
import unittest
os.environ['NEHOST_TESTING'] = 'true'

from app import create_app
from routes.auth import parse_created_at
import helpers

class TestAuthRoute(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        db = helpers.get_db()
        db.execute("DELETE FROM users WHERE email = 'johndoe@example.com' OR username = 'johndoe'")
        db.commit()
        db.close()

    def tearDown(self):
        db = helpers.get_db()
        db.execute("DELETE FROM users WHERE email = 'johndoe@example.com' OR username = 'johndoe'")
        db.commit()
        db.close()

    def test_parse_created_at_formats(self):
        # Standard format
        dt1 = parse_created_at("2026-09-12 14:30:00")
        self.assertIsNotNone(dt1)
        self.assertEqual(dt1.year, 2026)

        # Fractional seconds
        dt2 = parse_created_at("2026-09-12 14:30:00.123456")
        self.assertIsNotNone(dt2)

        # ISO T format
        dt3 = parse_created_at("2026-09-12T14:30:00")
        self.assertIsNotNone(dt3)

        # ISO T format with fractional seconds
        dt4 = parse_created_at("2026-09-12T14:30:00.654321")
        self.assertIsNotNone(dt4)

        # ISO format with Z
        dt5 = parse_created_at("2026-09-12T14:30:00Z")
        self.assertIsNotNone(dt5)

        # Empty/None
        self.assertIsNone(parse_created_at(None))
        self.assertIsNone(parse_created_at(""))

    def test_signup_login_flow(self):
        # Signup
        signup_resp = self.client.post('/signup', data={
            'fname': 'John',
            'lname': 'Doe',
            'username': 'johndoe',
            'email': 'johndoe@example.com',
            'password': 'password123',
            'confirm_password': 'password123'
        })
        self.assertEqual(signup_resp.status_code, 200)

        # Login
        login_resp = self.client.post('/login', data={
            'email': 'johndoe@example.com',
            'password': 'password123'
        })
        self.assertEqual(login_resp.status_code, 200)

        # Dashboard access
        dash_resp = self.client.get('/dashboard')
        self.assertEqual(dash_resp.status_code, 200)

if __name__ == '__main__':
    unittest.main()
