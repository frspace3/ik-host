import os
import sqlite3

DB_DIR  = os.path.join(os.getcwd(), 'storage')
DB_PATH = os.path.join(DB_DIR, 'ikhost.db')

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(DB_DIR, exist_ok=True)
    os.makedirs(os.path.join(DB_DIR, 'instances'), exist_ok=True)

    db = get_db()
    cursor = db.cursor()

    # -- 1. users --
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            fname         TEXT    NOT NULL,
            lname         TEXT    NOT NULL,
            username      TEXT    NOT NULL UNIQUE,
            email         TEXT    NOT NULL UNIQUE,
            password      TEXT    NOT NULL,
            pfp           TEXT    DEFAULT 'default.png',
            role          TEXT    DEFAULT 'free',
            status        TEXT    DEFAULT 'active',
            server_limit  INTEGER DEFAULT 1,
            notifications TEXT    DEFAULT ''
        )
    ''')

    # -- 2. servers --
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS servers (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL,
            name          TEXT    NOT NULL,
            folder        TEXT    NOT NULL UNIQUE,
            status        TEXT    DEFAULT 'Offline',
            startup       TEXT    DEFAULT 'main.py',
            pid           INTEGER,
            server_status TEXT    DEFAULT 'active',
            project_type  TEXT    DEFAULT 'script',
            assigned_port INTEGER,
            startup_command TEXT,
            public_url    TEXT,
            health_status TEXT    DEFAULT 'Unknown',
            last_health_check TEXT,
            restart_count INTEGER DEFAULT 0,
            uptime        TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    # -- 3. tickets --
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            id         INTEGER   PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER   NOT NULL,
            subject    TEXT      NOT NULL,
            message    TEXT      NOT NULL,
            status     TEXT      DEFAULT 'open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    # -- 4. admin_settings --
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_settings (
            id          INTEGER PRIMARY KEY,
            username    TEXT,
            password    TEXT,
            popup_title TEXT DEFAULT '',
            popup_msg   TEXT DEFAULT '',
            popup_img   TEXT DEFAULT '',
            show_popup  INTEGER DEFAULT 0
        )
    ''')

    existing = cursor.execute(
        'SELECT id FROM admin_settings WHERE id = 1'
    ).fetchone()

    if not existing:
        cursor.execute(
            '''INSERT INTO admin_settings (id, username, password, popup_title, popup_msg, popup_img, show_popup)
               VALUES (1, ?, ?, ?, ?, ?, ?)''',
            ('imran112233', 'imran112233', 'Welcome to IK Host!', '', '', 0)
        )
        print('[?] Default admin credentials inserted.')
        print('    Username : imran112233')
        print('    Password : imran112233')
    else:
        print('[i] Admin settings already exist skipping insert.')

    # -- 5. owner user seed --
    from werkzeug.security import generate_password_hash
    owner = cursor.execute("SELECT id FROM users WHERE username = 'imran' OR email = 'imran@owner.com'").fetchone()
    if not owner:
        cursor.execute(
            '''INSERT INTO users (fname, lname, username, email, password, server_limit, role, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))''',
            ('Imran', 'Kaiser', 'imran', 'imran@owner.com', generate_password_hash('554961'), 9999, 'admin', 'active')
        )
        print('[?] Default owner user profile inserted.')
        print('    Username : imran')
        print('    Password : 554961')
    else:
        cursor.execute(
            "UPDATE users SET password = ?, server_limit = 9999, role = 'admin', status = 'active' WHERE username = 'imran' OR email = 'imran@owner.com'",
            (generate_password_hash('554961'),)
        )
        print('[i] Updated owner profile (imran / 554961) with max limits.')

    db.commit()
    db.close()

    print('\n[?] Database initialised successfully.')
    print(f'    Path : {DB_PATH}')
    print('    Tables created : users, servers, tickets, admin_settings\n')

if __name__ == '__main__':
    init_db()
