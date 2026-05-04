"""
TITAN First-Run Setup Wizard

Interactive credential input at startup.
Saves to config_secrets.py (excluded from git).
"""

import getpass
import importlib
import json
import logging
import os
import re
import stat
from pathlib import Path

SECRETS_PATH = Path(__file__).parent.parent.parent / "config_secrets.py"
ENV_PATH     = Path(__file__).parent.parent.parent / ".env"
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
LOCATION_REGEX = re.compile(r"^[A-Za-zÀ-ÿ\s.'-]+,[A-Za-z]{2}$")
KEYRING_ENV_FLAG = "TITAN_USE_KEYRING"
KEYRING_USERNAME = "credential"
KEYRING_SERVICES = {
    "GARMIN_EMAIL": "TITAN_GARMIN_EMAIL",
    "GARMIN_PASSWORD": "TITAN_GARMIN_PASSWORD",
    "TELEGRAM_BOT_TOKEN": "TITAN_TELEGRAM_TOKEN",
}

_log = logging.getLogger(__name__)


def _credential_storage_event(backend: str) -> None:
    payload = {
        "flow": "setup_wizard",
        "action": "credential_storage_backend_selected",
        "backend": backend,
    }
    _log.info(json.dumps(payload, default=str))


def _load_keyring_module():
    if os.getenv(KEYRING_ENV_FLAG) != "1":
        return None
    try:
        return importlib.import_module("keyring")
    except ImportError:
        return None


def _banner():
    print("""
╔══════════════════════════════════════════════════════════════╗
║          TITAN v51 – FIRST RUN SETUP WIZARD               ║
║  Εισαγωγή credentials (αποθηκεύονται τοπικά, ΟΧΙ στο git) ║
╚══════════════════════════════════════════════════════════════╝
""")


def credentials_exist() -> bool:
    """Check if credentials are already configured."""
    # Check .env file
    if ENV_PATH.exists():
        text = ENV_PATH.read_text()
        if "GARMIN_EMAIL=" in text and "TELEGRAM_BOT_TOKEN=" in text:
            lines = {line.split("=")[0]: line.split("=", 1)[1].strip()
                     for line in text.splitlines() if "=" in line and not line.startswith("#")}
            if (lines.get("GARMIN_EMAIL","") and
                lines.get("GARMIN_PASSWORD","") and
                lines.get("TELEGRAM_BOT_TOKEN","")):
                return True
    _load_keyring_credentials()
    # Check env vars
    return bool(
        os.getenv("GARMIN_EMAIL") and
        os.getenv("GARMIN_PASSWORD") and
        os.getenv("TELEGRAM_BOT_TOKEN")
    )


def load_env_file():
    """Load .env file into os.environ."""
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())
    _load_keyring_credentials()


def _load_keyring_credentials() -> None:
    keyring = _load_keyring_module()
    if not keyring:
        return
    for env_key, service_name in KEYRING_SERVICES.items():
        value = keyring.get_password(service_name, KEYRING_USERNAME)
        if value:
            os.environ.setdefault(env_key, value)


def run_setup_wizard() -> dict:
    """Interactive setup wizard. Returns dict with credentials."""
    _banner()

    print("Για να λειτουργήσει το TITAN χρειάζεσαι:\n"
          "  1. Garmin Connect account\n"
          "  2. Telegram Bot (από @BotFather)\n"
          "  3. OpenWeatherMap API key (δωρεάν)\n\n"
          "Πάτα Enter για να προχωρήσεις σε κάθε ερώτηση.\n")

    creds = {}

    # ── Garmin ──────────────────────────────────────────────────────────
    print("━━━  GARMIN CONNECT  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    while True:
        garmin_email = input("  Email Garmin: ").strip()
        if EMAIL_REGEX.fullmatch(garmin_email):
            creds["GARMIN_EMAIL"] = garmin_email
            break
        print("  ⚠️  Μη έγκυρο email. Χρησιμοποίησε μορφή name@example.com.")


    creds["GARMIN_PASSWORD"] = getpass.getpass("  Password (κρυφό): ")

    # ── Telegram ─────────────────────────────────────────────────────────
    print("\n━━━  TELEGRAM BOT  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Πήγαινε στο @BotFather → /newbot → Πάρε το token")
    while True:
        token = input("  Bot Token: ").strip()
        if ":" in token and len(token) >= 20:
            creds["TELEGRAM_BOT_TOKEN"] = token
            break
        print("  ⚠️  Token άκυρο: ελάχιστο μήκος 20 και μορφή NNNNNNNN:ΑΛΦΑΡΙΘΜΗΤΙΚΟ")
    print("  Πήγαινε στο @userinfobot → Πάρε το Chat ID σου")
    while True:
        chat_raw = input("  Chat ID (αριθμός): ").strip()
        if chat_raw.lstrip("-").isdigit():
            creds["TELEGRAM_CHAT_ID"] = str(int(chat_raw))
            break
        print("  ⚠️  Το Chat ID πρέπει να είναι αριθμός. Δοκίμασε ξανά.")

    # ── Weather ──────────────────────────────────────────────────────────
    print("\n━━━  WEATHER API (openweathermap.org)  ━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Δωρεάν εγγραφή → API keys → Πάρε το key")

    while True:
        weather_key = input("  API Key: ").strip()
        if len(weather_key) >= 16:
            creds["WEATHER_API_KEY"] = weather_key
            break
        print("  ⚠️  API key πολύ μικρό. Ελάχιστο μήκος: 16 χαρακτήρες.")

    while True:
        location = input("  Τοποθεσία (π.χ. Athens,GR): ").strip() or "Athens,GR"
        if LOCATION_REGEX.fullmatch(location):
            creds["WEATHER_LOCATION"] = location
            break
        print("  ⚠️  Μη έγκυρη τοποθεσία. Χρησιμοποίησε μορφή City,CC (π.χ. Athens,GR).")


    # ── Save ─────────────────────────────────────────────────────────────
    backend = _save_credentials(creds)
    load_env_file()
    destination = "keyring" if backend == "keyring" else ".env"
    print(f"\n✅ Credentials αποθηκεύτηκαν στο {destination}\n")
    return creds


def _save_credentials(creds: dict) -> str:
    keyring = _load_keyring_module()
    if keyring:
        _save_keyring_credentials(creds, keyring)
        env_only = {k: v for k, v in creds.items() if k not in KEYRING_SERVICES}
        _save_env(env_only)
        _credential_storage_event("keyring")
        return "keyring"

    _save_env(creds)
    _credential_storage_event("env_file")
    return "env_file"


def _save_keyring_credentials(creds: dict, keyring) -> None:
    for env_key, service_name in KEYRING_SERVICES.items():
        keyring.set_password(service_name, KEYRING_USERNAME, creds[env_key])


def _save_env(creds: dict):
    lines = ["# TITAN v51 – Auto-generated credentials", "# ΜΗΝ κοινοποιήσεις αυτό το αρχείο!\n"]
    for k, v in creds.items():
        value = str(v).replace("\n", "").replace("\r", "")
        lines.append(f"{k}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n")
    ENV_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)
    if os.name == "nt":
        print("  ⚠️  Windows limitation: .env file permissions could not be restricted automatically.")
        print("     Verify .env access manually if this machine is shared.")


def _save_athlete_profile_to_env(changes: dict) -> None:
    """Update or append ATHLETE_* / TRAINING_* keys in the .env file.

    Reads the existing .env, replaces lines whose key appears in *changes*,
    and appends any key that is not already present.  All other lines
    (credentials, comments) are preserved untouched.
    """
    existing_lines: list[str] = ENV_PATH.read_text().splitlines() if ENV_PATH.exists() else []
    updated: set[str] = set()
    result: list[str] = []
    for line in existing_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in changes:
                value = str(changes[key]).replace("\n", "").replace("\r", "")
                result.append(f"{key}={value}")
                updated.add(key)
                continue
        result.append(line)
    for key, value in changes.items():
        if key not in updated:
            value = str(value).replace("\n", "").replace("\r", "")
            result.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(result) + "\n")


def ensure_credentials() -> bool:
    """
    Called at startup.
    If credentials exist → load them → return True.
    If not → run wizard → return True/False.
    """
    load_env_file()
    # credentials_exist() re-reads the file only when env vars are absent
    if os.getenv("GARMIN_EMAIL") and os.getenv("GARMIN_PASSWORD") and os.getenv("TELEGRAM_BOT_TOKEN"):
        return True
    if credentials_exist():
        return True
    print("\n🔑 Δεν βρέθηκαν credentials. Ξεκινώ setup wizard...\n")
    try:
        run_setup_wizard()
        return credentials_exist()
    except KeyboardInterrupt:
        print("\n\n❌ Setup ακυρώθηκε.")
        return False
