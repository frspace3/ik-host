import os
import re
import ast

def check_fstrings(directory):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # A naive regex to find backslashes within f-string expressions
                    # It's better to just check for backslash in the entire file if it has f-strings
                    tree = ast.parse(content)
                    
                    for node in ast.walk(tree):
                        if isinstance(node, ast.JoinedStr):
                            for value in node.values:
                                if isinstance(value, ast.FormattedValue):
                                    # FormattedValue represents the expression inside {}
                                    # We can get the source segment for this node
                                    # ast.get_source_segment(content, value)
                                    src = ast.get_source_segment(content, value)
                                    if src and '\\' in src:
                                        print(f"Warning: Found backslash in f-string expression in {filepath} at line {value.lineno}")
                                        print(f"  {src}")
                except Exception as e:
                    print(f"Error processing {filepath}: {e}")

check_fstrings(r"c:\Users\Imran kaiser LP\Documents\my hosting")
