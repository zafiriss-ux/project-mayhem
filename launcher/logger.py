"""
TITAN Launcher — Structured Logging

Centralized logging for launcher + kernel.
Logs written to ~/Documents/TITAN/logs/ with daily rotation.

Features:
  - File rotation (keep last 7 days)
  - Console output (optional, --debug flag)
  - Structured format: [TIMESTAMP] LEVEL: message
  - Redirect stdout/stderr to log file
  - Thread-safe (for Garmin sync, Telegram callbacks)
"""

import contextlib
import logging
import sys
import threading
from datetime import datetime
from pathlib import Path

from launcher.validator import get_data_directory

# ══════════════════════════════════════════════════════════════════════════════
# Log File Management
# ══════════════════════════════════════════════════════════════════════════════

def get_log_directory() -> Path:
    """Return path to logs directory."""
    return get_data_directory() / 'logs'


def get_log_file(prefix: str = 'launcher') -> Path:
    """
    Get today's log file path.

    Args:
        prefix: Log file prefix ('launcher' or 'titan')

    Returns:
        Path like ~/Documents/TITAN/logs/launcher_2026-02-19.log
    """
    log_dir = get_log_directory()
    log_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime('%Y-%m-%d')
    return log_dir / f"{prefix}_{today}.log"


def rotate_logs(keep_days: int = 7):
    """
    Delete log files older than N days.

    Args:
        keep_days: Number of days to keep (default 7)
    """
    log_dir = get_log_directory()
    if not log_dir.exists():
        return

    cutoff = datetime.now().timestamp() - (keep_days * 86400)
    for log_file in log_dir.glob('*.log'):
        if log_file.stat().st_mtime < cutoff:
            with contextlib.suppress(Exception):
                log_file.unlink()  # Best-effort cleanup


# ══════════════════════════════════════════════════════════════════════════════
# Logger Setup
# ══════════════════════════════════════════════════════════════════════════════

def setup_logging(debug: bool = False, prefix: str = 'launcher') -> logging.Logger:
    """
    Configure logging for launcher or kernel.

    Args:
        debug: Enable verbose console output (--debug flag)
        prefix: Log file prefix ('launcher' or 'titan')

    Returns:
        Configured logger instance
    """
    # Rotate old logs
    rotate_logs()

    # Get log file
    log_file = get_log_file(prefix)

    # Create logger
    logger = logging.getLogger(prefix)
    logger.setLevel(logging.DEBUG if debug else logging.INFO)

    # Clear existing handlers (avoid duplicates on re-initialization)
    logger.handlers.clear()

    # File handler (always enabled)
    file_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)-8s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Console handler (only if --debug and there is a console)
    if debug and sys.stdout is not None:
        console_formatter = logging.Formatter(
            '%(levelname)-8s %(message)s'
        )
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    logger.info(f"{'='*70}")
    logger.info(f"TITAN {prefix.upper()} — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Log file: {log_file}")
    logger.info(f"{'='*70}")

    return logger


# ══════════════════════════════════════════════════════════════════════════════
# Stdout/Stderr Redirection
# ══════════════════════════════════════════════════════════════════════════════

# Shared by the stdout and stderr tees: a failure logging stdout reports
# through stderr, so a guard per stream would let one round through.
_tee_state = threading.local()


class TeeStream:
    """
    Tee stdout/stderr to both console and log file.

    Usage:
        sys.stdout = TeeStream(sys.stdout, logger)

    The windowed Windows build has no console, so sys.stdout and sys.stderr
    are None there; output then goes to the log only.
    """

    def __init__(self, original_stream, logger: logging.Logger):
        self.original_stream = original_stream
        self.logger = logger

    def write(self, message):
        """Write to both console and log."""
        # A failing handler reports through logging's handleError, which writes
        # to sys.stderr, which is this stream. Logging that report again fails
        # the same way, and each report nests the previous one, so the loop
        # grows memory without bound. Inside a write, skip the logger.
        if message.strip() and not getattr(_tee_state, "writing", False):
            _tee_state.writing = True
            try:
                self.logger.info(message.rstrip())
            finally:
                _tee_state.writing = False
        # Also write to original stream (console)
        if self.original_stream is not None:
            self.original_stream.write(message)
        return len(message)

    def flush(self):
        """Flush original stream."""
        if self.original_stream is not None:
            self.original_stream.flush()


def redirect_output(logger: logging.Logger, enable: bool = True):
    """
    Redirect stdout/stderr to logger.

    Args:
        logger: Logger instance
        enable: True to redirect, False to restore original streams
    """
    if enable:
        sys.stdout = TeeStream(sys.stdout, logger)
        sys.stderr = TeeStream(sys.stderr, logger)
    else:
        # Restore original streams (if needed)
        if isinstance(sys.stdout, TeeStream):
            sys.stdout = sys.stdout.original_stream
        if isinstance(sys.stderr, TeeStream):
            sys.stderr = sys.stderr.original_stream


# ══════════════════════════════════════════════════════════════════════════════
# Quick Setup
# ══════════════════════════════════════════════════════════════════════════════

def init_launcher_logging(debug: bool = False) -> logging.Logger:
    """
    Quick setup for launcher logging.

    Args:
        debug: Enable --debug mode (console + file)

    Returns:
        Logger instance
    """
    logger = setup_logging(debug=debug, prefix='launcher')
    redirect_output(logger, enable=not debug)  # Only redirect if not in debug mode
    return logger
