import os
import shutil
import unittest
os.environ['NEHOST_TESTING'] = 'true'

from app import create_app
import helpers

class TestFilesRoute(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.test_folder = 'test_files_instance'
        self.instance_path = os.path.join(self.app.config['BASE_STORAGE'], self.test_folder)
        os.makedirs(self.instance_path, exist_ok=True)

        db = helpers.get_db()
        db.execute("INSERT OR IGNORE INTO users (id, fname, lname, username, email, password) VALUES (999, 'Test', 'User', 'testuser_files', 'test_files@example.com', 'pass')")
        db.execute("INSERT OR REPLACE INTO servers (user_id, name, folder, status) VALUES (999, 'Test Server', ?, 'Offline')", (self.test_folder,))
        db.commit()
        db.close()

    def tearDown(self):
        if os.path.exists(self.instance_path):
            shutil.rmtree(self.instance_path, ignore_errors=True)

    def test_fsave_handles_null_content(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = 999
        
        response = self.client.post(
            f'/api/v1/files/{self.test_folder}/save',
            json={'name': 'sample.txt', 'content': None, 'path': ''}
        )
        self.assertEqual(response.status_code, 200)
        file_p = os.path.join(self.instance_path, 'sample.txt')
        self.assertTrue(os.path.exists(file_p))
        with open(file_p, 'r', encoding='utf-8') as f:
            self.assertEqual(f.read(), '')

    def test_create_file_route_utf8(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = 999

        response = self.client.post(
            f'/api/v1/files/{self.test_folder}/create-file',
            json={'name': 'newfile.py', 'path': ''}
        )
        self.assertEqual(response.status_code, 200)
        file_p = os.path.join(self.instance_path, 'newfile.py')
        self.assertTrue(os.path.exists(file_p))

if __name__ == '__main__':
    unittest.main()
