import os
import socket
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'storage/ikhost.db')



def reserve_port(folder):
    """Allocates a unique port starting from 5001 and saves it to the instance DB record.
    
    NOTE: There is a known TOCTOU window between socket.bind() verification and
    the actual process binding to the port. In multi-worker deployments, two workers
    could theoretically allocate the same port. For single-worker setups this is safe.
    """
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    try:

        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Check if already assigned
        row = cursor.execute('SELECT assigned_port FROM servers WHERE folder = ?', (folder,)).fetchone()
        if row and row['assigned_port']:
            return row['assigned_port']

        conn.execute("BEGIN IMMEDIATE")

        # Get all currently active port reservations
        rows = cursor.execute('SELECT assigned_port FROM servers WHERE assigned_port IS NOT NULL').fetchall()
        reserved = {r['assigned_port'] for r in rows}

        platform_port = None
        try:
            platform_port = int(os.environ.get('PORT', '5000'))
        except:
            pass

        port = 5000
        while True:
            if port > 65535:
                raise Exception('No free port available')
            port += 1
            if port in reserved:
                continue
            if platform_port and port == platform_port:
                continue

            # Verify if port is physically free on the host interface
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.bind(('127.0.0.1', port))
                break
            except socket.error:
                continue
            finally:
                s.close()

        cursor.execute('UPDATE servers SET assigned_port = ? WHERE folder = ?', (port, folder))
        conn.commit()
        return port
    except Exception as e:
        try:
            conn.rollback()
        except:
            pass
        raise e
    finally:
        conn.close()

def release_port(folder):
    """Releases the allocated port reservation back to the pool."""
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    try:

        conn.execute("BEGIN IMMEDIATE")
        conn.execute('UPDATE servers SET assigned_port = NULL WHERE folder = ?', (folder,))
        conn.commit()
    except Exception as e:
        try:
            conn.rollback()
        except:
            pass
        raise e
    finally:
        conn.close()
