import os, sqlite3, zipfile, subprocess, signal, shutil, psutil, time, datetime, sys, threading
from flask import has_app_context, g, jsonify, session, request
from werkzeug.security import generate_password_hash, check_password_hash

import port_manager
import telegram_monitor

# ─── Global State ──────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
running_procs = {}
start_times   = {}
procs_lock    = threading.Lock()

PROTECTED_FILES = ['sitecustomize.py', 'security_preload.js', 'security_preload.cjs', 'HACK_ATTEMPT_DETECTED']

# ─── Standardized Response Helpers ─────────────────────────────────────────────
def api_success(msg='', status_code=200, **kwargs):
    """Return a standardized success JSON response."""
    response = {'status': 'success'}
    if msg: response['msg'] = msg
    response.update(kwargs)
    return jsonify(response), status_code

def api_error(msg, status_code=400):
    """Return a standardized error JSON response."""
    return jsonify({'status': 'error', 'msg': msg}), status_code

# ─── Database ──────────────────────────────────────────────────────────────────
def get_db():
    db_path = os.path.join(BASE_DIR, 'storage/ikhost.db')
    conn = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    if has_app_context():
        if not hasattr(g, '_db_connections'):
            g._db_connections = []
        g._db_connections.append(conn)
    return conn

# ─── Path Safety ───────────────────────────────────────────────────────────────
def is_safe_path(base_dir, path):
    base_dir = os.path.abspath(base_dir)
    path = os.path.abspath(path)
    try:
        common = os.path.commonpath([base_dir, path])
        return os.path.normcase(common) == os.path.normcase(base_dir)
    except ValueError:
        return False

def flatten_extracted_folder(extracted_path):
    try:
        items = os.listdir(extracted_path)
        items = [i for i in items if i != '__MACOSX']
        if len(items) == 1:
            single_dir = os.path.join(extracted_path, items[0])
            if os.path.isdir(single_dir):
                for sub_item in os.listdir(single_dir):
                    src = os.path.join(single_dir, sub_item)
                    dst = os.path.join(extracted_path, sub_item)
                    if os.path.exists(dst):
                        if os.path.isdir(dst):
                            shutil.rmtree(dst)
                        else:
                            os.remove(dst)
                    shutil.move(src, dst)
                try:
                    os.rmdir(single_dir)
                except:
                    pass
    except Exception as e:
        print(f"Error flattening folder: {e}")

# ─── Access Control ────────────────────────────────────────────────────────────
def is_hacked(folder):
    return False

def check_server_access(folder):
    """Checks if the current session belongs to the server owner or admin."""
    if is_hacked(folder):
        return False, api_error('you cant hack anything from here . so you should go and fuck your self 🤣', 403)

    if not session.get('admin_logged') and 'user_id' not in session:
        return False, api_error('Not logged in', 401)

    if not session.get('admin_logged'):
        db = get_db()
        srv = db.execute('SELECT user_id FROM servers WHERE folder=?', (folder,)).fetchone()
        if not srv or srv['user_id'] != session['user_id']:
            return False, api_error('Access denied', 403)

    return True, None

# ─── Process Management ────────────────────────────────────────────────────────
def get_process_resources(pid):
    """
    Calculates CPU percentage and RAM usage (RSS in MB) for a given process PID,
    including all recursively spawned child processes.
    This ensures accurate memory measurement for applications like Gunicorn, Node.js,
    or shell wrappers that spawn worker/child processes.
    Returns: (cpu_str, ram_str, ram_mb_float)
    """
    if not pid or not psutil.pid_exists(pid):
        return "0%", "0MB", 0.0
    try:
        proc = psutil.Process(pid)
        total_rss = proc.memory_info().rss
        total_cpu = proc.cpu_percent(interval=None) or 0.0

        try:
            for child in proc.children(recursive=True):
                try:
                    total_rss += child.memory_info().rss
                    total_cpu += child.cpu_percent(interval=None) or 0.0
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

        ram_mb = total_rss / (1024 * 1024)
        return f"{total_cpu:.1f}%", f"{ram_mb:.1f}MB", ram_mb
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return "0%", "0MB", 0.0
    except Exception:
        return "0%", "0MB", 0.0

_start_lock = threading.Lock()
_starting_instances = set()

def kill_process_by_pid(pid):
    if not pid: return
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        for child in children:
            try:
                child.kill()
            except:
                pass
        parent.kill()
        try:
            psutil.wait_procs(children + [parent], timeout=0.1)
        except Exception:
            pass
    except Exception:
        if os.name != 'nt':
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except:
                pass
        else:
            try:
                os.kill(pid, signal.SIGTERM)
            except:
                pass

def _write_if_changed(filepath, content):
    """Write file only if it doesn't exist or content differs."""
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                if f.read() == content:
                    return  # Already up to date
    except Exception:
        pass
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

def start_instance_by_folder(folder, act='start'):
    with _start_lock:
        if folder in _starting_instances:
            return True
        _starting_instances.add(folder)
    try:
        return _do_start_instance(folder, act)
    finally:
        with _start_lock:
            _starting_instances.discard(folder)

def stop_instance_by_folder(folder):
    """Stops an instance by folder name, killing its PID and updating DB status."""
    db = get_db()
    try:
        row = db.execute('SELECT pid FROM servers WHERE folder=?', (folder,)).fetchone()
        with procs_lock:
            old_proc = running_procs.pop(folder, None)
            t_pid = old_proc.pid if old_proc else (row['pid'] if row else None)
            start_times.pop(folder, None)
        if t_pid and psutil.pid_exists(t_pid):
            kill_process_by_pid(t_pid)
        db.execute('UPDATE servers SET pid=NULL, status="Offline" WHERE folder=?', (folder,))
        db.commit()
        
        path = os.path.join(BASE_DIR, 'storage/instances', folder)
        logpath = os.path.join(path, 'console.log')
        if os.path.exists(path):
            now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            try:
                with open(logpath, 'a', encoding='utf-8') as f:
                    f.write(f"\n[{now}] 🛑 Instance STOPPED via Admin/Bot Command\n")
            except Exception:
                pass
        return True
    except Exception as e:
        print(f"[stop_instance_by_folder] Error stopping {folder}: {e}")
        return False
    finally:
        db.close()

def _do_start_instance(folder, act='start'):
    path = os.path.join(BASE_DIR, 'storage/instances', folder)
    logpath = os.path.join(path, 'console.log')
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    db = get_db()
    row = db.execute('SELECT pid,startup,assigned_port FROM servers WHERE folder=?', (folder,)).fetchone()
    if not row:
        db.close()
        return False

    old_pid = row['pid']
    startup = row['startup'] or 'main.py'
    assigned_port = row['assigned_port']

    is_owner = False
    user_row = db.execute('SELECT username FROM users WHERE id = (SELECT user_id FROM servers WHERE folder = ?)', (folder,)).fetchone()
    if user_row:
        owner_config = telegram_monitor.read_config()
        owner_username = owner_config.get('owner_username', 'imran').strip().lower()
        if user_row['username'].strip().lower() == owner_username:
            is_owner = True

    # Kill old process if running and pop from tracking dictionary
    with procs_lock:
        old_proc = running_procs.pop(folder, None)
        t_pid = old_proc.pid if old_proc else old_pid
        start_times.pop(folder, None)

    if t_pid and psutil.pid_exists(t_pid):
        kill_process_by_pid(t_pid)

    try:
        os.makedirs(path, exist_ok=True)

        # 1. Recreate sitecustomize.py dynamically
        sc_path = os.path.join(path, 'sitecustomize.py')
        sc_code = r'''import os
import sys
import socket

# Low-level socket bind patch to force the assigned port
try:
    if not hasattr(socket.socket, '_original_bind'):
        socket.socket._original_bind = socket.socket.bind
        def patched_bind(self, address, *args, **kwargs):
            env_port = os.environ.get("PORT")
            if env_port and isinstance(address, tuple) and len(address) >= 2:
                host, port = address[0], address[1]
                if isinstance(port, int) and port != 0:
                    address = (host, int(env_port)) + address[2:]
            return socket.socket._original_bind(self, address, *args, **kwargs)
        socket.socket.bind = patched_bind
except Exception:
    pass

# Auto-patch Flask to listen on the assigned port
try:
    import flask
    if not hasattr(flask.Flask, '_original_run'):
        flask.Flask._original_run = flask.Flask.run
        def patched_run(self, host=None, port=None, *args, **kwargs):
            env_port = os.environ.get("PORT")
            if env_port:
                port = int(env_port)
            env_host = os.environ.get("HOST")
            if env_host:
                host = env_host
            return flask.Flask._original_run(self, host=host, port=port, *args, **kwargs)
        flask.Flask.run = patched_run
except Exception:
    pass

# Auto-patch Flask-SocketIO to listen on the assigned port
try:
    import flask_socketio
    if not hasattr(flask_socketio.SocketIO, '_original_run'):
        flask_socketio.SocketIO._original_run = flask_socketio.SocketIO.run
        def patched_socketio_run(self, app, host=None, port=None, *args, **kwargs):
            env_port = os.environ.get("PORT")
            if env_port:
                port = int(env_port)
            env_host = os.environ.get("HOST")
            if env_host:
                host = env_host
            return flask_socketio.SocketIO._original_run(self, app, host=host, port=port, *args, **kwargs)
        flask_socketio.SocketIO.run = patched_socketio_run
except Exception:
    pass

# Auto-patch Uvicorn to listen on the assigned port
try:
    import uvicorn
    if not hasattr(uvicorn, '_original_run'):
        uvicorn._original_run = uvicorn.run
        def patched_uvicorn_run(app, *args, **kwargs):
            env_port = os.environ.get("PORT")
            if env_port:
                kwargs["port"] = int(env_port)
            env_host = os.environ.get("HOST")
            if env_host:
                kwargs["host"] = env_host
            return uvicorn._original_run(app, *args, **kwargs)
        uvicorn.run = patched_uvicorn_run
except Exception:
    pass
'''
        # Only write if missing or content changed (avoid unnecessary disk I/O on restarts)
        _write_if_changed(sc_path, sc_code)

        # 2. Recreate security_preload.cjs dynamically
        js_path = os.path.join(path, 'security_preload.cjs')
        js_code = r'''try {
    const net = require('net');
    const originalListen = net.Server.prototype.listen;
    net.Server.prototype.listen = function(...args) {
        if (process.env.PORT) {
            const port = parseInt(process.env.PORT);
            if (typeof args[0] === 'number' || (typeof args[0] === 'string' && !isNaN(Number(args[0])))) {
                args[0] = port;
            } else if (args[0] && typeof args[0] === 'object') {
                if ('port' in args[0]) args[0].port = port;
            }
        }
        return originalListen.apply(this, args);
    };
} catch (e) {}
'''
        _write_if_changed(js_path, js_code)

        flog = open(logpath, 'a', encoding='utf-8')
    except:
        try:
            flog = open(logpath, 'a')
        except Exception as e:
            db.close()
            return False

    flog.write(f"\n[{now}] 🚀 Instance {act.upper()}ED\n")
    flog.flush()

    env = os.environ.copy()
    env.pop('WERKZEUG_SERVER_FD', None)
    env.pop('WERKZEUG_RUN_MAIN', None)
    if assigned_port:
        env['PORT'] = str(assigned_port)
        env['HOST'] = '0.0.0.0'
    env['INSTANCE_ID'] = folder
    env['PLATFORM_PORT'] = str(os.environ.get('PORT', 5000))

    preload_path = os.path.join(path, 'security_preload.cjs')
    env['NODE_OPTIONS'] = f'--require "{preload_path}"'

    # Add instance path to PYTHONPATH to ensure sitecustomize.py is loaded early
    existing_pythonpath = env.get('PYTHONPATH', '')
    if existing_pythonpath:
        env['PYTHONPATH'] = path + os.pathsep + existing_pythonpath
    else:
        env['PYTHONPATH'] = path

    cmd_run = startup
    if assigned_port:
        cmd_run = cmd_run.replace('$PORT', str(assigned_port)).replace('%PORT%', str(assigned_port))

    # Auto-install requirements.txt if present inside instance directory
    req_file = os.path.join(path, 'requirements.txt')
    if os.path.isfile(req_file):
        try:
            flog.write(f"[{now}] 📦 Auto-checking requirements.txt dependencies...\n")
            flog.flush()
            python_exec = sys.executable or 'python'
            subprocess.run(
                [python_exec, '-m', 'pip', 'install', '-r', 'requirements.txt'],
                cwd=path, stdout=flog, stderr=flog, timeout=120
            )
            flog.write(f"[{now}] ✓ Dependencies check complete.\n")
            flog.flush()
        except Exception as ex_req:
            flog.write(f"[{now}] ⚠ Requirements auto-install warning: {ex_req}\n")
            flog.flush()

    popen_kwargs = {'cwd': path, 'stdout': flog, 'stderr': flog, 'stdin': subprocess.PIPE, 'env': env, 'shell': True}
    if os.name != 'nt':
        popen_kwargs['preexec_fn'] = os.setsid

    try:
        proc = subprocess.Popen(cmd_run, **popen_kwargs)
        with procs_lock:
            running_procs[folder] = proc
            start_times[folder] = time.time()
        if act in ['start', 'restart']:
            db.execute('UPDATE servers SET pid=?, status="Running", restart_count=0 WHERE folder=?', (proc.pid, folder))
        else:
            db.execute('UPDATE servers SET pid=?, status="Running" WHERE folder=?', (proc.pid, folder))
        db.commit()
        db.close()
        try:
            flog.close()
        except:
            pass
        return True
    except Exception as e:
        try:
            if flog and not flog.closed:
                flog.write(f"[{now}] ✗ Failed to start: {str(e)}\n")
                flog.close()
        except:
            pass
        try:
            db.close()
        except:
            pass
        return False

# ─── Database Initialization ───────────────────────────────────────────────────
def _is_valid_sqlite(path):
    if not os.path.exists(path):  return True
    if os.path.getsize(path) == 0: return False
    try:
        with open(path, 'rb') as f:
            return f.read(16) == b'SQLite format 3\x00'
    except: return False

def init_db():
    db_path = os.path.join(BASE_DIR, 'storage/ikhost.db')
    os.makedirs(os.path.join(BASE_DIR, 'storage'), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, 'storage/instances'), exist_ok=True)
    if not _is_valid_sqlite(db_path):
        print('[init_db] Corrupted DB — removing and rebuilding.')
        os.remove(db_path)

    db = get_db()
    db.execute('''CREATE TABLE IF NOT EXISTS users (
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
        notifications TEXT    DEFAULT '',
        ram_limit     INTEGER DEFAULT 100,
        cpu_limit     INTEGER DEFAULT 100
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS servers (
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
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS tickets (
        id         INTEGER   PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER   NOT NULL,
        subject    TEXT      NOT NULL,
        message    TEXT      NOT NULL,
        status     TEXT      DEFAULT 'open',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS admin_settings (
        id          INTEGER PRIMARY KEY,
        username    TEXT,
        password    TEXT,
        popup_title TEXT DEFAULT '',
        popup_msg   TEXT DEFAULT '',
        popup_img   TEXT DEFAULT '',
        show_popup  INTEGER DEFAULT 0
    )''')
    # Synchronize admin credentials from config.txt
    owner_config = telegram_monitor.read_config()
    admin_user = owner_config.get('admin_username', 'imran112233').strip()
    admin_pass = owner_config.get('admin_password', 'imran112233').strip()
    hashed_pass = generate_password_hash(admin_pass)

    row_1 = db.execute('SELECT * FROM admin_settings WHERE id=1').fetchone()
    if not row_1:
        db.execute('INSERT INTO admin_settings (id, username, password, popup_title, popup_msg, popup_img, show_popup) VALUES (1, ?, ?, "Welcome to IK Host!", "", "", 0)', (admin_user, hashed_pass))
    else:
        db.execute('UPDATE admin_settings SET username=?, password=? WHERE id=1', (admin_user, hashed_pass))
    db.commit()

    # Run migrations for existing database columns
    cursor = db.cursor()
    cursor.execute("PRAGMA table_info(servers)")
    columns = [row['name'] for row in cursor.fetchall()]

    migrations = {
        'project_type': "TEXT DEFAULT 'script'",
        'assigned_port': "INTEGER",
        'startup_command': "TEXT",
        'public_url': "TEXT",
        'health_status': "TEXT DEFAULT 'Unknown'",
        'last_health_check': "TEXT",
        'restart_count': "INTEGER DEFAULT 0",
        'uptime': "TEXT",
        'auto_restart_enabled': "INTEGER DEFAULT 0",
        'auto_restart_time': "TEXT DEFAULT NULL",
        'last_auto_restart': "TEXT DEFAULT NULL"
    }

    for col, definition in migrations.items():
        if col not in columns:
            print(f"[Migration] Adding column {col} to servers table.")
            try:
                db.execute(f"ALTER TABLE servers ADD COLUMN {col} {definition}")
            except Exception as e:
                print(f"[Migration] Error adding column {col}: {e}")

    # Users table migrations
    cursor.execute("PRAGMA table_info(users)")
    u_columns = [row['name'] for row in cursor.fetchall()]
    if 'ram_limit' not in u_columns:
        print("[Migration] Adding column ram_limit to users table.")
        try:
            db.execute("ALTER TABLE users ADD COLUMN ram_limit INTEGER DEFAULT 100")
        except Exception as e:
            print(f"[Migration] Error adding column ram_limit: {e}")

    if 'cpu_limit' not in u_columns:
        print("[Migration] Adding column cpu_limit to users table.")
        try:
            db.execute("ALTER TABLE users ADD COLUMN cpu_limit INTEGER DEFAULT 100")
        except Exception as e:
            print(f"[Migration] Error adding column cpu_limit: {e}")

    if 'created_at' not in u_columns:
        print("[Migration] Adding column created_at to users table.")
        try:
            db.execute("ALTER TABLE users ADD COLUMN created_at TEXT DEFAULT NULL")
        except Exception as e:
            print(f"[Migration] Error adding column created_at: {e}")

    db.commit()
    db.close()

def get_secret_key():
    secret_path = os.path.join(BASE_DIR, 'storage/secret_key.bin')
    if os.path.exists(secret_path):
        try:
            with open(secret_path, 'rb') as f:
                return f.read()
        except:
            pass
    key = os.urandom(32)
    try:
        os.makedirs(os.path.join(BASE_DIR, 'storage'), exist_ok=True)
        with open(secret_path, 'wb') as f:
            f.write(key)
    except:
        pass
    return key

# ─── Uptime ────────────────────────────────────────────────────────────────────
def get_precise_uptime(ts):
    if not ts: return "Offline"
    diff = int(time.time() - ts)
    months, r = divmod(diff, 2592000)
    days,   r = divmod(r, 86400)
    hours,  r = divmod(r, 3600)
    minutes,_ = divmod(r, 60)
    parts = []
    if months: parts.append(f"{months}mo")
    if days:   parts.append(f"{days}d")
    if hours:  parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)
