import os
import datetime
import hmac
import uuid as _uuid

from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, current_app
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

import telegram_monitor
from helpers import get_db, api_success, api_error, BASE_DIR

auth_bp = Blueprint('auth_bp', __name__)

@auth_bp.route('/')
def home():
    return render_template('index.html')


@auth_bp.route('/signup', methods=['GET', 'POST'])
@auth_bp.route('/api/v1/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        fname    = request.form.get('fname', '').strip()
        lname    = request.form.get('lname', '').strip()
        username = request.form.get('username', '').strip()
        email    = request.form.get('email', '').strip()
        pwd      = request.form.get('password', '')
        cpwd     = request.form.get('confirm_password', '')
        pfp      = request.files.get('pfp')

        if not all([fname, username, email, pwd]):
            return api_error('All fields are required.', 400)
        if pwd != cpwd:
            return api_error('Passwords do not match!', 400)

        db = get_db()
        if db.execute('SELECT id FROM users WHERE email=? OR username=?', (email, username)).fetchone():
            db.close()
            return api_error('Email or Username already taken!', 400)

        pfp_name = 'default.png'
        if pfp and pfp.filename:
            ext = os.path.splitext(secure_filename(pfp.filename))[1] or '.png'
            pfp_name = f"{_uuid.uuid4().hex}{ext}"
            pfp.save(os.path.join(current_app.config['UPLOAD_FOLDER'], pfp_name))

        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db.execute(
            'INSERT INTO users (fname,lname,username,email,password,pfp,server_limit,role,status,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
            (fname, lname, username, email, generate_password_hash(pwd), pfp_name, 10, 'free', 'active', now_str)
        )
        db.commit()
        db.close()
        return api_success(url='/login')
    if request.path.startswith('/api/v1'):
        return redirect('/signup')
    return render_template('web/signup.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
@auth_bp.route('/api/v1/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        ident = request.form.get('email', '').strip()
        pwd   = request.form.get('password', '')
        
        # Read owner credentials from config.txt
        owner_config = telegram_monitor.read_config()
        owner_username = owner_config.get('owner_username', 'imran').strip().lower()
        owner_password = owner_config.get('owner_password', '').strip()
        
        is_owner_login = False
        if owner_password:
            if (ident.lower() == owner_username or ident.lower() == f"{owner_username}@owner.com") and hmac.compare_digest(pwd, owner_password):
                is_owner_login = True
            
        db = get_db()
        if is_owner_login:
            user = db.execute('SELECT * FROM users WHERE username=?', (owner_username,)).fetchone()
            if not user:
                now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                db.execute(
                    'INSERT INTO users (fname, lname, username, email, password, server_limit, role, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    (owner_username.capitalize(), 'Owner', owner_username, f"{owner_username}@owner.com", generate_password_hash(owner_password), 100, 'admin', 'active', now_str)
                )
                db.commit()
                user = db.execute('SELECT * FROM users WHERE username=?', (owner_username,)).fetchone()
            else:
                db.execute('UPDATE users SET password=? WHERE id=?', (generate_password_hash(owner_password), user['id']))
                db.commit()
                user = db.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone()
        else:
            user = db.execute('SELECT * FROM users WHERE email=? OR username=?', (ident, ident)).fetchone()
        db.close()
        
        # For non-owner login, check password hash
        if not is_owner_login:
            if user and check_password_hash(user['password'], pwd):
                pass
            else:
                return api_error('Invalid credentials!', 401)
                
        if user:
            if user['status'] == 'banned':
                return jsonify({'status':'banned','msg':'Your account has been suspended!'}), 403
            session['user_id'] = user['id']
            if is_owner_login:
                session['admin_logged'] = True
            return api_success(url='/dashboard')
        return api_error('Invalid credentials!', 401)
    if request.path.startswith('/api/v1'):
        return redirect('/login')
    return render_template('web/login.html')


@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth_bp.login'))


@auth_bp.route('/dashboard')
def dashboard():
    if 'user_id' not in session: return redirect(url_for('auth_bp.login'))
    db   = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
    
    # Initialize created_at for existing users if missing
    if user and not user['created_at']:
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db.execute('UPDATE users SET created_at=? WHERE id=?', (now_str, session['user_id']))
        db.commit()
        user = db.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
        
    db.close()
    if not user or user['status'] != 'active':
        session.clear()
        return redirect(url_for('auth_bp.login'))
        
    # Calculate trial/subscription days left (countdown starting from 28 days)
    created_at_str = user['created_at']
    days_left = 28
    if created_at_str:
        try:
            created_at_dt = datetime.datetime.strptime(created_at_str, '%Y-%m-%d %H:%M:%S')
            delta = datetime.datetime.now() - created_at_dt
            days_left = max(0, 28 - delta.days)
        except Exception as e:
            current_app.logger.error(f"Error parsing created_at: {e}")
            
    return render_template('web/dashboard.html', user=user, days_left=days_left)


@auth_bp.route('/api/v1/profile/update', methods=['POST'])
def update_profile():
    if 'user_id' not in session: return api_error('Unauthorized', 401)
    uid   = session['user_id']
    fname = request.form.get('fname', '').strip()
    lname = request.form.get('lname', '').strip()
    pwd   = request.form.get('password', '')
    pfp   = request.files.get('pfp')
    db    = get_db()
    if pfp and pfp.filename:
        ext = os.path.splitext(secure_filename(pfp.filename))[1] or '.png'
        pfp_name = f"{_uuid.uuid4().hex}{ext}"
        pfp.save(os.path.join(current_app.config['UPLOAD_FOLDER'], pfp_name))
        db.execute('UPDATE users SET pfp=? WHERE id=?', (pfp_name, uid))
    if pwd:
        db.execute('UPDATE users SET fname=?,lname=?,password=? WHERE id=?', (fname, lname, generate_password_hash(pwd), uid))
    else:
        db.execute('UPDATE users SET fname=?,lname=? WHERE id=?', (fname, lname, uid))
    db.commit()
    db.close()
    return api_success()


@auth_bp.route('/api/v1/ticket/create', methods=['POST'])
def create_ticket():
    if 'user_id' not in session: return api_error('Unauthorized', 401)
    d = request.json or {}
    subject = d.get('subject', '')
    message = d.get('message', '')
    if not isinstance(subject, str) or not isinstance(message, str):
        return api_error('Subject and message must be strings', 400)
    db = get_db()
    db.execute('INSERT INTO tickets (user_id,subject,message) VALUES (?,?,?)',
               (session['user_id'], subject, message))
    db.commit()
    db.close()
    return api_success()


@auth_bp.route('/api/v1/announcement')
def get_announcement():
    db   = get_db()
    conf = db.execute('SELECT popup_title,popup_msg,popup_img,show_popup FROM admin_settings WHERE id=1').fetchone()
    db.close()
    if not conf:
        return jsonify({'popup_title':'','popup_msg':'','popup_img':'','show_popup':0})
    return jsonify(dict(conf))
