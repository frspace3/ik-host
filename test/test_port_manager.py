import os
import sqlite3
import tempfile
import unittest

import port_manager

class TestPortManager(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, 'ikhost.db')
        self.orig_db_path = port_manager.DB_PATH
        port_manager.DB_PATH = self.db_path
        
        # Clear in-memory port tracking set for test isolation
        port_manager._allocated_ports.clear()
        
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            CREATE TABLE servers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                folder TEXT UNIQUE,
                assigned_port INTEGER
            )
        ''')
        conn.commit()
        conn.close()

    def tearDown(self):
        port_manager.DB_PATH = self.orig_db_path
        port_manager._allocated_ports.clear()
        self.tmpdir.cleanup()

    def test_reserve_and_release_port(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("INSERT INTO servers (name, folder) VALUES ('test_server', 'srv_1')")
        conn.commit()
        conn.close()

        port = port_manager.reserve_port('srv_1')
        self.assertIsInstance(port, int)
        self.assertGreater(port, 5000)
        self.assertIn(port, port_manager._allocated_ports)

        # Reserving again for same folder returns same port
        port2 = port_manager.reserve_port('srv_1')
        self.assertEqual(port, port2)

        # Reserve another server gets a different port
        conn = sqlite3.connect(self.db_path)
        conn.execute("INSERT INTO servers (name, folder) VALUES ('test_server2', 'srv_2')")
        conn.commit()
        conn.close()

        port3 = port_manager.reserve_port('srv_2')
        self.assertNotEqual(port, port3)

        # Release port
        port_manager.release_port('srv_1')
        self.assertNotIn(port, port_manager._allocated_ports)

    def test_concurrent_port_reservation(self):
        import concurrent.futures
        num_threads = 5
        conn = sqlite3.connect(self.db_path)
        for i in range(num_threads):
            conn.execute("INSERT INTO servers (name, folder) VALUES (?, ?)", (f"srv_{i}", f"folder_{i}"))
        conn.commit()
        conn.close()

        def alloc(folder):
            return port_manager.reserve_port(folder)

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(alloc, f"folder_{i}") for i in range(num_threads)]
            ports = [f.result() for f in futures]

        self.assertEqual(len(ports), num_threads)
        self.assertEqual(len(set(ports)), num_threads)  # All allocated ports must be unique!

if __name__ == '__main__':
    unittest.main()

