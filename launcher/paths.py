"""
TITAN Launcher — Frozen-Safe Path Resolution

Handles path resolution for both:
  - Normal Python execution (python launcher/main.py)
  - Frozen PyInstaller execution (TITAN.exe)

When PyInstaller bundles the app, __file__ doesn't work reliably.
Use sys._MEIPASS to find the temporary extraction directory.

References:
  - https://pyinstaller.org/en/stable/runtime-information.html
"""

import sys
from pathlib import Path


# ══════════════════════════════════════════════════════════════════════════════
# Frozen Detection
# ══════════════════════════════════════════════════════════════════════════════

def is_frozen() -> bool:
    """
    Check if running as PyInstaller frozen executable.

    Returns:
        True if frozen (TITAN.exe), False if normal Python
    """
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')


# ══════════════════════════════════════════════════════════════════════════════
# Base Directories
# ══════════════════════════════════════════════════════════════════════════════

def get_bundle_dir() -> Path:
    """
    Get the directory containing the bundled application.

    Returns:
        - Frozen mode: sys._MEIPASS (temporary extraction directory)
        - Normal mode: Project root (parent of launcher/)
    """
    if is_frozen():
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        return Path(sys._MEIPASS)
    else:
        # Development mode — launcher/ is in project root
        return Path(__file__).parent.parent.resolve()


def get_executable_dir() -> Path:
    """
    Get the directory containing the executable or main script.

    Returns:
        - Frozen mode: Directory containing TITAN.exe
        - Normal mode: launcher/ directory
    """
    if is_frozen():
        # sys.executable points to TITAN.exe
        return Path(sys.executable).parent.resolve()
    else:
        # __file__ is launcher/paths.py
        return Path(__file__).parent.resolve()


# ══════════════════════════════════════════════════════════════════════════════
# Resource Access
# ══════════════════════════════════════════════════════════════════════════════

def get_resource_path(relative_path: str) -> Path:
    """
    Get absolute path to a bundled resource.

    Args:
        relative_path: Path relative to bundle root (e.g., "assets/icon.png")

    Returns:
        Absolute path to resource in bundle or project root

    Example:
        icon = get_resource_path("launcher/icon.png")
    """
    return get_bundle_dir() / relative_path


# ══════════════════════════════════════════════════════════════════════════════
# Validation
# ══════════════════════════════════════════════════════════════════════════════

def validate_paths() -> bool:
    """
    Validate that all critical paths are accessible.

    Returns:
        True if all paths valid, False otherwise
    """
    try:
        bundle_dir = get_bundle_dir()
        exe_dir = get_executable_dir()

        # Check bundle directory exists
        if not bundle_dir.exists():
            return False

        # Check we can resolve titan module
        titan_module = bundle_dir / 'titan'
        if not titan_module.exists() and not is_frozen():
            # In development, titan/ should be in project root
            return False

        # Check launcher module
        launcher_module = bundle_dir / 'launcher'
        if not launcher_module.exists() and not is_frozen():
            return False

        return True

    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
# Debug Info
# ══════════════════════════════════════════════════════════════════════════════

def get_path_info() -> dict:
    """
    Get debug information about path resolution.

    Returns:
        Dictionary with path details
    """
    return {
        'frozen': is_frozen(),
        'sys.executable': sys.executable,
        'sys._MEIPASS': getattr(sys, '_MEIPASS', None),
        'bundle_dir': str(get_bundle_dir()),
        'exe_dir': str(get_executable_dir()),
        'cwd': str(Path.cwd()),
        '__file__': str(Path(__file__).resolve()) if not is_frozen() else 'N/A (frozen)',
    }
