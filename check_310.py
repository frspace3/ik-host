import os, glob, re, ast

def check_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # We will use simple regex to find f-strings and look for issues inside them.
    # regex for f-strings
    pattern = re.compile(r'(f\'\'\'.*?\'\'\'|f\"\"\".*?\"\"\"|f\'[^\'\n]*\'|f\"[^\"\n]*\")', re.DOTALL)
    
    for match in pattern.finditer(content):
        fstr = match.group(1)
        # find content inside {}
        braces = re.compile(r'\{([^{}]+)\}')
        for b_match in braces.finditer(fstr):
            expr = b_match.group(1)
            # check for backslash
            if '\\' in expr:
                print(f'{file_path}: backslash in f-string expression: {expr}')
            # check for same quote
            if fstr.startswith('f\'') and not fstr.startswith('f\'\'\''):
                if '\'' in expr:
                    print(f'{file_path}: single quote in single quote f-string expression: {expr}')
            elif fstr.startswith('f\"') and not fstr.startswith('f\"\"\"'):
                if '\"' in expr:
                    print(f'{file_path}: double quote in double quote f-string expression: {expr}')

for root, dirs, files in os.walk('.'):
    if '.git' in root or '__pycache__' in root or '.venv' in root:
        continue
    for f in files:
        if f.endswith('.py'):
            check_file(os.path.join(root, f))
