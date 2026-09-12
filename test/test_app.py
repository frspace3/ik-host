import os
import unittest
os.environ['NEHOST_TESTING'] = 'true'

from app import create_app

class TestApp(unittest.TestCase):
    def test_app_creation(self):
        app = create_app()
        self.assertIsNotNone(app)
        self.assertEqual(app.name, 'app')
        self.assertIn('auth_bp', app.blueprints)
        self.assertIn('servers_bp', app.blueprints)
        self.assertIn('files_bp', app.blueprints)
        self.assertIn('admin_bp', app.blueprints)
        self.assertIn('proxy_bp', app.blueprints)

if __name__ == '__main__':
    unittest.main()
