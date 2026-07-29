import os, shutil, psutil, time, datetime, hmac
import port_manager, telegram_monitor
from helpers import get_db, kill_process_by_pid, api_success, api_error, running_procs, start_times, procs_lock, BASE_DIR
from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, current_app
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

admin_bp = Blueprint('admin_bp', __name__)

@admin_bp.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        user = request.form.get('username', '')
        pwd = request.form.get('password', '')
        
        owner_config = telegram_monitor.read_config()
        admin_user = owner_config.get('admin_username', 'imran112233').strip()
        admin_pass = owner_config.get('admin_password', '').strip()
        
        if not admin_user or not admin_pass:
            return render_template('web/admin_login.html')
            
        if user == admin_user and hmac.compare_digest(pwd, admin_pass):
            session['admin_logged'] = True
            return redirect(url_for('admin_bp.admin_panel'))
    return render_template('web/admin_login.html')

@admin_bp.route('/admin/panel')
def admin_panel():
    if not session.get('admin_logged'): return redirect(url_for('admin_bp.admin_login'))
    return render_template('web/admin_panel.html')

@admin_bp.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_bp.admin_login'))

@admin_bp.route('/api/v1/admin/stats')
def admin_stats():
    if not session.get('admin_logged'): return jsonify({}), 403
    db = get_db()
    users = db.execute('SELECT * FROM users').fetchall()
    srv_counts = db.execute('SELECT user_id, COUNT(*) as cnt FROM servers GROUP BY user_id').fetchall()
    srv_count_map = {r['user_id']: r['cnt'] for r in srv_counts}
    all_servers = db.execute('SELECT user_id, pid, folder FROM servers').fetchall()
    user_servers = {}
    for s in all_servers:
        user_servers.setdefault(s['user_id'], []).append(s)
    user_list = []
    for u in users:
        srvs = user_servers.get(u['id'], [])
        act = 0
        for s in srvs:
            on = False
            if s['pid'] and psutil.pid_exists(s['pid']):
                try:
                    proc = psutil.Process(s['pid'])
                    if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE: on = True
                except: pass
            else:
                with procs_lock:
                    if s['folder'] in running_procs and running_procs[s['folder']].poll() is None: on = True
            if on: act += 1
        ram_lim = u['ram_limit'] if 'ram_limit' in u.keys() else 100
        cpu_lim = u['cpu_limit'] if 'cpu_limit' in u.keys() else 100
        user_list.append({'id': u['id'], 'fname': u['fname'], 'email': u['email'],
                          'srv_count': srv_count_map.get(u['id'], 0), 'active_srvs': act, 'status': u['status'],
                          'role': u['role'], 'server_limit': u['server_limit'],
                          'ram_limit': ram_lim, 'cpu_limit': cpu_lim, 'created_at': u['created_at']})
    db.close()
    return jsonify({'users': user_list, 'sys_cpu': f"{psutil.cpu_percent()}%", 'sys_ram': f"{psutil.virtual_memory().percent}%"})

@admin_bp.route('/api/v1/admin/users/update', methods=['POST'])
def update_user():
    if not session.get('admin_logged'): return jsonify({'status': 'error'}), 403
    d = request.json or {}
    if 'user_id' not in d:
        return jsonify({'status': 'error', 'msg': 'Missing user_id'}), 400
    db = get_db()
    current = db.execute('SELECT * FROM users WHERE id=?', (d['user_id'],)).fetchone()
    if not current:
        db.close()
        return jsonify({'status': 'error', 'msg': 'User not found'}), 404
    role = d.get('role', current['role'])
    status = d.get('status', current['status'])
    try:
        limit = int(d.get('limit', current['server_limit']))
        ram_limit = int(d.get('ram_limit', current['ram_limit']))
        cpu_limit = int(d.get('cpu_limit', current['cpu_limit']))
    except ValueError:
        db.close()
        return jsonify({'status': 'error', 'msg': 'Limits must be integers'}), 400
    db.execute('UPDATE users SET role=?,status=?,server_limit=?,ram_limit=?,cpu_limit=? WHERE id=?',
               (role, status, limit, ram_limit, cpu_limit, d['user_id']))
    db.commit()
    db.close()
    return jsonify({'status': 'success'})

@admin_bp.route('/api/v1/admin/users/bulk-limit', methods=['POST'])
def bulk_limit_users():
    if not session.get('admin_logged'): return jsonify({'status': 'error'}), 403
    d = request.json or {}
    try:
        ram_lim = int(d.get('ram_limit', 100))
        cpu_lim = int(d.get('cpu_limit', 100))
    except ValueError:
        return jsonify({'status': 'error', 'msg': 'Limits must be integers'}), 400
    db = get_db()
    db.execute('UPDATE users SET ram_limit=?, cpu_limit=? WHERE role != "admin"', (ram_lim, cpu_lim))
    db.commit()
    db.close()
    return jsonify({'status': 'success'})

@admin_bp.route('/api/v1/admin/set-popup', methods=['POST'])
def set_popup():
    if not session.get('admin_logged'): return jsonify({'status': 'error'}), 403
    title = request.form.get('title', '')
    msg = request.form.get('msg', '')
    show = request.form.get('show', 'false')
    img = request.files.get('image')
    db = get_db()
    old = db.execute('SELECT popup_img FROM admin_settings WHERE id=1').fetchone()
    iname = old['popup_img'] if old else ''
    if img and img.filename:
        iname = secure_filename(img.filename)
        img.save(os.path.join(current_app.config['UPLOAD_FOLDER'], iname))
    db.execute('UPDATE admin_settings SET popup_title=?,popup_msg=?,popup_img=?,show_popup=? WHERE id=1',
               (title, msg, iname, 1 if show == 'true' else 0))
    db.commit()
    db.close()
    return jsonify({'status': 'success'})

@admin_bp.route('/api/v1/admin/send-warning', methods=['POST'])
def send_warning():
    if not session.get('admin_logged'): return jsonify({'status': 'error'}), 403
    d = request.json or {}
    if 'user_id' not in d:
        return jsonify({'status': 'error', 'msg': 'Missing user_id'}), 400
    msg = d.get('message', '')
    if not isinstance(msg, str):
        msg = str(msg)
    db = get_db()
    db.execute('UPDATE users SET notifications=? WHERE id=?', (msg, d['user_id']))
    db.commit()
    db.close()

    try:
        owner_cfg = telegram_monitor.read_config()
        owner_id = owner_cfg.get('owner_id')
        if owner_id:
            telegram_monitor.send_telegram_msg(
                owner_id,
                f"⚠️ *ADMIN WARNING ISSUED*\n----------------------------------\n"
                f"👤 *Target User ID:* `{d['user_id']}`\n"
                f"💬 *Warning Message:* {msg}"
            )
    except Exception as e_warn_tg:
        current_app.logger.error(f"Error sending warning Telegram alert: {e_warn_tg}")

    return jsonify({'status': 'success'})

@admin_bp.route('/admin/login-as/<int:uid>')
def login_as(uid):
    if not session.get('admin_logged'): return redirect(url_for('admin_bp.admin_login'))
    session['user_id'] = uid
    return redirect(url_for('auth_bp.dashboard'))

@admin_bp.route('/admin/manage-user/<int:uid>')
def admin_manage_user_servers(uid):
    if not session.get('admin_logged'): return redirect(url_for('admin_bp.admin_login'))
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    rows = db.execute('SELECT * FROM servers WHERE user_id=?', (uid,)).fetchall()
    db.close()
    servers = []
    for r in rows:
        f = r['folder']
        with procs_lock:
            online = (f in running_procs and running_procs[f].poll() is None) or (r['pid'] and psutil.pid_exists(r['pid']))
        servers.append({'id': r['id'], 'name': r['name'], 'folder': f, 'online': online, 'status': r['server_status']})
    return render_template('web/admin_manage_user.html', user=user, servers=servers)

@admin_bp.route('/api/v1/admin/servers/<int:sid>/suspend', methods=['POST'])
def admin_suspend_server(sid):
    if not session.get('admin_logged'): return jsonify({'status': 'error'}), 403
    d = request.json or {}
    status = d.get('status', 'active')
    if not isinstance(status, str):
        status = str(status)
    db = get_db()
    db.execute('UPDATE servers SET server_status=? WHERE id=?', (status, sid))
    db.commit()
    db.close()
    return jsonify({'status': 'success'})

@admin_bp.route('/api/v1/admin/servers/<int:sid>/delete', methods=['POST'])
def admin_delete_server(sid):
    if not session.get('admin_logged'): return jsonify({'status': 'error'}), 403
    db = get_db()
    srv = db.execute('SELECT folder, pid FROM servers WHERE id=?', (sid,)).fetchone()
    if not srv:
        db.close()
        return jsonify({'status': 'error', 'msg': 'Not found'}), 404
    folder = srv['folder']
    with procs_lock:
        t_pid = running_procs[folder].pid if folder in running_procs else srv['pid']
        running_procs.pop(folder, None)
        start_times.pop(folder, None)
    if t_pid and psutil.pid_exists(t_pid):
        kill_process_by_pid(t_pid)
    db.execute('DELETE FROM servers WHERE id=?', (sid,))
    db.commit()
    db.close()
    
    port_manager.release_port(folder)
    
    path = os.path.join(current_app.config['BASE_STORAGE'], folder)
    if os.path.exists(path):
        shutil.rmtree(path)
    return jsonify({'status': 'deleted'})

@admin_bp.route('/api/v1/admin/users/create', methods=['POST'])
def admin_create_user():
    if not session.get('admin_logged'): return jsonify({'status': 'error'}), 403
    d = request.json or {}
    raw = d.get('name', 'User')
    if not isinstance(raw, str):
        raw = str(raw) if raw is not None else 'User'
    raw = raw.strip()
    parts = (raw + ' ').split(' ', 1)
    fname = parts[0] or 'User'
    lname = parts[1].strip() or ''
    email = d.get('email')
    if not isinstance(email, str):
        email = str(email) if email is not None else ''
    email = email.strip()
    uname = (email.split('@')[0] + str(int(time.time()))[-4:]).lower()
    pwd = d.get('pass', 'changeme123')
    if not isinstance(pwd, str):
        pwd = str(pwd)
    hashed = generate_password_hash(pwd)
    try:
        limit = int(d.get('limit', 1))
    except ValueError:
        limit = 1
    db = get_db()
    try:
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db.execute('INSERT INTO users (fname,lname,username,email,password,server_limit,created_at) VALUES (?,?,?,?,?,?,?)',
                   (fname, lname, uname, email, hashed, limit, now_str))
        db.commit()
        db.close()
        return jsonify({'status': 'success'})
    except Exception as e:
        db.close()
        return jsonify({'status': 'error', 'msg': str(e)})

@admin_bp.route('/api/v1/admin/users/<int:uid>/delete', methods=['POST'])
def delete_user(uid):
    if not session.get('admin_logged'): return jsonify({'status': 'error'}), 403
    db = get_db()
    srvs = db.execute('SELECT folder FROM servers WHERE user_id=?', (uid,)).fetchall()
    for s in srvs:
        p = os.path.join(current_app.config['BASE_STORAGE'], s['folder'])
        if os.path.exists(p): shutil.rmtree(p)
    db.execute('DELETE FROM servers WHERE user_id=?', (uid,))
    db.execute('DELETE FROM users WHERE id=?', (uid,))
    db.commit()
    db.close()
    
    for s in srvs:
        port_manager.release_port(s['folder'])
        
    return jsonify({'status': 'deleted'})

@admin_bp.route('/admin/files/<folder>')
def admin_browse_files(folder):
    if not session.get('admin_logged'): return redirect(url_for('admin_bp.admin_login'))
    return render_template('web/dashboard.html',
                           user={'fname': 'Admin', 'role': 'admin'},
                           is_admin_view=True, admin_folder=folder)
