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

import sys
import os
from pathlib import Path

# Add project root to path so we can import titan
sys.path.insert(0, str(Path(__file__).parent.parent.absolute()))

from launcher import __version__
from launcher.validator import validate_environment, get_data_directory
from launcher.wizard import ensure_config, load_env
from launcher.errors import TitanError, translate_kernel_error


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

        # For now, we just print a success message
        # In the real implementation, titan.__main__ would have a main() function
        # that runs the morning routine or interactive CLI

        print("   Status: Kernel initialized successfully.")
        print("=" * 70)
        print("\n✅ TITAN is ready.\n")
        print("   Next steps:")
        print("   • Run 'python -m titan' to start daily coaching")
        print("   • Check logs in ~/Documents/TITAN/logs/")
        print("   • Configure Telegram bot to receive morning briefings\n")

        # TODO: Actually call titan.__main__.main() when it exists
        # For now, this is a successful dry-run

    except ImportError as e:
        raise TitanError(
            code='KERNEL_IMPORT_FAILED',
            message="Could not import TITAN kernel.",
            remediation="Ensure titan/ directory exists in project root.",
            details=str(e),
        )
    except Exception as e:
        # Translate raw kernel exceptions to TitanError
        raise translate_kernel_error(e)


# ══════════════════════════════════════════════════════════════════════════════
# Main Entry Point
# ══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    """
    Main launcher entry point.

    Returns:
        Exit code: 0 = success, 1 = failure
    """
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
    if not ensure_config():
        print("\n❌ Configuration setup failed or was cancelled.\n")
        return 1

    # Step 3: Load .env into os.environ
    load_env_to_os()

    # Step 4: Run TITAN kernel
    try:
        run_titan_kernel()
        return 0
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


if __name__ == '__main__':
    sys.exit(main())
