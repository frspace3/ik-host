import os, shutil, zipfile, datetime
from flask import Blueprint, request, session, jsonify, send_file, current_app
from werkzeug.utils import secure_filename
from helpers import get_db, is_safe_path, check_server_access, flatten_extracted_folder, api_success, api_error, PROTECTED_FILES

files_bp = Blueprint('files_bp', __name__, url_prefix='/api/v1/files')

@files_bp.route('/<folder>/list')
def flist(folder):
    allowed, err = check_server_access(folder)
    if not allowed: return err
    sub   = request.args.get('path','')
    instance_base = os.path.abspath(os.path.join(current_app.config['BASE_STORAGE'], folder))
    full = os.path.abspath(os.path.join(instance_base, sub))
    if not is_safe_path(instance_base, full): return jsonify([])
    if not os.path.isdir(full): return jsonify([])
    items = []
    for f in sorted(os.listdir(full)):
        if f in ['console.log'] + PROTECTED_FILES: continue
        p = os.path.join(full, f)
        items.append({'name':f,'is_dir':os.path.isdir(p),'is_zip':f.lower().endswith('.zip')})
    return jsonify(items)

@files_bp.route('/<folder>/read')
def fread(folder):
    allowed, err = check_server_access(folder)
    if not allowed: return err
    name = request.args.get('name','')
    sub  = request.args.get('path','')
    instance_base = os.path.abspath(os.path.join(current_app.config['BASE_STORAGE'], folder))
    if name in PROTECTED_FILES:
        return jsonify({'content':'Access denied'}), 403
    p = os.path.abspath(os.path.join(instance_base, sub, name))
    if not is_safe_path(instance_base, p):
        return jsonify({'content':'Access denied'}), 403
    try:
        # Prevent OOM: refuse to read files larger than 10MB
        file_size = os.path.getsize(p)
        if file_size > 10 * 1024 * 1024:
            return jsonify({'content': f'Error: File too large ({file_size // (1024*1024)}MB). Max: 10MB'}), 413
        with open(p,'r',encoding='utf-8',errors='ignore') as f:
            return jsonify({'content':f.read()})
    except Exception as e:
        return jsonify({'content':f'Error: {e}'})

@files_bp.route('/<folder>/save', methods=['POST'])
def fsave(folder):
    allowed, err = check_server_access(folder)
    if not allowed: return err
    d    = request.json or {}
    name = d.get('name', '')
    sub  = d.get('path', '')
    if not isinstance(name, str) or not isinstance(sub, str):
        return api_error('Invalid parameters', 400)
    instance_base = os.path.abspath(os.path.join(current_app.config['BASE_STORAGE'], folder))
    if name in PROTECTED_FILES:
        return api_error('Access denied', 403)
    p = os.path.abspath(os.path.join(instance_base, sub, name))
    if not is_safe_path(instance_base, p):
        return api_error('Access denied', 403)
    try:
        with open(p,'w',encoding='utf-8') as f: f.write(d.get('content',''))
        return api_success('saved')
    except Exception as e:
        return api_error(str(e))

@files_bp.route('/<folder>/delete-bulk', methods=['POST'])
def delete_bulk(folder):
    allowed, err = check_server_access(folder)
    if not allowed: return err
    d     = request.json or {}
    sub   = d.get('path','')
    names = d.get('names',[])
    if not isinstance(names, list) or not isinstance(sub, str):
        return api_error('Invalid parameters', 400)
    cleaned_names = []
    for n in names:
        if isinstance(n, str):
            cleaned_names.append(n)
    names = cleaned_names
    instance_base = os.path.abspath(os.path.join(current_app.config['BASE_STORAGE'], folder))
    base = os.path.abspath(os.path.join(instance_base, sub))
    if not is_safe_path(instance_base, base):
        return api_error('Access denied', 403)
    if not os.path.isdir(base):
        return api_error('Directory not found', 404)
    if not names: names = [f for f in os.listdir(base) if f != 'console.log']
    for name in names:
        if name in ['console.log'] + PROTECTED_FILES: continue
        p = os.path.abspath(os.path.join(base, name))
        if not is_safe_path(instance_base, p): continue
        try:
            if os.path.isdir(p): shutil.rmtree(p)
            elif os.path.exists(p): os.remove(p)
        except: pass
    return api_success('ok')

@files_bp.route('/<folder>/create-file', methods=['POST'])
def create_file_route(folder):
    allowed, err = check_server_access(folder)
    if not allowed: return err
    d = request.json or {}
    name_val = d.get('name', 'newfile.py')
    sub_val = d.get('path', '')
    if not isinstance(name_val, str) or not isinstance(sub_val, str):
        return api_error('Invalid parameters', 400)
    instance_base = os.path.abspath(os.path.join(current_app.config['BASE_STORAGE'], folder))
    name = secure_filename(name_val)
    if name in PROTECTED_FILES:
        return api_error('Access denied', 403)
    p = os.path.abspath(os.path.join(instance_base, sub_val, name))
    if not is_safe_path(instance_base, p):
        return api_error('Access denied', 403)
    try:
        with open(p,'w') as f: f.write('')
        return api_success('success')
    except Exception as e:
        return api_error(str(e))

@files_bp.route('/<folder>/create-folder', methods=['POST'])
def create_folder_route(folder):
    allowed, err = check_server_access(folder)
    if not allowed: return err
    d = request.json or {}
    name_val = d.get('name', 'new_folder')
    sub_val = d.get('path', '')
    if not isinstance(name_val, str) or not isinstance(sub_val, str):
        return api_error('Invalid parameters', 400)
    instance_base = os.path.abspath(os.path.join(current_app.config['BASE_STORAGE'], folder))
    name = secure_filename(name_val)
    if name in PROTECTED_FILES:
        return api_error('Access denied', 403)
    p = os.path.abspath(os.path.join(instance_base, sub_val, name))
    if not is_safe_path(instance_base, p):
        return api_error('Access denied', 403)
    try:
        os.makedirs(p, exist_ok=True)
        return api_success('success')
    except Exception as e:
        return api_error(str(e))

@files_bp.route('/<folder>/upload', methods=['POST'])
def upload_file(folder):
    allowed, err = check_server_access(folder)
    if not allowed: return err
    sub  = request.form.get('path','')
    file = request.files.get('file')
    if not file: return api_error('No file')
    
    instance_base = os.path.abspath(os.path.join(current_app.config['BASE_STORAGE'], folder))
    dest = os.path.abspath(os.path.join(instance_base, sub))
    if not is_safe_path(instance_base, dest):
        return api_error('Access denied', 403)
        
    os.makedirs(dest, exist_ok=True)
    filename = secure_filename(file.filename)
    if filename in PROTECTED_FILES:
        return api_error('Access denied', 403)
    filepath = os.path.abspath(os.path.join(dest, filename))
    if not is_safe_path(instance_base, filepath):
        return api_error('Access denied', 403)
    
    try:
        file.save(filepath)
        if not os.path.exists(filepath):
            return api_error(f'File {filename} was not saved')
        
        logpath = os.path.join(dest, 'console.log')
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            with open(logpath, 'a', encoding='utf-8') as f:
                f.write(f"\n[{now}] 📁 Uploaded: {filename} ({os.path.getsize(filepath)} bytes)\n")
        except: pass
        
        return jsonify({'status':'success','filename':filename})
    except Exception as e:
        return api_error(f'Upload failed: {str(e)}')

@files_bp.route('/<folder>/rename', methods=['POST'])
def rename_file(folder):
    allowed, err = check_server_access(folder)
    if not allowed: return err
    d    = request.json or {}
    old_val = d.get('old')
    new_val = d.get('new')
    sub_val = d.get('path', '')
    if not isinstance(old_val, str) or not isinstance(new_val, str) or not isinstance(sub_val, str) or not old_val or not new_val:
        return api_error('Invalid parameters', 400)
    instance_base = os.path.abspath(os.path.join(current_app.config['BASE_STORAGE'], folder))
    base = os.path.abspath(os.path.join(instance_base, sub_val))
    if not is_safe_path(instance_base, base):
        return api_error('Access denied', 403)
    try:
        if old_val in PROTECTED_FILES or new_val in PROTECTED_FILES:
            return api_error('Access denied', 403)
        old_p = os.path.abspath(os.path.join(base, old_val))
        new_p = os.path.abspath(os.path.join(base, new_val))
        if not is_safe_path(instance_base, old_p) or not is_safe_path(instance_base, new_p):
            return api_error('Access denied', 403)
        os.rename(old_p, new_p)
        return api_success('success')
    except Exception as e:
        return api_error(str(e))

@files_bp.route('/<folder>/download/<name>')
def download_file(folder, name):
    allowed, err = check_server_access(folder)
    if not allowed: return err
    sub = request.args.get('path','')
    instance_base = os.path.abspath(os.path.join(current_app.config['BASE_STORAGE'], folder))
    if name in PROTECTED_FILES: return "Access Denied", 403
    p = os.path.abspath(os.path.join(instance_base, sub, name))
    if not is_safe_path(instance_base, p): return "Access Denied", 403
    if not os.path.isfile(p): return "Not found", 404
    return send_file(p, as_attachment=True)

@files_bp.route('/<folder>/zip-bulk', methods=['POST'])
def zip_bulk(folder):
    allowed, err = check_server_access(folder)
    if not allowed: return err
    d     = request.json or {}
    names = d.get('names',[])
    sub   = d.get('path','')
    if not isinstance(names, list) or not isinstance(sub, str):
        return api_error('names must be a list and path must be a string', 400)
    cleaned_names = []
    for n in names:
        if isinstance(n, str):
            cleaned_names.append(n)
    names = cleaned_names
    instance_base = os.path.abspath(os.path.join(current_app.config['BASE_STORAGE'], folder))
    base = os.path.abspath(os.path.join(instance_base, sub))
    if not is_safe_path(instance_base, base):
        return api_error('Access denied', 403)
    if not os.path.isdir(base):
        return api_error('Directory not found', 404)
    if not names: names = [f for f in os.listdir(base) if f != 'console.log']
    
    db = get_db()
    srv = db.execute('SELECT name FROM servers WHERE folder=?', (folder,)).fetchone()
    db.close()
    import re
    srv_name = srv['name'] if srv else 'archive'
    safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', srv_name).strip('_')
    if not safe_name: safe_name = 'archive'
    zname = f"{safe_name}.zip"
    zpath = os.path.abspath(os.path.join(base, zname))
    if not is_safe_path(instance_base, zpath):
        return api_error('Access denied', 403)
    with zipfile.ZipFile(zpath,'w') as z:
        for n in names:
            if n in PROTECTED_FILES: continue
            p = os.path.abspath(os.path.join(base, n))
            if not is_safe_path(instance_base, p): continue
            if n == zname: continue
            if os.path.isdir(p):
                for root,_,files in os.walk(p):
                    for file in files:
                        fp = os.path.abspath(os.path.join(root, file))
                        if is_safe_path(instance_base, fp):
                            z.write(fp, os.path.relpath(fp, base))
            elif os.path.exists(p): z.write(p, n)
    return jsonify({'status':'success','zip':zname})

@files_bp.route('/<folder>/unzip', methods=['POST'])
def unzip_file(folder):
    allowed, err = check_server_access(folder)
    if not allowed: return err
    d    = request.json or {}
    sub  = d.get('path','')
    zname = d.get('name','')
    if not isinstance(sub, str) or not isinstance(zname, str):
        return api_error('Invalid parameters', 400)
    instance_base = os.path.abspath(os.path.join(current_app.config['BASE_STORAGE'], folder))
    base = os.path.abspath(os.path.join(instance_base, sub))
    if not is_safe_path(instance_base, base):
        return api_error('Access denied', 403)
    zpath = os.path.abspath(os.path.join(base, zname))
    if not is_safe_path(instance_base, zpath):
        return api_error('Access denied', 403)
    
    logpath = os.path.join(base, 'console.log')
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    if not os.path.exists(zpath):
        msg = f'ZIP file not found: {zname}'
        try:
            with open(logpath, 'a', encoding='utf-8') as f:
                f.write(f"\n[{now}] ✗ UNZIP FAILED: {msg}\n")
        except: pass
        return api_error(msg)
    
    if not zipfile.is_zipfile(zpath):
        msg = f'Not a valid ZIP file: {zname}'
        try:
            with open(logpath, 'a', encoding='utf-8') as f:
                f.write(f"\n[{now}] ✗ UNZIP FAILED: {msg}\n")
        except: pass
        return api_error(msg)
    
    try:
        with open(logpath, 'a', encoding='utf-8') as f:
            f.write(f"\n[{now}] 📂 Extracting {zname}...\n")
        
        with zipfile.ZipFile(zpath,'r') as z:
            # Zip Slip Validation
            for member in z.infolist():
                target_member_path = os.path.abspath(os.path.join(base, member.filename))
                if not is_safe_path(instance_base, target_member_path):
                    raise Exception(f"Directory traversal detected in ZIP: {member.filename}")
            z.extractall(base)
        
        os.remove(zpath)
        try:
            flatten_extracted_folder(base)
        except:
            pass
        with open(logpath, 'a', encoding='utf-8') as f:
            f.write(f"[{now}] ✓ Successfully extracted and removed {zname}\n")
        return api_success(f'Extracted {zname}')
    except Exception as e:
        msg = f'Extraction error: {str(e)}'
        try:
            with open(logpath, 'a', encoding='utf-8') as f:
                f.write(f"\n[{now}] ✗ UNZIP ERROR: {msg}\n")
        except: pass
        return api_error(msg)

@files_bp.route('/<folder>/copy-bulk', methods=['POST'])
def copy_bulk(folder):
    allowed, err = check_server_access(folder)
    if not allowed: return err
    d = request.json or {}
    sub = d.get('path', '')
    names = d.get('names', [])
    target_sub = d.get('target_path', '')
    
    if not isinstance(names, list) or not isinstance(sub, str) or not isinstance(target_sub, str):
        return api_error('Invalid parameters', 400)
        
    instance_base = os.path.abspath(os.path.join(current_app.config['BASE_STORAGE'], folder))
    source_dir = os.path.abspath(os.path.join(instance_base, sub))
    target_dir = os.path.abspath(os.path.join(instance_base, target_sub))
    
    if not is_safe_path(instance_base, source_dir) or not is_safe_path(instance_base, target_dir):
        return api_error('Access denied', 403)
        
    if not os.path.isdir(source_dir) or not os.path.isdir(target_dir):
        return api_error('Directory not found', 404)
        
    copied_count = 0
    for name in names:
        if not isinstance(name, str): continue
        if name in ['console.log'] + PROTECTED_FILES: continue
        
        src_file = os.path.abspath(os.path.join(source_dir, name))
        dst_file = os.path.abspath(os.path.join(target_dir, name))
        
        if not is_safe_path(instance_base, src_file) or not is_safe_path(instance_base, dst_file):
            continue
            
        if src_file == dst_file or (os.path.isdir(src_file) and dst_file.startswith(src_file + os.path.sep)):
            continue
            
        try:
            if os.path.isdir(src_file):
                shutil.copytree(src_file, dst_file, dirs_exist_ok=True)
            else:
                shutil.copy2(src_file, dst_file)
            copied_count += 1
        except Exception as e:
            return api_error(f"Failed to copy '{name}': {str(e)}", 500)
            
    return jsonify({'status': 'success', 'copied_count': copied_count})

@files_bp.route('/<folder>/move-bulk', methods=['POST'])
def move_bulk(folder):
    allowed, err = check_server_access(folder)
    if not allowed: return err
    d = request.json or {}
    sub = d.get('path', '')
    names = d.get('names', [])
    target_sub = d.get('target_path', '')
    
    if not isinstance(names, list) or not isinstance(sub, str) or not isinstance(target_sub, str):
        return api_error('Invalid parameters', 400)
        
    instance_base = os.path.abspath(os.path.join(current_app.config['BASE_STORAGE'], folder))
    source_dir = os.path.abspath(os.path.join(instance_base, sub))
    target_dir = os.path.abspath(os.path.join(instance_base, target_sub))
    
    if not is_safe_path(instance_base, source_dir) or not is_safe_path(instance_base, target_dir):
        return api_error('Access denied', 403)
        
    if not os.path.isdir(source_dir) or not os.path.isdir(target_dir):
        return api_error('Directory not found', 404)
        
    moved_count = 0
    for name in names:
        if not isinstance(name, str): continue
        if name in ['console.log'] + PROTECTED_FILES: continue
        
        src_file = os.path.abspath(os.path.join(source_dir, name))
        dst_file = os.path.abspath(os.path.join(target_dir, name))
        
        if not is_safe_path(instance_base, src_file) or not is_safe_path(instance_base, dst_file):
            continue
            
        if src_file == dst_file or (os.path.isdir(src_file) and dst_file.startswith(src_file + os.path.sep)):
            continue
            
        try:
            if os.path.exists(dst_file):
                if os.path.isdir(dst_file):
                    shutil.rmtree(dst_file)
                else:
                    os.remove(dst_file)
            shutil.move(src_file, dst_file)
            moved_count += 1
        except Exception as e:
            return api_error(f"Failed to move '{name}': {str(e)}", 500)
            
    return jsonify({'status': 'success', 'moved_count': moved_count})
