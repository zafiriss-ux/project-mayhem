"""
TITAN Launcher — Environment Validator

Pre-flight checks before starting TITAN kernel.
Validates Python version, OS compatibility, data directory, disk space, UTF-8.

All checks return (success: bool, error: Optional[TitanError]).
"""

import os
import platform
import shutil
import sys
from pathlib import Path

from launcher.errors import (
    ConfigurationError,
    EnvironmentError,
    SystemError,
    TitanError,
)

# ══════════════════════════════════════════════════════════════════════════════
# System Requirements
# ══════════════════════════════════════════════════════════════════════════════

MIN_PYTHON_VERSION = (3, 11)
MIN_DISK_SPACE_MB = 100


def get_data_directory() -> Path:
    """
    Get platform-specific data directory for TITAN.

    Windows: %USERPROFILE%\\Documents\\TITAN
    Linux:   ~/Documents/TITAN
    macOS:   ~/Documents/TITAN
    """
    if platform.system() == 'Windows':
        base = Path(os.environ.get('USERPROFILE', Path.home()))
    else:
        base = Path.home()
    return base / 'Documents' / 'TITAN'


# ══════════════════════════════════════════════════════════════════════════════
# Validation Checks
# ══════════════════════════════════════════════════════════════════════════════

def check_python_version() -> tuple[bool, TitanError | None]:
    """
    Validate Python version >= 3.11.

    Returns:
        (True, None) if OK, (False, EnvironmentError) otherwise
    """
    current = sys.version_info[:2]
    if current < MIN_PYTHON_VERSION:
        current_str = f"{current[0]}.{current[1]}"
        required_str = f"{MIN_PYTHON_VERSION[0]}.{MIN_PYTHON_VERSION[1]}"
        return False, EnvironmentError.python_version(current_str, required_str)
    return True, None


def check_os_compatibility() -> tuple[bool, TitanError | None]:
    """
    Check if OS is supported.

    Fully supported: Windows 10/11, Linux (Ubuntu, Debian, Arch, Fedora)
    Experimental:    macOS

    Returns:
        (True, None) always — just warns on macOS
    """
    os_name = platform.system()
    if os_name == 'Darwin':
        # macOS: warn but allow
        print("⚠️  macOS support is experimental. Report issues to GitHub.")
    return True, None


def check_utf8_environment() -> tuple[bool, TitanError | None]:
    """
    Ensure UTF-8 encoding is active.

    Python 3.11+ defaults to UTF-8 mode on Windows.
    Set PYTHONUTF8=1 environment variable if needed.

    Returns:
        (True, None) — this check always passes (Python 3.11+ handles it)
    """
    # Python 3.11+ with UTF-8 mode is default on Windows
    # Linux/macOS: locale should be UTF-8 already
    if sys.getdefaultencoding() != 'utf-8':
        # Force UTF-8 for stdout/stderr
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass  # Best-effort
    return True, None


def check_data_directory() -> tuple[bool, TitanError | None]:
    """
    Ensure data directory exists and is writable.

    Creates ~/Documents/TITAN/ if missing.
    Creates subdirectories: logs/, exports/

    Returns:
        (True, None) if OK, (False, ConfigurationError | SystemError) otherwise
    """
    data_dir = get_data_directory()
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / 'logs').mkdir(exist_ok=True)
        (data_dir / 'exports').mkdir(exist_ok=True)

        # Test write permission
        test_file = data_dir / '.write_test'
        test_file.write_text('test', encoding='utf-8')
        test_file.unlink()

        return True, None
    except PermissionError:
        return False, ConfigurationError.data_dir_permission(str(data_dir))
    except Exception as e:
        return False, SystemError.permission_denied(str(data_dir), 'create', details=str(e))


def check_disk_space() -> tuple[bool, TitanError | None]:
    """
    Ensure at least 100 MB free disk space in data directory.

    Returns:
        (True, None) if OK, (False, SystemError) otherwise
    """
    data_dir = get_data_directory()
    try:
        stat = shutil.disk_usage(data_dir.parent)  # Check parent if data_dir doesn't exist yet
        free_mb = stat.free / (1024 * 1024)
        if free_mb < MIN_DISK_SPACE_MB:
            return False, SystemError.disk_full(str(data_dir))
        return True, None
    except Exception:
        # If we can't check, assume it's OK (proceed optimistically)
        return True, None


def check_database() -> tuple[bool, TitanError | None]:
    """
    Check if database exists. If not, flag for creation.

    Returns:
        (True, None) if DB exists or can be created
        (False, DatabaseError) if corruption detected
    """
    from launcher.errors import DatabaseError
    data_dir = get_data_directory()
    db_path = data_dir / 'titan_core.db'

    if not db_path.exists():
        # DB missing — will be created on first run
        return True, DatabaseError.missing(str(db_path))

    # DB exists — check if it can be opened
    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1")
        conn.close()
        return True, None
    except Exception as e:
        return False, DatabaseError.corrupted(str(db_path), str(e))


# ══════════════════════════════════════════════════════════════════════════════
# Run All Checks
# ══════════════════════════════════════════════════════════════════════════════

def validate_environment() -> tuple[bool, list]:
    """
    Run all pre-flight checks.

    Returns:
        (all_passed: bool, errors: list[TitanError])
    """
    checks = [
        ("Python version", check_python_version),
        ("OS compatibility", check_os_compatibility),
        ("UTF-8 encoding", check_utf8_environment),
        ("Data directory", check_data_directory),
        ("Disk space", check_disk_space),
        ("Database", check_database),
    ]

    errors = []
    print("🔍 Running pre-flight checks...\n")

    for name, check_fn in checks:
        success, error = check_fn()
        if success and error is None:
            print(f"   ✓ {name}")
        elif success and error:
            # Warning (e.g., DB missing but will be created)
            print(f"   ⚠ {name}: {error.message}")
        else:
            # Fatal error
            print(f"   ✗ {name}: {error.message}")
            errors.append(error)

    print()
    return len(errors) == 0, errors
