import os
import sqlite3
import tempfile
import unittest

from storage.init_db import init_db, DB_PATH, BASE_DIR

class TestInitDb(unittest.TestCase):
    def test_base_dir_defined(self):
        self.assertTrue(os.path.isabs(BASE_DIR))
        self.assertTrue(os.path.exists(BASE_DIR))

    def test_init_db_creates_tables_and_columns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_db_dir = os.path.join(tmpdir, 'storage')
            test_db_path = os.path.join(test_db_dir, 'ikhost.db')
            
            # Patch DB_DIR and DB_PATH in storage.init_db module temporarily
            import storage.init_db as s_init
            orig_dir, orig_path = s_init.DB_DIR, s_init.DB_PATH
            s_init.DB_DIR = test_db_dir
            s_init.DB_PATH = test_db_path
            try:
                s_init.init_db()
                self.assertTrue(os.path.exists(test_db_path))

                conn = sqlite3.connect(test_db_path)
                cursor = conn.cursor()

                # Check users table columns
                cursor.execute("PRAGMA table_info(users)")
                columns = [row[1] for row in cursor.fetchall()]
                self.assertIn('created_at', columns)
                self.assertIn('ram_limit', columns)
                self.assertIn('cpu_limit', columns)

                # Check owner user created
                owner = cursor.execute("SELECT * FROM users WHERE username = 'imran'").fetchone()
                self.assertIsNotNone(owner)
                conn.close()
            finally:
                s_init.DB_DIR, s_init.DB_PATH = orig_dir, orig_path

if __name__ == '__main__':
    unittest.main()
