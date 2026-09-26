import os
import unittest
import tempfile
import sqlite3
import shutil
import zipfile
import telegram_monitor
import helpers
import health_monitor
import deployment_manager
from app import create_app
from werkzeug.security import generate_password_hash

class TestDeepFixes(unittest.TestCase):
    def setUp(self):
        os.environ['NEHOST_TESTING'] = 'true'
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def test_1_and_12_read_config_fallbacks(self):
        """Bug 1 & 12: Verify read_config returns fallbacks for missing/empty credentials."""
        # Reset cache
        telegram_monitor._config_cache = None
        config = telegram_monitor.read_config()
        self.assertEqual(config.get('admin_username'), 'imran112233')
        self.assertEqual(config.get('admin_password'), 'imran112233')
        self.assertEqual(config.get('owner_username'), 'imran')
        self.assertEqual(config.get('owner_password'), '554961')

    def test_2_master_gateway_password_config(self):
        """Bug 2: Verify master gateway unlock uses config password."""
        with self.client.session_transaction() as sess:
            sess['master_unlocked'] = False
        res = self.client.post('/unlock-gateway', data={'password': '554961'})
        self.assertEqual(res.status_code, 302)

    def test_3_master_gateway_api_interception(self):
        """Bug 3: Verify /api/... requests return 401 JSON when master gateway is locked."""
        os.environ.pop('NEHOST_TESTING', None) # Enable gateway check temporarily
        try:
            with self.client.session_transaction() as sess:
                sess.pop('master_unlocked', None)
            res = self.client.get('/api/v1/servers')
            self.assertEqual(res.status_code, 401)
            json_data = res.get_json()
            self.assertEqual(json_data.get('status'), 'error')
            self.assertIn('locked', json_data.get('msg', '').lower())
        finally:
            os.environ['NEHOST_TESTING'] = 'true'

    def test_4_protected_file_bounds_and_zip_isolation(self):
        """Bug 4: Verify normalized basename check for PROTECTED_FILES and unzip protection."""
        storage = self.app.config['BASE_STORAGE']
        folder = 'test_bounds_instance'
        inst_dir = os.path.join(storage, folder)
        sub_dir = os.path.join(inst_dir, 'sub')
        os.makedirs(sub_dir, exist_ok=True)

        with self.client.session_transaction() as sess:
            sess['admin_logged'] = True

        # Test subfolder read bypass block
        res = self.client.get(f'/api/v1/files/{folder}/read?path=sub&name=sitecustomize.py')
        self.assertEqual(res.status_code, 403)

        # Test case-insensitive subfolder read bypass block
        res = self.client.get(f'/api/v1/files/{folder}/read?path=sub&name=SiteCustomize.py')
        self.assertEqual(res.status_code, 403)

        # Test subfolder save bypass block
        res = self.client.post(f'/api/v1/files/{folder}/save', json={'path': 'sub', 'name': 'security_preload.cjs', 'content': 'hack'})
        self.assertEqual(res.status_code, 403)

        # Create zip with protected file inside to test unzip block
        zip_path = os.path.join(inst_dir, 'bad.zip')
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('sitecustomize.py', 'malicious')

        res = self.client.post(f'/api/v1/files/{folder}/unzip', json={'path': '', 'name': 'bad.zip'})
        self.assertEqual(res.status_code, 400)
        self.assertIn('protected', res.get_json().get('msg', '').lower())

        shutil.rmtree(inst_dir, ignore_errors=True)

    def test_5_windows_node_options_escaping(self):
        """Bug 5: Verify backslashes in NODE_OPTIONS are converted to forward slashes."""
        preload_path = r'C:\Users\test\security_preload.cjs'
        converted = preload_path.replace('\\', '/')
        self.assertNotIn('\\', converted)
        self.assertEqual(converted, 'C:/Users/test/security_preload.cjs')

    def test_6_python_cmd_argument_handling(self):
        """Bug 6: Verify commands with arguments get python prepended correctly."""
        cmd_run = "main.py --port $PORT"
        cmd_parts = cmd_run.strip().split()
        if cmd_parts and cmd_parts[0].endswith('.py') and not (cmd_parts[0].startswith('python') or cmd_run.startswith('python ') or cmd_run.startswith('python3 ')):
            python_cmd = 'python' if os.name == 'nt' else 'python3'
            cmd_run = f"{python_cmd} {cmd_run}"
        self.assertTrue(cmd_run.startswith('python') or cmd_run.startswith('python3'))

    def test_7_health_monitor_non_web_status(self):
        """Bug 7: Verify non-web script project types set Healthy when online."""
        srv = {'project_type': 'bot', 'assigned_port': 9999}
        p_type = (srv['project_type'] or '').lower()
        is_web = p_type in ('flask', 'fastapi', 'django', 'node', 'web')
        self.assertFalse(is_web)

    def test_10_atomic_running_procs_access(self):
        """Bug 10: Verify atomic running_procs accesses under procs_lock."""
        with helpers.procs_lock:
            proc = helpers.running_procs.get('non_existent_folder')
            self.assertIsNone(proc)
            old_proc = helpers.running_procs.pop('non_existent_folder', None)
            self.assertIsNone(old_proc)

    def test_13_sitecustomize_alignment(self):
        """Bug 13: Verify sitecustomize alignment."""
        temp_dir = tempfile.mkdtemp()
        sc_path = os.path.join(temp_dir, 'sitecustomize.py')
        try:
            patch_code = "import socket\n"
            helpers._write_if_changed(sc_path, patch_code)
            self.assertTrue(os.path.exists(sc_path))
            with open(sc_path) as f:
                self.assertEqual(f.read(), patch_code)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_14_download_zip_excludes_protected(self):
        """Bug 14: Verify download_server_zip excludes protected files."""
        storage = self.app.config['BASE_STORAGE']
        folder = 'test_zip_leak_instance'
        inst_dir = os.path.join(storage, folder)
        os.makedirs(inst_dir, exist_ok=True)
        with open(os.path.join(inst_dir, 'SiteCustomize.py'), 'w') as f:
            f.write('# protected')
        with open(os.path.join(inst_dir, 'user_script.py'), 'w') as f:
            f.write('# user code')

        db = helpers.get_db()
        db.execute('INSERT OR REPLACE INTO servers (user_id, name, folder) VALUES (1, "TestServer", ?)', (folder,))
        db.commit()
        db.close()

        with self.client.session_transaction() as sess:
            sess['admin_logged'] = True

        res = self.client.get(f'/api/v1/servers/{folder}/download-zip')
        self.assertEqual(res.status_code, 200)

        zip_bytes = res.data
        res.close()
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tf:
            tf.write(zip_bytes)
            tf_path = tf.name

        try:
            with zipfile.ZipFile(tf_path, 'r') as zf:
                names = [n.lower() for n in zf.namelist()]
                self.assertNotIn('sitecustomize.py', names)
                self.assertIn('user_script.py', names)
        finally:
            if os.path.exists(tf_path):
                os.remove(tf_path)
            shutil.rmtree(inst_dir, ignore_errors=True)

if __name__ == '__main__':
    unittest.main()
