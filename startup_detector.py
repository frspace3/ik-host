import os
import json
import re

def detect_startup_command(instance_path, project_type):
    """Detects the default startup command for a project type inside the instance directory (supports subfolders)."""
    if not os.path.exists(instance_path):
        return 'main.py'

    if project_type == 'django':
        # Look for manage.py recursively
        for root, dirs, files in os.walk(instance_path):
            depth = root[len(instance_path):].count(os.sep)
            if depth > 2:
                continue
            if 'manage.py' in files:
                rel_path = os.path.relpath(os.path.join(root, 'manage.py'), instance_path)
                return f"python {rel_path.replace(os.sep, '/')} runserver 0.0.0.0:$PORT"
        return 'python manage.py runserver 0.0.0.0:$PORT'

    if project_type == 'node':
        # Check root package.json first
        pkg_json_path = os.path.join(instance_path, 'package.json')
        if os.path.exists(pkg_json_path):
            try:
                with open(pkg_json_path, 'r', encoding='utf-8', errors='ignore') as f:
                    data = json.load(f)
                    if 'scripts' in data and 'start' in data['scripts']:
                        return 'npm start'
            except:
                pass
        
        # Check standard entrypoints recursively
        for root, dirs, files in os.walk(instance_path):
            depth = root[len(instance_path):].count(os.sep)
            if depth > 2:
                continue
            for entry in ['index.js', 'app.js', 'server.js', 'main.js']:
                if entry in files:
                    rel_path = os.path.relpath(os.path.join(root, entry), instance_path)
                    return f"node {rel_path.replace(os.sep, '/')}"
        return 'node index.js'

    if project_type == 'fastapi':
        # 1. Search for typical FastAPI entrypoint files recursively
        for root, dirs, files in os.walk(instance_path):
            depth = root[len(instance_path):].count(os.sep)
            if depth > 2:
                continue
            for entry in ['main.py', 'app.py', 'api.py', 'index.py']:
                if entry in files:
                    rel_dir = os.path.relpath(root, instance_path)
                    module_name = entry[:-3]
                    if rel_dir != '.':
                        module_path = rel_dir.replace(os.sep, '.') + '.' + module_name
                    else:
                        module_path = module_name
                    return f"uvicorn {module_path}:app --host 0.0.0.0 --port $PORT"
        
        # 2. Scan python files recursively for FastAPI instantiation
        try:
            for root, dirs, files in os.walk(instance_path):
                depth = root[len(instance_path):].count(os.sep)
                if depth > 2:
                    continue
                for file in files:
                    if file.lower().endswith('.py') and file != 'console.log':
                        p = os.path.join(root, file)
                        try:
                            with open(p, 'r', encoding='utf-8', errors='ignore') as f:
                                if 'fastapi' in f.read().lower():
                                    rel_dir = os.path.relpath(root, instance_path)
                                    module_name = file[:-3]
                                    if rel_dir != '.':
                                        module_path = rel_dir.replace(os.sep, '.') + '.' + module_name
                                    else:
                                        module_path = module_name
                                    return f"uvicorn {module_path}:app --host 0.0.0.0 --port $PORT"
                        except:
                            pass
        except:
            pass
        return 'uvicorn main:app --host 0.0.0.0 --port $PORT'

    if project_type == 'flask':
        # 1. Search for typical Flask entrypoint files recursively
        for root, dirs, files in os.walk(instance_path):
            depth = root[len(instance_path):].count(os.sep)
            if depth > 2:
                continue
            for entry in ['app.py', 'main.py', 'wsgi.py', 'run.py']:
                if entry in files:
                    rel_path = os.path.relpath(os.path.join(root, entry), instance_path)
                    return f"python {rel_path.replace(os.sep, '/')}"
                    
        # 2. Fallback to any python file containing Flask recursively
        try:
            for root, dirs, files in os.walk(instance_path):
                depth = root[len(instance_path):].count(os.sep)
                if depth > 2:
                    continue
                for file in files:
                    if file.lower().endswith('.py') and file != 'console.log':
                        p = os.path.join(root, file)
                        try:
                            with open(p, 'r', encoding='utf-8', errors='ignore') as f:
                                if 'flask' in f.read().lower():
                                    rel_path = os.path.relpath(p, instance_path)
                                    return f"python {rel_path.replace(os.sep, '/')}"
                        except:
                            pass
        except:
            pass
        return 'python app.py'

    # Fallback/Script type (Recursive)
    priority = ['main.py', 'app.py', 'bot.py', 'run.py', 'start.py', 'index.py']
    for root, dirs, files in os.walk(instance_path):
        depth = root[len(instance_path):].count(os.sep)
        if depth > 2:
            continue
        for entry in priority:
            if entry in files:
                rel_path = os.path.relpath(os.path.join(root, entry), instance_path)
                return f"python {rel_path.replace(os.sep, '/')}"

    # Search for first python file found recursively
    try:
        for root, dirs, files in os.walk(instance_path):
            depth = root[len(instance_path):].count(os.sep)
            if depth > 2:
                continue
            for file in files:
                if file.lower().endswith('.py') and file != 'console.log':
                    rel_path = os.path.relpath(os.path.join(root, file), instance_path)
                    return f"python {rel_path.replace(os.sep, '/')}"
    except:
        pass

    return 'python main.py'
