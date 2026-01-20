import sys
import os

def get_base_path():
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # In dev mode, use the directory of the main script (or utility root)
        # Assuming this file is in utils/, so parent is root
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return base_path

def get_resource_path(relative_path):
    """ Get absolute path to read-only bundled resources (e.g., locales) """
    base_path = get_base_path()
    return os.path.join(base_path, relative_path)

def get_ffmpeg_path():
    """ Get absolute path to the bundled ffmpeg executable """
    base_path = get_base_path()
    ffmpeg_exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    return os.path.join(base_path, 'ffmpeg', 'bin', ffmpeg_exe)

def get_config_path(filename):
    """ 
    Get absolute path to mutable config files.
    In frozen mode, this should be beside the executable, not in _MEIPASS.
    """
    if getattr(sys, 'frozen', False):
        # If frozen, use the directory of the executable
        base_path = os.path.dirname(sys.executable)
    else:
        # In dev mode, use the project root
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    return os.path.join(base_path, filename)
