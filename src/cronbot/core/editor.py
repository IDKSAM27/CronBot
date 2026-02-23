import os
import json
import tempfile
import platform
import subprocess
from typing import Dict, Any

def interactive_edit(data: Dict[str, Any]) -> Dict[str, Any]:
    """Opens the generated data in a local editor for human review."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode='w') as tf:
        json.dump(data, tf, indent=4)
        temp_path = tf.name
    
    if platform.system() == 'Windows':
        git_vim_path = r"C:\Program Files\Git\usr\bin\vim.exe"
        if os.path.exists(git_vim_path):
            editor = git_vim_path
        else:
            editor = 'notepad'
    else:
        editor = os.environ.get('EDITOR', 'vim')
    
    try:
        exit_code = subprocess.call([editor, temp_path])
    except FileNotFoundError as e:
        raise RuntimeError(f"Editor executable not found: {editor}") from e

    if exit_code not in (0, None):
        raise RuntimeError(f"Editor exited with non-zero status: {exit_code}")
    
    try:
        with open(temp_path, 'r') as f:
            updated_data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError("Edited JSON is not valid JSON. Please fix syntax and retry.") from e
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path) 
        
    return updated_data
