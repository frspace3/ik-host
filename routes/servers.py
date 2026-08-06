import os, datetime, time, subprocess, sys, psutil, zipfile, shutil, re
import health_monitor
import port_manager, project_detector, deployment_manager, telegram_monitor
from flask import Blueprint, request, session, jsonify, send_file, current_app
from werkzeug.utils import secure_filename
import uuid

from helpers import (
    get_db, is_safe_path, check_server_access, kill_process_by_pid,
    start_instance_by_folder, flatten_extracted_folder, api_success,
    api_error, running_procs, start_times, procs_lock, PROTECTED_FILES,
    BASE_DIR, get_precise_uptime, get_process_resources, is_hacked
)

servers_bp = Blueprint('servers_bp', __name__, url_prefix='/api/v1')

@servers_bp.route('/servers', methods=['GET'])
def list_servers():
    if 'user_id' not in session: 
        return api_success('Not logged in', servers=[])
    db = get_db()
    rows = db.execute('SELECT * FROM servers WHERE user_id=?', (session['user_id'],)).fetchall()
    db.close()
    srvs = []
    for r in rows:
        f, saved_pid = r['folder'], r['pid']
        online = False
        if saved_pid:
            try:
                p = psutil.Process(saved_pid)
                if p.is_running() and p.status() != psutil.STATUS_ZOMBIE: 
                    online = True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess): 
                pass
        if not online:
            with procs_lock:
                if f in running_procs and running_procs[f].poll() is None: 
                    online = True
        with procs_lock:
            start_time_val = start_times.get(f)
            has_start_time = f in start_times
        uptime = get_precise_uptime(start_time_val) if (online and has_start_time) else ("Online" if online else "Offline")
        cpu, ram = "0%", "0MB"
        if online:
            # Use cached metrics from health monitor (updated every 60s) instead of expensive live psutil calls
            with health_monitor.metrics_cache_lock:
                cached = health_monitor.metrics_cache.get(f)
            if cached:
                cpu, ram = cached['cpu'], cached['ram']
            else:
                with procs_lock:
                    pid_ = running_procs[f].pid if f in running_procs else saved_pid
                cpu, ram, _ = get_process_resources(pid_)
        srvs.append({
            'name': r['name'],
            'folder': f,
            'online': online,
            'startup': r['startup'],
            'uptime': uptime,
            'cpu': cpu,
            'ram': ram,
            'status': r['server_status'],
            'runner_status': r['status'] or 'Offline',
            'project_type': r['project_type'] or 'script',
            'assigned_port': r['assigned_port'],
            'public_url': r['public_url'] or '',
            'health_status': r['health_status'] or 'Unknown',
            'restart_count': r['restart_count'] or 0,
            'auto_restart_enabled': r['auto_restart_enabled'] or 0,
            'auto_restart_time': r['auto_restart_time'] or '',
            'is_hacked': is_hacked(f)
        })
    total_ram_mb = 0.0
    for srv in srvs:
        if srv.get('online'):
            try:
                ram_str = srv.get('ram', '0MB')
                val = float(ram_str.replace('MB', '').strip())
                total_ram_mb += val
            except Exception:
                pass

    try:
        vmem = psutil.virtual_memory()
        sys_ram_mb = round(vmem.used / (1024 * 1024), 1)
        sys_ram_percent = round(vmem.percent, 1)
    except Exception:
        sys_ram_mb = round(total_ram_mb, 1)
        sys_ram_percent = 0.0

    return api_success(
        'Servers retrieved',
        servers=srvs,
        total_ram_mb=round(total_ram_mb, 1),
        sys_ram_mb=sys_ram_mb,
        sys_ram_percent=sys_ram_percent,
        total_ram_limit_mb=1024
    )

@servers_bp.route('/servers', methods=['POST'])
def add_srv():
    if 'user_id' not in session: 
        return api_error('Not logged in', 401)
    d = request.json or {}
    name = d.get('name')
    if not isinstance(name, str):
        name = str(name) if name is not None else ''
    name = name.strip()
    if not name:
        return api_error('Server name cannot be empty', 400)
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
    count = db.execute('SELECT COUNT(*) as c FROM servers WHERE user_id=?', (session['user_id'],)).fetchone()['c']
    if user['role'] != 'admin' and count >= user['server_limit']:
        db.close()
        return api_error(f"Limit reached! Max: {user['server_limit']}", 403)
    folder_prefix = secure_filename(name).lower()
    if not folder_prefix:
        folder_prefix = "instance"
    folder = f"{folder_prefix}_{uuid.uuid4().hex[:6]}"
    db.execute('INSERT INTO servers (user_id,name,folder,status,startup,project_type,health_status,restart_count) VALUES (?,?,?,?,?,?,?,?)',
               (session['user_id'], name, folder, 'Offline', 'main.py', 'script', 'Unknown', 0))
    db.commit()
    db.close()
    os.makedirs(os.path.join(current_app.config['BASE_STORAGE'], folder), exist_ok=True)
    return api_success('Server created', folder=folder)

@servers_bp.route('/servers/<folder>/action/<act>', methods=['POST'])
def server_action(folder, act):
    allowed, err_resp = check_server_access(folder)
    if not allowed: 
        return err_resp
    db = get_db()
    srv_data = db.execute('SELECT server_status FROM servers WHERE folder=?', (folder,)).fetchone()
    if srv_data and srv_data['server_status'] == 'suspended':
        db.close()
        return api_error('This server is suspended by Admin.', 403)
    path = os.path.join(current_app.config['BASE_STORAGE'], folder)
    logpath = os.path.join(path, 'console.log')
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if act == 'install':
        req = os.path.join(path, 'requirements.txt')
        if os.path.exists(req):
            flog = open(logpath, 'a', encoding='utf-8')
            flog.write(f"\n[{now}] 📦 Installing packages...\n")
            flog.flush()
            subprocess.Popen([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'], cwd=path, stdout=flog, stderr=flog)
            db.close()
            return api_success('installing')
        db.close()
        return api_error('requirements.txt not found', 404)

    if act in ['start', 'restart']:
        db.close()
        success = start_instance_by_folder(folder, act)
        if success:
            return api_success('started')
        else:
            return api_error('Failed to start process', 500)

    if act == 'stop':
        row = db.execute('SELECT pid FROM servers WHERE folder=?', (folder,)).fetchone()
        with procs_lock:
            t_pid = running_procs[folder].pid if folder in running_procs else (row['pid'] if row else None)
            running_procs.pop(folder, None)
            start_times.pop(folder, None)
        if t_pid and psutil.pid_exists(t_pid):
            kill_process_by_pid(t_pid)
        db.execute('UPDATE servers SET pid=NULL, status="Offline" WHERE folder=?', (folder,))
        db.commit()
        db.close()
        with open(logpath, 'a', encoding='utf-8') as f: 
            f.write(f"\n[{now}] 🛑 Instance STOPPED\n")
        return api_success('stopped')
    
    db.close()
    return api_success('ok')

@servers_bp.route('/servers/<folder>/log', methods=['GET'])
def server_log(folder):
    if is_hacked(folder):
        if not session.get('admin_logged') and 'user_id' not in session:
            return api_error('Access denied', 401)
        if not session.get('admin_logged'):
            db = get_db()
            srv = db.execute('SELECT user_id FROM servers WHERE folder=?', (folder,)).fetchone()
            db.close()
            if not srv or srv['user_id'] != session['user_id']:
                return api_error('Access denied', 403)
        return api_success('Hacked', log='you cant hack anything from here . so you should go and fuck your self 🤣\n\n[WARNING] HACK DETECTED: This instance has been terminated and locked.')

    allowed, err_resp = check_server_access(folder)
    if not allowed: 
        return err_resp
    path = os.path.join(current_app.config['BASE_STORAGE'], folder, 'console.log')
    if os.path.exists(path):
        try:
            file_size = os.path.getsize(path)
            with open(path, 'rb') as f:
                if file_size > 8000:
                    f.seek(-8000, 2)
                raw = f.read()
            return api_success('Log fetched', log=raw.decode('utf-8', errors='ignore'))
        except Exception:
            return api_error('Error reading log file', 500)
    return api_success('Log fetched', log='No logs yet...')

@servers_bp.route('/servers/<folder>/set-startup', methods=['POST'])
def set_startup(folder):
    allowed, err_resp = check_server_access(folder)
    if not allowed: 
        return err_resp
    d = request.json or {}
    fname = d.get('file')
    if not isinstance(fname, str):
        fname = str(fname) if fname is not None else ''
    fname = fname.strip()
    if not fname: 
        return api_error('Filename cannot be empty', 400)
    
    if not session.get('admin_logged'):
        forbidden = [';', '&', '|', '`', '(', ')', '<', '>', '\n', '\r']
        if any(char in fname for char in forbidden):
            return api_error('Invalid characters in startup command', 400)
            
        if re.search(r'\s-S\b', fname) or re.search(r'\s--no-site\b', fname):
            return api_error('Bypassing sitecustomize is not allowed.', 400)
            
        for match in re.finditer(r'\$', fname):
            start = match.start()
            if fname[start:start+5] != '$PORT':
                return api_error('Only $PORT environment variable is allowed', 400)
            if len(fname) > start + 5:
                next_char = fname[start + 5]
                if next_char.isalnum() or next_char == '_':
                    return api_error('Only $PORT environment variable is allowed', 400)
    db = get_db()
    db.execute('UPDATE servers SET startup=? WHERE folder=?', (fname, folder))
    db.commit()
    db.close()
    return api_success('Startup file updated successfully')

@servers_bp.route('/servers/<folder>/set-auto-restart', methods=['POST'])
def set_auto_restart(folder):
    allowed, err_resp = check_server_access(folder)
    if not allowed: 
        return err_resp
    
    d = request.json or {}
    enabled = 1 if d.get('enabled') else 0
    time_str = d.get('time')
    if not isinstance(time_str, str):
        time_str = str(time_str) if time_str is not None else ''
    time_str = time_str.strip()
    
    if enabled:
        if not time_str or len(time_str) != 5 or ':' not in time_str:
            return api_error('Invalid time format. Must be HH:MM.', 400)
        try:
            parts = time_str.split(':')
            h_val = int(parts[0])
            m_val = int(parts[1])
            if h_val < 0 or h_val > 23 or m_val < 0 or m_val > 59:
                raise ValueError()
        except:
            return api_error('Invalid hours or minutes.', 400)
    
    db = get_db()
    db.execute('UPDATE servers SET auto_restart_enabled=?, auto_restart_time=? WHERE folder=?', (enabled, time_str, folder))
    db.commit()
    db.close()
    return api_success('Auto-restart updated successfully')

@servers_bp.route('/servers/<folder>/command', methods=['POST'])
def server_command(folder):
    allowed, err_resp = check_server_access(folder)
    if not allowed: 
        return err_resp
    d = request.json or {}
    cmd = d.get('command')
    if not isinstance(cmd, str):
        cmd = str(cmd) if cmd is not None else ''
    cmd = cmd.strip()
    if not cmd: 
        return api_error('No command provided', 400)
    srv_path = os.path.join(current_app.config['BASE_STORAGE'], folder)
    logpath = os.path.join(srv_path, 'console.log')
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    with procs_lock:
        proc = running_procs.get(folder)
    if proc and proc.poll() is None and proc.stdin:
        try:
            proc.stdin.write((cmd + '\n').encode('utf-8'))
            proc.stdin.flush()
            with open(logpath, 'a', encoding='utf-8') as f:
                f.write(f"\n[{now}] $ {cmd}\n")
            return api_success('Command sent', output='')
        except Exception:
            pass

    if not session.get('admin_logged'):
        return api_error('Standalone shell execution is disabled for security.', 403)

    try:
        result = subprocess.run(
            cmd, shell=True, cwd=srv_path,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, timeout=30, errors='replace'
        )
        output = result.stdout.strip() if result.stdout else ''
        with open(logpath, 'a', encoding='utf-8') as f:
            f.write(f"\n[{now}] $ {cmd}\n")
            if output:
                f.write(output + '\n')
        return api_success('Command executed', output=output)
    except subprocess.TimeoutExpired:
        return api_error('Command timed out (30s)', 504)
    except Exception as e:
        return api_error(str(e), 500)

@servers_bp.route('/servers/<folder>/delete', methods=['POST'])
def delete_server(folder):
    allowed, err_resp = check_server_access(folder)
    if not allowed: 
        return err_resp
    db = get_db()
    srv = db.execute('SELECT server_status,pid FROM servers WHERE folder=?', (folder,)).fetchone()
    if not srv:    
        db.close()
        return api_error('Server not found', 404)
    if srv['server_status'] == 'suspended':  
        db.close()
        return api_error('Suspended servers cannot be deleted!', 403)
    with procs_lock:
        t_pid = running_procs[folder].pid if folder in running_procs else srv['pid']
        running_procs.pop(folder, None)
        start_times.pop(folder, None)
    if t_pid and psutil.pid_exists(t_pid):
        kill_process_by_pid(t_pid)
    db.execute('DELETE FROM servers WHERE folder=?', (folder,))
    db.commit()
    db.close()
    
    port_manager.release_port(folder)
    
    path = os.path.join(current_app.config['BASE_STORAGE'], folder)
    if os.path.exists(path): 
        shutil.rmtree(path)
    return api_success('Server deleted')

@servers_bp.route('/servers/<folder>/download-zip', methods=['GET'])
def download_server_zip(folder):
    allowed, err_resp = check_server_access(folder)
    if not allowed: 
        # Here we don't use api_error because it's a direct file download request.
        # But if the user rule explicitly wants api_error, we can return it.
        # However, a browser GET download expects text/html or the file. We'll return the error string if requested or standard error.
        return err_resp
    
    db = get_db()
    srv = db.execute('SELECT name FROM servers WHERE folder=?', (folder,)).fetchone()
    db.close()
    
    srv_name = srv['name'] if srv else folder
    safe_name = re.sub(r'[\\/*?:"<>|]', '_', srv_name).strip()
    if not safe_name: 
        safe_name = folder
    
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    bdt_now = utc_now + datetime.timedelta(hours=6)
    date_str = bdt_now.strftime('%d-%m-%Y')
    download_filename = f"{safe_name} ik-{date_str}.zip"
    
    instance_base = os.path.abspath(os.path.join(current_app.config['BASE_STORAGE'], folder))
    if not os.path.exists(instance_base):
        return api_error('Instance directory not found', 404)
        
    import tempfile
    temp_dir = tempfile.gettempdir()
    zip_filename = f"{folder}_{int(time.time())}.zip"
    zip_path = os.path.join(temp_dir, zip_filename)
    
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(instance_base):
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, instance_base)
                    if is_safe_path(instance_base, file_path):
                        zf.write(file_path, rel_path)
                        
        response = send_file(
            zip_path,
            mimetype='application/zip',
            as_attachment=True,
            download_name=download_filename
        )
        @response.call_on_close
        def remove_file():
            try:
                os.remove(zip_path)
            except Exception as e:
                current_app.logger.error(f"Error removing temporary zip file: {e}")
        return response
    except Exception as e:
        if os.path.exists(zip_path):
            try:
                os.remove(zip_path)
            except:
                pass
        return api_error(f"Zipping failed: {str(e)}", 500)

@servers_bp.route('/servers/<folder>/rename', methods=['POST'])
def rename_server(folder):
    allowed, err_resp = check_server_access(folder)
    if not allowed: 
        return err_resp
    d = request.json or {}
    new_name = d.get('name')
    if not isinstance(new_name, str):
        new_name = str(new_name) if new_name is not None else ''
    new_name = new_name.strip()
    if not new_name: 
        return api_error('Name cannot be empty', 400)
    db = get_db()
    db.execute('UPDATE servers SET name=? WHERE folder=?', (new_name, folder))
    db.commit()
    db.close()
    return api_success('Server renamed successfully')

@servers_bp.route('/servers/<folder>/deploy-pipeline', methods=['POST'])
def deploy_pipeline(folder):
    allowed, err_resp = check_server_access(folder)
    if not allowed: 
        return err_resp
    db = get_db()
    db.execute('UPDATE servers SET status="Deploying" WHERE folder=?', (folder,))
    db.commit()
    db.close()
    host = request.headers.get('Host', 'localhost:5000')
    res = deployment_manager.run_deployment_pipeline(folder, host)
    if res and res.get('status') == 'success':
        return api_success('Pipeline deployed', **res)
    else:
        return api_error('Pipeline deployment failed', 500)

@servers_bp.route('/report-hack/<folder>', methods=['POST'])
def report_hack(folder):
    db = get_db()
    row = db.execute(
        'SELECT users.username FROM servers JOIN users ON servers.user_id = users.id WHERE servers.folder = ?',
        (folder,)
    ).fetchone()
    db.close()
    if row:
        uploader_username = row['username'].strip().lower()
        owner_config = telegram_monitor.read_config()
        owner_username = owner_config.get('owner_username', 'imran').strip().lower()
        if uploader_username == owner_username:
            return api_success('ignored_owner')
    return api_success('reported')

@servers_bp.route('/servers/<folder>/detect-startup', methods=['GET'])
def detect_startup(folder):
    allowed, err_resp = check_server_access(folder)
    if not allowed: 
        return err_resp
    base = os.path.join(current_app.config['BASE_STORAGE'], folder)
    priority = ['main.py', 'app.py', 'bot.py', 'run.py', 'start.py', 'index.py']

    for name in priority:
        if os.path.isfile(os.path.join(base, name)):
            return api_success('Found startup script', startup=name)

    try:
        for entry in os.listdir(base):
            sub = os.path.join(base, entry)
            if os.path.isdir(sub):
                for name in priority:
                    if os.path.isfile(os.path.join(sub, name)):
                        return api_success('Found startup script', startup=f"{entry}/{name}")
    except Exception:
        pass

    try:
        for f in os.listdir(base):
            if f.endswith('.py') and f != 'console.log':
                return api_success('Found startup script', startup=f)
    except Exception:
        pass

    return api_success('Startup script not found', startup='main.py')

@servers_bp.route('/servers/<folder>/endpoints', methods=['GET'])
def server_endpoints(folder):
    allowed, err_resp = check_server_access(folder)
    if not allowed: 
        return err_resp
    
    instance_path = os.path.join(current_app.config['BASE_STORAGE'], folder)
    detected = project_detector.detect_endpoints(instance_path)
    
    def get_mock_val(p):
        pl = p.lower()
        if 'uid' in pl: return 'YOUR_UID'
        if 'server' in pl: return 'bd'
        if 'email' in pl: return 'user@example.com'
        if 'pass' in pl: return 'your_password'
        if 'limit' in pl: return '10'
        if 'name' in pl: return 'test'
        return 'value'
        
    host = request.headers.get('Host', 'localhost:5000')
    scheme = 'https' if request.is_secure else 'http'
    
    urls = []
    for ep in detected:
        path = ep['path']
        params = ep['params']
        query_str = ""
        if params:
            query_str = "?" + "&".join([f"{p}={get_mock_val(p)}" for p in params])
        full_url = f"{scheme}://{host}/instance/{folder}{path}{query_str}"
        urls.append({
            'path': path,
            'url': full_url
        })
        
    return api_success('Endpoints detected', endpoints=urls)

@servers_bp.route('/servers/<folder>/sync-install', methods=['POST'])
def sync_install(folder):
    allowed, err_resp = check_server_access(folder)
    if not allowed: 
        return err_resp
    path = os.path.join(current_app.config['BASE_STORAGE'], folder)
    req = os.path.join(path, 'requirements.txt')
    logpath = os.path.join(path, 'console.log')
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if not os.path.isfile(req):
        return api_success('No requirements.txt', output='')

    try:
        with open(logpath, 'a', encoding='utf-8') as flog:
            flog.write(f"\n[{now}] 📦 Auto-installing packages...\n")
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'],
            cwd=path, capture_output=True, text=True, timeout=120
        )
        output = (result.stdout + result.stderr).strip()
        with open(logpath, 'a', encoding='utf-8') as flog:
            flog.write(output + '\n')
        return api_success('Packages installed', output=output)
    except subprocess.TimeoutExpired:
        return api_error('pip install timed out (120s)', 504)
    except Exception as e:
        return api_error(str(e), 500)
