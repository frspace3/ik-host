import requests
from flask import Blueprint, request, render_template
from helpers import get_db, is_hacked

proxy_bp = Blueprint('proxy_bp', __name__)

@proxy_bp.route('/instance/<folder>', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
@proxy_bp.route('/instance/<folder>/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
@proxy_bp.route('/apps/<folder>', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
@proxy_bp.route('/apps/<folder>/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
def proxy_instance_traffic(folder, path):
    db = get_db()
    srv = db.execute('SELECT assigned_port, status, server_status, folder FROM servers WHERE folder=? OR name=?', (folder, folder)).fetchone()
    db.close()
    
    real_folder = srv['folder'] if srv else folder
    if is_hacked(real_folder):
        return render_template('web/hack_blocked.html'), 403
        
    if not srv:
        return "Instance not found", 404
    if srv['server_status'] == 'suspended':
        return "This instance is suspended by Admin.", 403
    if not srv['assigned_port']:
        return "This instance is not exposing any web ports.", 400
    if srv['status'] != 'Running':
        return "Instance is offline", 503
        
    target_url = f"http://127.0.0.1:{srv['assigned_port']}/{path}"
    if request.query_string:
        target_url += f"?{request.query_string.decode('utf-8')}"
        
    try:
        headers = {key: value for key, value in request.headers if key.lower() not in ['host', 'content-length']}
        resp = requests.request(
            method=request.method,
            url=target_url,
            headers=headers,
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
            timeout=20
        )
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        resp_headers = [(name, value) for name, value in resp.raw.headers.items() if name.lower() not in excluded_headers]
        return (resp.content, resp.status_code, resp_headers)
    except Exception as e:
        return f"Reverse Proxy connection error: {str(e)}", 502
