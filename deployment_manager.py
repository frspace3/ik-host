import os
import shutil
import zipfile
import subprocess
import sqlite3
import datetime
import port_manager
import project_detector
import startup_detector
import proxy_manager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'storage/ikhost.db')
BASE_STORAGE = os.path.join(BASE_DIR, 'storage/instances')

def is_safe_path(base_dir, path):
    base_dir = os.path.abspath(base_dir)
    path = os.path.abspath(path)
    try:
        common = os.path.commonpath([base_dir, path])
        return os.path.normcase(common) == os.path.normcase(base_dir)
    except ValueError:
        return False

def flatten_extracted_folder(extracted_path):
    import shutil
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

def run_deployment_pipeline(folder, request_host):
    """Executes the complete one-click deployment pipeline for an instance."""
    path = os.path.join(BASE_STORAGE, folder)
    logpath = os.path.join(path, 'console.log')
    now = lambda: datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Check if owner
    is_owner = False
    import telegram_monitor
    conn_check = sqlite3.connect(DB_PATH, timeout=30.0)
    try:
        user_row = conn_check.execute('SELECT username FROM users WHERE id = (SELECT user_id FROM servers WHERE folder = ?)', (folder,)).fetchone()
        if user_row:
            owner_config = telegram_monitor.read_config()
            owner_username = owner_config.get('owner_username', 'imran').strip().lower()
            if user_row[0].strip().lower() == owner_username:
                is_owner = True
    except Exception as e_check:
        print(f"Error checking owner status in deployment pipeline: {e_check}")
    finally:
        conn_check.close()

    def log(msg):
        try:
            with open(logpath, 'a', encoding='utf-8') as f:
                f.write(f"[{now()}] {msg}\n")
        except:
            pass

    try:
        log("🚀 Starting one-click deployment pipeline...")

        # 1. Unzip archive if uploaded
        zips = [f for f in os.listdir(path) if f.lower().endswith('.zip')]
        if zips:
            if len(zips) > 1:
                log(f"⚠ Multiple ZIP files found ({len(zips)}). Only processing: {zips[0]}")
            zip_name = zips[0]
            zip_path = os.path.join(path, zip_name)
            log(f"📦 Extracting {zip_name}...")
            
            # Resolve absolute instance path
            abs_instance_path = os.path.abspath(path)
            
            # Validate ZIP content to prevent Zip Slip traversal
            if not zipfile.is_zipfile(zip_path):
                raise Exception("Invalid ZIP archive upload")
                
            with zipfile.ZipFile(zip_path, 'r') as z:
                for member in z.infolist():
                    target_member_path = os.path.abspath(os.path.join(abs_instance_path, member.filename))
                    if not is_safe_path(abs_instance_path, target_member_path):
                        raise Exception(f"Directory traversal attempt detected in ZIP: {member.filename}")

                z.extractall(path)
            os.remove(zip_path)
            try:
                flatten_extracted_folder(path)
            except Exception as e_flat:
                log(f"Info: folder flattening skipped: {e_flat}")
            log("✓ Extraction complete.")
        else:
            log("ℹ No ZIP archive found (assuming script or raw file upload).")

        # 2. Detect project type
        log("🔎 Scanning project files...")
        p_type = project_detector.detect_project_type(path)
        log(f"✓ Detected project type: {p_type.upper()}")

        # 3. Port allocation
        port = None
        p_url = ""
        if True: # Always allocate a port and enable proxying for all instance types to prevent EADDRINUSE conflicts
            log("🔌 Allocating unique port...")
            port = port_manager.reserve_port(folder)
            log(f"✓ Assigned Port: {port}")
            p_url = proxy_manager.generate_public_url(folder, request_host)
            log(f"✓ Public Route: {p_url}")

        # 4. Startup command detection
        log("📝 Detecting startup command...")
        cmd = startup_detector.detect_startup_command(path, p_type)
        log(f"✓ Startup Command: {cmd}")

        # 5. Install dependencies
        if p_type == 'node':
            log("📦 Installing Node modules (npm install)...")
            try:
                conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
                try:

                    conn.execute('UPDATE servers SET status = "Installing" WHERE folder = ?', (folder,))
                    conn.commit()
                finally:
                    conn.close()
                npm_cmd = shutil.which('npm') or ('npm.cmd' if os.name == 'nt' else 'npm')
                result = subprocess.run(
                    [npm_cmd, 'install'], cwd=path,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, timeout=180
                )
                log("✓ npm install finished.")
                if result.stdout:
                    log(f"npm logs:\n{result.stdout[-1000:]}")
            except Exception as ex:
                log(f"⚠ npm install error: {str(ex)}")
        else:
            req_path = os.path.join(path, 'requirements.txt')
            if os.path.isfile(req_path):
                log("📦 Installing Python packages (pip install)...")
                try:
                    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
                    try:

                        conn.execute('UPDATE servers SET status = "Installing" WHERE folder = ?', (folder,))
                        conn.commit()
                    finally:
                        conn.close()
                    import sys
                    result = subprocess.run(
                        [sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'], cwd=path,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, timeout=180
                    )
                    log("✓ pip install finished.")
                    if result.stdout:
                        log(f"pip logs:\n{result.stdout[-1000:]}")
                except Exception as ex:
                    log(f"⚠ pip install error: {str(ex)}")

        # Create sitecustomize.py to automatically force the assigned port for Flask/FastAPI/Uvicorn/etc.
        if port:
            sc_path = os.path.join(path, 'sitecustomize.py')
            patch_code = '''import os
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
            try:
                if os.path.exists(sc_path):
                    with open(sc_path, 'r', encoding='utf-8', errors='ignore') as fsc_r:
                        existing_content = fsc_r.read()
                    if "patched_bind" not in existing_content:
                        with open(sc_path, 'a', encoding='utf-8') as fsc:
                            fsc.write("\n" + patch_code)
                else:
                    with open(sc_path, 'w', encoding='utf-8') as fsc:
                        fsc.write(patch_code)
            except Exception as e_sc:
                log(f"⚠ Warning: Failed to write sitecustomize.py: {e_sc}")

        # 6. Update database record
        conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
        try:

            conn.execute(
                'UPDATE servers SET project_type = ?, assigned_port = ?, startup = ?, public_url = ?, status = "Offline" WHERE folder = ?',
                (p_type, port, cmd, p_url, folder)
            )
            conn.commit()
        finally:
            conn.close()

        log("✅ Deployment pipeline completed successfully!")

        # Send Telegram notification with hosting URL to owner
        try:
            owner_cfg = telegram_monitor.read_config()
            owner_id = owner_cfg.get('owner_id')
            if owner_id:
                srv_name = folder
                conn_name = sqlite3.connect(DB_PATH, timeout=30.0)
                try:
                    nr = conn_name.execute('SELECT name FROM servers WHERE folder=?', (folder,)).fetchone()
                    if nr and nr[0]: srv_name = nr[0]
                finally:
                    conn_name.close()

                msg_text = (
                    f"🚀 *INSTANCE DEPLOYED & READY*\n"
                    f"----------------------------------\n"
                    f"📦 *Name:* `{srv_name}` (`{folder}`)\n"
                    f"🛠️ *Type:* `{p_type.upper()}`\n"
                    f"🔌 *Assigned Port:* `{port or 'N/A'}`\n"
                    f"🌐 *Hosting URL:* {p_url or 'N/A'}\n"
                    f"⚡ *Startup Command:* `{cmd or 'N/A'}`"
                )
                telegram_monitor.send_telegram_msg(owner_id, msg_text)
        except Exception as e_tg:
            print(f"Error sending Telegram deployment notification: {e_tg}")

        return {
            'status': 'success',
            'project_type': p_type,
            'assigned_port': port,
            'startup_command': cmd,
            'public_url': p_url
        }
    except Exception as e:
        log(f"✗ Deployment pipeline failed: {str(e)}")
        try:
            conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
            try:

                conn.execute('UPDATE servers SET status = "Offline" WHERE folder = ?', (folder,))
                conn.commit()
            finally:
                conn.close()
        except:
            pass
        return {'status': 'error', 'msg': str(e)}
