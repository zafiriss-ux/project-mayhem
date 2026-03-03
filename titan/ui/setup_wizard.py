"""
TITAN First-Run Setup Wizard

Interactive credential input at startup.
Saves to config_secrets.py (excluded from git).
"""

import getpass
import os
import re
import stat
from pathlib import Path

SECRETS_PATH = Path(__file__).parent.parent.parent / "config_secrets.py"
ENV_PATH     = Path(__file__).parent.parent.parent / ".env"
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
LOCATION_REGEX = re.compile(r"^[A-Za-zÀ-ÿ\s.'-]+,[A-Za-z]{2}$")


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

    email = input("  Email Garmin: ").strip()
    if "@" not in email or "." not in email.split("@", 1)[-1]:
        print("  ⚠️  Email μοιάζει άκυρο (αναμένεται μορφή user@example.com)")
    creds["GARMIN_EMAIL"]    = email

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

    api_key = input("  API Key: ").strip()
    if len(api_key) < 20:
        print("  ⚠️  API key μοιάζει άκυρο (OpenWeatherMap keys είναι 32 χαρακτήρες)")
    creds["WEATHER_API_KEY"]  = api_key
    creds["WEATHER_LOCATION"] = input("  Τοποθεσία (π.χ. Athens,GR): ").strip() or "Athens,GR"

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
    _save_env(creds)
    load_env_file()
    print("\n✅ Credentials αποθηκεύτηκαν στο .env\n")
    return creds


def _save_env(creds: dict):
    lines = ["# TITAN v51 – Auto-generated credentials", "# ΜΗΝ κοινοποιήσεις αυτό το αρχείο!\n"]
    for k, v in creds.items():
        value = str(v).replace("\n", "").replace("\r", "")
        lines.append(f"{k}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n")
    ENV_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)
    if os.name == "nt":
        print(
            "  ⚠️  Windows: τα permissions του .env δεν εφαρμόζονται αυτόματα.\n"
            "  Προστάτεψε το χειροκίνητα: Ιδιότητες → Ασφάλεια → αφαίρεσε άλλους χρήστες."
        )
    if os.name == "nt":
        print("  ⚠️  Windows limitation: .env file permissions could not be restricted automatically.")
        print("     Verify .env access manually if this machine is shared.")
    else:
        ENV_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)

    # Also add to .gitignore if not already there
    gitignore = Path(__file__).parent.parent.parent / ".gitignore"
    existing = gitignore.read_text() if gitignore.exists() else ""
    additions = []
    for entry in [".env", "config_secrets.py", "data/database/", "data/logs/"]:
        if entry not in existing:
            additions.append(entry)
    if additions:
        with gitignore.open("a") as f:
            f.write("\n# TITAN secrets\n" + "\n".join(additions) + "\n")


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
