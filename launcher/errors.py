"""
TITAN Launcher — Structured Error System

All kernel errors are caught and translated to user-friendly messages.
Error codes follow the pattern: CATEGORY_SPECIFIC_ISSUE

Categories:
  ENV_*    — Environment/system issues (Python version, OS compatibility)
  CFG_*    — Configuration issues (.env missing, invalid format)
  DB_*     — Database issues (missing, corrupt, schema mismatch)
  VAL_*    — Validation issues (invalid credentials, unreachable API)
  NET_*    — Network issues (timeout, DNS, firewall)
  SYS_*    — System-level issues (permissions, disk space)
"""



class TitanError(Exception):
    """
    Base class for all TITAN launcher errors.

    Attributes:
        code:        Machine-readable error code (e.g., "ENV_PYTHON_VERSION")
        message:     Human-readable error description
        remediation: Actionable fix (shown to user)
        details:     Optional technical details (for logs)
    """

    def __init__(
        self,
        code: str,
        message: str,
        remediation: str = '',
        details: str | None = None,
    ):
        self.code = code
        self.message = message
        self.remediation = remediation
        self.details = details
        super().__init__(f"[{code}] {message}")

    def to_user_message(self) -> str:
        """
        Format error for display to end-user.
        Returns emoji + message + remediation.
        """
        emoji = self._get_emoji()
        parts = [f"{emoji} {self.message}"]
        if self.remediation:
            parts.append(f"\n   ➜ {self.remediation}")
        return '\n'.join(parts)

    def _get_emoji(self) -> str:
        """Map error category to emoji."""
        category = self.code.split('_')[0]
        return {
            'ENV': '🔴',
            'CFG': '⚙️',
            'DB':  '💾',
            'VAL': '🔑',
            'NET': '🌐',
            'SYS': '⚠️',
        }.get(category, '❌')


# ══════════════════════════════════════════════════════════════════════════════
# Environment Errors
# ══════════════════════════════════════════════════════════════════════════════

class EnvironmentError(TitanError):
    """Raised when system environment is incompatible."""

    @classmethod
    def python_version(cls, current: str, required: str = "3.11"):
        return cls(
            code='ENV_PYTHON_VERSION',
            message=f"Python {current} is not supported.",
            remediation=f"Install Python {required}+ from python.org",
        )

    @classmethod
    def missing_dependency(cls, package: str):
        return cls(
            code='ENV_MISSING_DEPENDENCY',
            message=f"Required package '{package}' not found.",
            remediation=f"Run: pip install {package}",
        )

    @classmethod
    def os_unsupported(cls, os_name: str):
        return cls(
            code='ENV_OS_UNSUPPORTED',
            message=f"Operating system '{os_name}' is not fully supported.",
            remediation="TITAN is optimized for Windows 10/11 and Linux. macOS may work but is untested.",
        )


# ══════════════════════════════════════════════════════════════════════════════
# Configuration Errors
# ══════════════════════════════════════════════════════════════════════════════

class ConfigurationError(TitanError):
    """Raised when .env or config files are missing/invalid."""

    @classmethod
    def env_missing(cls, path: str):
        return cls(
            code='CFG_ENV_MISSING',
            message=f".env file not found at: {path}",
            remediation="First-time setup will create one. Press Enter to continue.",
        )

    @classmethod
    def env_invalid(cls, key: str):
        return cls(
            code='CFG_ENV_INVALID',
            message=f".env file is missing required key: {key}",
            remediation=f"Add {key}=your_value to .env",
        )

    @classmethod
    def data_dir_permission(cls, path: str):
        return cls(
            code='CFG_DATA_DIR_PERMISSION',
            message=f"Cannot write to data directory: {path}",
            remediation="Check folder permissions or choose a different location.",
        )


# ══════════════════════════════════════════════════════════════════════════════
# Database Errors
# ══════════════════════════════════════════════════════════════════════════════

class DatabaseError(TitanError):
    """Raised when database operations fail."""

    @classmethod
    def missing(cls, path: str):
        return cls(
            code='DB_MISSING',
            message=f"Database not found at: {path}",
            remediation="Creating new database with schema v5.7...",
        )

    @classmethod
    def corrupted(cls, path: str, details: str):
        return cls(
            code='DB_CORRUPTED',
            message=f"Database file is corrupted: {path}",
            remediation="Backup current DB and delete it. TITAN will create a fresh one.",
            details=details,
        )

    @classmethod
    def schema_mismatch(cls, found: str, expected: str):
        return cls(
            code='DB_SCHEMA_MISMATCH',
            message=f"Database schema version mismatch: found {found}, expected {expected}",
            remediation="Running automatic migration...",
        )


# ══════════════════════════════════════════════════════════════════════════════
# Validation Errors (API credentials, tokens)
# ══════════════════════════════════════════════════════════════════════════════

class ValidationError(TitanError):
    """Raised when API credentials or tokens are invalid."""

    @classmethod
    def garmin_auth(cls, username: str):
        return cls(
            code='VAL_GARMIN_AUTH',
            message=f"Garmin authentication failed for user: {username}",
            remediation="Check username/password. Enable 2FA if required.",
        )

    @classmethod
    def telegram_token(cls):
        return cls(
            code='VAL_TELEGRAM_TOKEN',
            message="Telegram bot token is invalid.",
            remediation="Get a new token from @BotFather on Telegram.",
        )

    @classmethod
    def openai_key(cls):
        return cls(
            code='VAL_OPENAI_KEY',
            message="OpenAI API key is invalid or expired.",
            remediation="Get a valid key from platform.openai.com/api-keys",
        )


# ══════════════════════════════════════════════════════════════════════════════
# Network Errors
# ══════════════════════════════════════════════════════════════════════════════

class NetworkError(TitanError):
    """Raised when network operations fail."""

    @classmethod
    def unreachable(cls, service: str):
        return cls(
            code='NET_UNREACHABLE',
            message=f"Cannot reach {service} — check your internet connection.",
            remediation="Verify network is active and firewall allows TITAN.",
        )

    @classmethod
    def timeout(cls, service: str, timeout_sec: int):
        return cls(
            code='NET_TIMEOUT',
            message=f"{service} request timed out after {timeout_sec}s.",
            remediation="Retry or check if the service is down.",
        )


# ══════════════════════════════════════════════════════════════════════════════
# System Errors (disk, permissions)
# ══════════════════════════════════════════════════════════════════════════════

class SystemError(TitanError):
    """Raised for system-level issues."""

    @classmethod
    def disk_full(cls, path: str):
        return cls(
            code='SYS_DISK_FULL',
            message=f"Disk is full at: {path}",
            remediation="Free up disk space (at least 100 MB recommended).",
        )

    @classmethod
    def permission_denied(cls, path: str, operation: str):
        return cls(
            code='SYS_PERMISSION_DENIED',
            message=f"Permission denied: {operation} on {path}",
            remediation="Run as administrator or change folder permissions.",
        )


# ══════════════════════════════════════════════════════════════════════════════
# Error Registry (for kernel → launcher translation)
# ══════════════════════════════════════════════════════════════════════════════

ERROR_REGISTRY = {
    # Map kernel exception names to launcher error classes
    'FileNotFoundError':     DatabaseError,
    'PermissionError':       SystemError,
    'ConnectionError':       NetworkError,
    'TimeoutError':          NetworkError,
    'ValueError':            ConfigurationError,
    'KeyError':              ConfigurationError,
}


def translate_kernel_error(exc: Exception) -> TitanError:
    """
    Translate a raw kernel exception into a structured TitanError.

    Args:
        exc: Raw exception from titan kernel

    Returns:
        TitanError subclass with user-friendly message
    """
    exc_type = type(exc).__name__

    # Generic fallback
    return TitanError(
        code=f'KERNEL_{exc_type.upper()}',
        message=str(exc),
        remediation="Check logs for details.",
        details=repr(exc),
    )
