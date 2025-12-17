"""
QPT Logging - File and console logging for Quick Paint Tool debugging
"""
import os
from datetime import datetime
from pathlib import Path

# Log file path
_log_file = None
_log_enabled = True

def init_logging(log_dir: str = None):
    """Initialize file logging for QPT"""
    global _log_file
    
    if log_dir is None:
        # Default to Reggie's root directory
        log_dir = Path(__file__).parent.parent.parent
    
    log_path = Path(log_dir) / "qpt_debug.log"
    
    try:
        # Clear previous log
        _log_file = open(log_path, 'w', encoding='utf-8')
        _log_file.write(f"=== QPT Debug Log - {datetime.now().isoformat()} ===\n\n")
        _log_file.flush()
        print(f"[QPT] Logging to: {log_path}")
    except Exception as e:
        print(f"[QPT] Warning: Could not create log file: {e}")
        _log_file = None

def log(message: str, prefix: str = "[QPT]"):
    """Log a message to both console and file"""
    global _log_file
    
    full_message = f"{prefix} {message}"
    
    # Always print to console
    print(full_message)
    
    # Write to file if available
    if _log_file and _log_enabled:
        try:
            _log_file.write(full_message + "\n")
            _log_file.flush()
        except:
            pass

def log_engine(message: str):
    """Log a PaintingEngine message"""
    log(message, "[PaintingEngine]")

def log_handler(message: str):
    """Log a MouseEventHandler message"""
    log(message, "[MouseEventHandler]")

def log_hook(message: str):
    """Log a QPT Hook message"""
    log(message, "[QPT Hook]")

def log_brush(message: str):
    """Log a SmartBrush message"""
    log(message, "[SmartBrush]")

def close_logging():
    """Close the log file"""
    global _log_file
    if _log_file:
        try:
            _log_file.close()
        except:
            pass
        _log_file = None

def set_logging_enabled(enabled: bool):
    """Enable or disable file logging"""
    global _log_enabled
    _log_enabled = enabled
