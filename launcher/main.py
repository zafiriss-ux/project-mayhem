"""
TITAN Launcher — Main Entry Point

Beginner-friendly one-click launcher for TITAN OS.

Workflow:
  1. Print welcome banner
  2. Validate environment (Python, OS, disk, data directory)
  3. Run first-time setup wizard (if .env missing)
  4. Load .env into environment variables
  5. Import and run titan.__main__.main()
  6. Catch all errors and translate to user-friendly messages
  7. Exit with code 0 (success) or 1 (failure)

Usage:
    python launcher/main.py                # Interactive mode
    python -m launcher.main                # Module mode
    TITAN.exe                              # PyInstaller bundle (future)
"""

import os
import sys
from pathlib import Path

# Add project root to path so we can import titan
sys.path.insert(0, str(Path(__file__).parent.parent.absolute()))

from launcher import __version__
from launcher.errors import TitanError, translate_kernel_error
from launcher.logger import init_launcher_logging
from launcher.validator import get_data_directory, validate_environment
from launcher.wizard import ensure_config, env_exists, load_env

# ══════════════════════════════════════════════════════════════════════════════
# Argument Redaction
# ══════════════════════════════════════════════════════════════════════════════

def _redact_argv(argv: list) -> list:
    """Return a copy of argv with sensitive flag values replaced by <redacted>."""
    result = []
    skip_next = False
    for token in argv:
        if skip_next:
            result.append("<redacted>")
            skip_next = False
        elif "=" in token and token.startswith("--"):
            flag, _ = token.split("=", 1)
            result.append(f"{flag}=<redacted>")
        elif token.startswith("--") and len(token) > 2:
            result.append(token)
            skip_next = True
        else:
            result.append(token)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Banner
# ══════════════════════════════════════════════════════════════════════════════

def print_banner():
    """Print ASCII art welcome banner."""
    banner = r"""
╔════════════════════════════════════════════════════════════════════╗
║                                                                    ║
║   ▀█▀ █ ▀█▀ ▄▀█ █▄ █   █▀█ █▀   ▀█ █ ▀▀█                         ║
║    █  █  █  █▀█ █ ▀█   █▄█ ▄█    █▄▀     █                        ║
║                                                                    ║
║   Closed-Loop Sovereign Training Intelligence                     ║
║   https://github.com/zafiriss-ux/project-mayhem                   ║
║                                                                    ║
╚════════════════════════════════════════════════════════════════════╝
"""
    print(banner)
    print(f"   Version: {__version__}")
    print(f"   Data Directory: {get_data_directory()}\n")


# ══════════════════════════════════════════════════════════════════════════════
# Environment Setup
# ══════════════════════════════════════════════════════════════════════════════

def load_env_to_os():
    """
    Load .env file variables into os.environ.

    This allows titan kernel to access them via os.getenv().
    """
    env_vars = load_env()
    for key, value in env_vars.items():
        os.environ[key] = value
    if env_vars:
        print(f"✓ Loaded {len(env_vars)} configuration variables.\n")


# ══════════════════════════════════════════════════════════════════════════════
# Kernel Invocation
# ══════════════════════════════════════════════════════════════════════════════

def run_titan_kernel():
    """
    Import and run the TITAN kernel.

    Raises:
        TitanError or any kernel exception
    """
    print("🚀 Starting TITAN kernel...\n")
    print("=" * 70)

    try:
        # Import titan kernel (this will fail if titan/ is not on path)
        import titan
        print(f"   Kernel version: {getattr(titan, '__version__', 'unknown')}")

        print("   Status: Kernel initialized successfully.")
        print("=" * 70)

        import titan.__main__ as titan_main
        titan_main.main()

    except ImportError as e:
        raise TitanError(
            code='KERNEL_IMPORT_FAILED',
            message="Could not import TITAN kernel.",
            remediation="Ensure titan/ directory exists in project root.",
            details=str(e),
        ) from e
    except Exception as e:
        # Translate raw kernel exceptions to TitanError
        raise translate_kernel_error(e) from e


# ══════════════════════════════════════════════════════════════════════════════
# Main Entry Point
# ══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    """
    Main launcher entry point.

    Returns:
        Exit code: 0 = success, 1 = failure
    """
    # Check for --version flag (forensic metadata)
    if '--version' in sys.argv:
        from launcher.paths import get_path_info

        path_info = get_path_info()
        frozen = path_info['frozen']

        print(f"TITAN OS v{__version__}")
        print(f"Launcher: v{__version__}")
        print("Kernel: v5.7.5")
        print("Build date: 2026-02-19")
        print(f"Frozen mode: {'Yes (TITAN.exe)' if frozen else 'No (Python script)'}")
        print(f"Python: {sys.version.split()[0]}")

        if frozen:
            print(f"Executable: {path_info['sys.executable']}")
        else:
            print(f"Script: {__file__}")

        return 0

    # Check for --debug flag
    debug_mode = '--debug' in sys.argv

    # Initialize logging
    logger = init_launcher_logging(debug=debug_mode)
    logger.info(f"Launcher started with args: {_redact_argv(sys.argv)}")

    # Debug: Print path diagnostics (frozen-safe troubleshooting)
    if debug_mode:
        import json

        from launcher.paths import get_path_info
        print("\n" + "="*70)
        print("DEBUG: Path Diagnostics (Frozen-Safe Resolution)")
        print("="*70)
        path_info = get_path_info()
        for key, value in path_info.items():
            print(f"  {key:20} {value}")
        print("="*70 + "\n")
        logger.debug(f"Path info: {json.dumps(path_info, indent=2)}")

    print_banner()

    # Step 1: Validate environment
    success, errors = validate_environment()
    if not success:
        print("\n❌ Pre-flight checks failed:\n")
        for error in errors:
            print(error.to_user_message())
        print("\n   Fix the issues above and try again.\n")
        return 1

    print("✅ All pre-flight checks passed.\n")

    # Step 2: Ensure configuration (.env)
    if not env_exists():
        # First-run setup needed
        use_gui = '--console' not in sys.argv  # Default to GUI unless --console flag

        if use_gui:
            # Try GUI wizard (requires tkinter)
            try:
                from launcher.gui_wizard import run_gui_wizard
                print("🎨 Launching GUI setup wizard...\n")
                if not run_gui_wizard():
                    print("\n❌ Setup cancelled or failed.\n")
                    return 1
            except ImportError:
                # Tkinter not available — fall back to console
                print("⚠️  GUI not available. Using console wizard.\n")
                if not ensure_config():
                    print("\n❌ Configuration setup failed or was cancelled.\n")
                    return 1
            except Exception as e:
                # GUI crashed — fall back to console wizard
                logger.error(f"GUI wizard crashed: {e}", exc_info=True)
                print(f"⚠️  GUI wizard crashed: {e}")
                print("   Falling back to console wizard...\n")
                if not ensure_config():
                    print("\n❌ Configuration setup failed or was cancelled.\n")
                    return 1
        else:
            # Console wizard (--console flag or non-interactive environment)
            if not ensure_config():
                print("\n❌ Configuration setup failed or was cancelled.\n")
                return 1
    else:
        print("✓ Configuration found.\n")

    # Step 3: Load .env into os.environ
    load_env_to_os()

    # Step 4: Run TITAN kernel
    try:
        run_titan_kernel()
    except TitanError as e:
        print(f"\n{e.to_user_message()}\n")
        if e.details:
            print(f"   Details: {e.details}\n")
        return 1
    except KeyboardInterrupt:
        print("\n\n⚠️  TITAN stopped by user (Ctrl+C).\n")
        return 0
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}\n")
        print("   Please report this issue to:")
        print("   https://github.com/zafiriss-ux/project-mayhem/issues\n")
        return 1
    else:
        return 0


if __name__ == '__main__':
    sys.exit(main())
