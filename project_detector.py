import os
import re

def detect_project_type(instance_path):
    """Scans the directory files to automatically classify project types (recursive & case-insensitive)."""
    if not os.path.exists(instance_path):
        return 'script'

    # 1. Node.js Express/API Check (Root package.json)
    if os.path.exists(os.path.join(instance_path, 'package.json')):
        return 'node'

    # 2. Django Check (Root manage.py)
    if os.path.exists(os.path.join(instance_path, 'manage.py')):
        return 'django'

    # 3. Read Python configuration/dependency files at root level
    req_file = os.path.join(instance_path, 'requirements.txt')
    pyproject_file = os.path.join(instance_path, 'pyproject.toml')

    dependencies = ""
    if os.path.exists(req_file):
        try:
            with open(req_file, 'r', encoding='utf-8', errors='ignore') as f:
                dependencies += f.read().lower()
        except:
            pass

    if os.path.exists(pyproject_file):
        try:
            with open(pyproject_file, 'r', encoding='utf-8', errors='ignore') as f:
                dependencies += f.read().lower()
        except:
            pass

    if 'fastapi' in dependencies:
        return 'fastapi'
    if 'flask' in dependencies or 'quart' in dependencies:
        return 'flask'

    # 4. Fallback: Scan python files recursively (up to 2 levels deep) for imports & instantiation
    try:
        for root, dirs, files in os.walk(instance_path):
            depth = root[len(instance_path):].count(os.sep)
            if depth > 2:
                continue
            for file in files:
                file_lower = file.lower()
                if file_lower.endswith('.py') and file_lower != 'console.log':
                    full_path = os.path.join(root, file)
                    try:
                        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                            code_lower = f.read().lower()
                            # Check for FastAPI imports or instantiation
                            if re.search(r'\bfrom\s+fastapi\b|\bimport\s+fastapi\b', code_lower) or 'fastapi(' in code_lower:
                                return 'fastapi'
                            # Check for Flask / Quart imports or instantiation
                            if re.search(r'\bfrom\s+(flask|quart)\b|\bimport\s+(flask|quart)\b', code_lower) or 'flask(__name__)' in code_lower.replace(' ', ''):
                                return 'flask'
                    except:
                        pass
    except Exception as e:
        print(f"[detect_project_type] Error scanning python files: {e}")

    # 5. Fallback: Scan Node/JS files recursively for express or server setups
    try:
        for root, dirs, files in os.walk(instance_path):
            depth = root[len(instance_path):].count(os.sep)
            if depth > 2:
                continue
            for file in files:
                file_lower = file.lower()
                if file_lower.endswith(('.js', '.ts', '.cjs', '.mjs')):
                    full_path = os.path.join(root, file)
                    try:
                        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                            code_lower = f.read().lower()
                            if 'express' in code_lower or 'http.createserver' in code_lower or 'koa' in code_lower or 'fastify' in code_lower:
                                return 'node'
                    except:
                        pass
    except Exception as e:
        print(f"[detect_project_type] Error scanning js files: {e}")

    return 'script'

def detect_endpoints(instance_path):
    """Scans python and javascript files recursively inside the instance directory to find web route endpoints."""
    endpoints = []
    if not os.path.exists(instance_path):
        return endpoints

    try:
        for root, dirs, files in os.walk(instance_path):
            depth = root[len(instance_path):].count(os.sep)
            if depth > 2:
                continue
            for file in files:
                file_lower = file.lower()
                if file_lower == 'console.log':
                    continue
                full_path = os.path.join(root, file)
                
                # Scan python files
                if file_lower.endswith('.py'):
                    try:
                        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                            code = f.read()
                            endpoints.extend(detect_python_endpoints(code))
                    except:
                        pass
                # Scan javascript/typescript files
                elif file_lower.endswith(('.js', '.ts', '.cjs', '.mjs')):
                    try:
                        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                            code = f.read()
                            endpoints.extend(detect_js_endpoints(code))
                    except:
                        pass
    except Exception as e:
        print(f"[detect_endpoints] Error scanning files: {e}")

    # Deduplicate by path
    unique_endpoints = []
    seen_paths = set()
    for ep in endpoints:
        p = ep['path']
        # normalize path: ensure starts with /
        if not p.startswith('/'):
            p = '/' + p
        if p not in seen_paths:
            seen_paths.add(p)
            ep['path'] = p
            unique_endpoints.append(ep)

    return unique_endpoints

def detect_python_endpoints(file_content):
    route_matches = re.finditer(r'''@(?:[a-zA-Z0-9_]+)\.(?:route|get|post|put|delete)\(\s*['"]([^'"]+)['"]''', file_content)
    endpoints = []
    
    for match in route_matches:
        path = match.group(1)
        if path == '/' or '<path:' in path or '*' in path:
            continue
            
        start_idx = match.end()
        # Find next route to limit the function block search
        next_route = re.search(r'''@(?:[a-zA-Z0-9_]+)\.(?:route|get|post|put|delete)\(''', file_content[start_idx:])
        block_end = start_idx + (next_route.start() if next_route else 1200)
        func_block = file_content[start_idx:block_end]
        
        # Scan for request.args.get('param') etc.
        params = re.findall(r'''(?:request\.args\.get|request\.args\.getlist|request\.args|request\.query_params\.get)\(\s*['"]([^'"]+)['"]''', func_block)
        
        # Check query params in signature
        sig_match = re.search(r'''def\s+[a-zA-Z0-9_]+\s*\(([^)]*)\)''', func_block)
        if sig_match:
            sig_args = sig_match.group(1)
            for arg in re.findall(r'''([a-zA-Z0-9_]+)(?:\s*:\s*[a-zA-Z0-9_\[\]]+)?(?:\s*=\s*['"]?([^,'"]*)['"]?)?''', sig_args):
                arg_name = arg[0]
                if arg_name not in ['self', 'request', 'db', 'conn', 'session', 'args'] and arg_name not in params:
                    params.append(arg_name)
                    
        endpoints.append({
            'path': path,
            'params': list(dict.fromkeys(params))
        })
    return endpoints

def detect_js_endpoints(file_content):
    route_matches = re.finditer(r'''(?:app|router)\.(?:get|post|put|delete)\(\s*['"]([^'"]+)['"]''', file_content)
    endpoints = []
    for match in route_matches:
        path = match.group(1)
        if path == '/' or '*' in path:
            continue
        start_idx = match.end()
        next_route = re.search(r'''(?:app|router)\.(?:get|post|put|delete)\(''', file_content[start_idx:])
        block_end = start_idx + (next_route.start() if next_route else 1200)
        func_block = file_content[start_idx:block_end]
        
        params = re.findall(r'''req\.query\.([a-zA-Z0-9_]+)''', func_block)
        params2 = re.findall(r'''req\.query\[\s*['"]([^'"]+)['"]''', func_block)
        all_params = list(dict.fromkeys(params + params2))
        endpoints.append({
            'path': path,
            'params': all_params
        })
    return endpoints
