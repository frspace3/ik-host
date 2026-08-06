import os
from flask import Flask, render_template, request, redirect, session
from flask_compress import Compress
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import helpers
import health_monitor
import telegram_monitor

# Re-export helper functions and global state for backward compatibility
from helpers import (
    get_db, init_db, start_instance_by_folder, is_safe_path,
    running_procs, start_times, procs_lock, BASE_DIR
)

from routes.auth import auth_bp
from routes.servers import servers_bp
from routes.files import files_bp
from routes.admin import admin_bp
from routes.proxy import proxy_bp
from routes.legacy import legacy_bp

limiter = Limiter(key_func=get_remote_address, default_limits=["60 per minute"])

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', helpers.get_secret_key())
    app.config['BASE_STORAGE'] = os.path.join(helpers.BASE_DIR, 'storage/instances')
    app.config['UPLOAD_FOLDER'] = os.path.join(helpers.BASE_DIR, 'static/uploads')
    app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 604800  # 7 days cache for static files
    app.config['COMPRESS_MIN_SIZE'] = 500  # Don't waste CPU compressing tiny responses

    os.makedirs(app.config['BASE_STORAGE'], exist_ok=True)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    helpers.init_db()

    # Set WAL mode once at startup
    try:
        import sqlite3
        _db_file = os.path.join(helpers.BASE_DIR, 'storage/ikhost.db')
        _init_conn = sqlite3.connect(_db_file, timeout=30.0)
        _init_conn.execute("PRAGMA journal_mode=WAL")
        _init_conn.close()

        from storage.init_db import init_db
        init_db()
    except Exception as ex_db:
        print(f"[App] DB init warning: {ex_db}")

    # Enable gzip compression & rate limiting
    Compress(app)
    limiter.init_app(app)

    # Register start callbacks and monitors
    health_monitor.register_restart_callback(helpers.start_instance_by_folder)
    if os.environ.get('NEHOST_TESTING') != 'true':
        health_monitor.start_health_monitor()

    telegram_monitor.register_restart_callback(helpers.start_instance_by_folder)
    if os.environ.get('NEHOST_TESTING') != 'true':
        telegram_monitor.start_monitoring()

    # Register Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(servers_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(proxy_bp)
    app.register_blueprint(legacy_bp)

    @app.teardown_appcontext
    def close_db_connections(exception):
        from flask import g
        connections = getattr(g, '_db_connections', [])
        for conn in connections:
            try:
                conn.close()
            except Exception:
                pass

    # ─── Master Gateway Middleware & Route ────────────────────────
    @app.before_request
    def check_master_gateway():
        if os.environ.get('NEHOST_TESTING') == 'true':
            return
        if (
            request.path == '/' or
            request.path.startswith('/static') or
            request.path == '/unlock-gateway' or
            request.path.startswith('/instance/') or
            request.path.startswith('/apps/') or
            request.path.startswith('/socket.io')
        ):
            return
        if not session.get('master_unlocked'):
            return render_template('web/master_gateway.html')

    @app.route('/unlock-gateway', methods=['GET', 'POST'])
    @limiter.limit("5 per minute")
    def unlock_gateway():
        if request.method == 'POST':
            pwd = request.form.get('password')
            if pwd == '554961':
                session['master_unlocked'] = True
                next_url = request.args.get('next', '/')
                if not next_url.startswith('/') or next_url.startswith('//'):
                    next_url = '/'
                return redirect(next_url)
            return render_template('web/master_gateway.html', error="Invalid Master Key")
        if session.get('master_unlocked'):
            return redirect('/')
        return render_template('web/master_gateway.html')

    return app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('NEHOST_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
