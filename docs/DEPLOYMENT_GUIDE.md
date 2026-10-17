> ⚠️ CANONICAL DEPLOYMENT: Docker.
> See docs/runbooks/docker-deploy.md
> This guide describes LOCAL DEV ONLY.
> Database path: titan_core.db
> (NOT titan.db — that file is stale)

# TITAN OS — Local Development Guide

For the canonical Docker deployment, see [`docs/runbooks/docker-deploy.md`](runbooks/docker-deploy.md).

## Quick Start (Local Dev Only)

Requires Python 3.12 or newer.

```bash
pip install -r requirements.txt
python launcher/main.py
```

For development (tests, lint, CI gates):

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest --no-cov -q
bash scripts/titan_ci.sh
```

## Database

- Docker: `/data/titan_core.db`
- Local: `~/Documents/TITAN/titan_core.db`
- **NEVER** use `titan.db` — that file is stale and must not be referenced in any runbook or script.

Backups and restore: [`docs/runbooks/database-recovery.md`](runbooks/database-recovery.md). The Docker worker also takes a daily backup (`/backups/titan_YYYY-MM-DD.db` on the `titan-backups` volume, 7 daily + 4 weekly; see [`RUNBOOK_DR.md`](RUNBOOK_DR.md)).

---

# Οδηγός πρώτης ρύθμισης (τοπικά, στα ελληνικά)

Συγχωνεύει τον παλιό `DEPLOYMENT_GUIDE.md` της ρίζας, διορθωμένο ώστε να ταιριάζει με τον κώδικα της έκδοσης 5.8.0.

## 1. Εγκατάσταση

```bash
git clone https://github.com/zafiriss-ux/project-mayhem.git
cd project-mayhem

python3 -m venv venv
source venv/bin/activate        # Linux/macOS
# ή
.\venv\Scripts\activate         # Windows

pip install --upgrade pip
pip install -r requirements.txt

cp .env.example .env            # μετά συμπλήρωσε τα credentials (βλ. παρακάτω)
```

Πού διαβάζονται οι ρυθμίσεις:

| Τρόπος εκκίνησης | Αρχείο ρυθμίσεων |
|---|---|
| `python launcher/main.py` | `~/Documents/TITAN/.env` (το φτιάχνει ο οδηγός του launcher) |
| `python -m titan` ή `python main.py` | `.env` στη ρίζα του repo (ή μεταβλητές περιβάλλοντος) |
| `docker compose up` | `.env` στη ρίζα του repo |

Τα παρακάτω snippets δοκιμής διαβάζουν μόνο μεταβλητές περιβάλλοντος. Φόρτωσε πρώτα το `.env` στο shell:

```bash
set -a; source .env; set +a     # Linux/macOS
```

## 2. Garmin

Στο `.env`:
```bash
GARMIN_EMAIL=your_email@example.com
GARMIN_PASSWORD=your_password
TITAN_GARTH_TOKEN_KEY=          # κλειδί Fernet, απαραίτητο σε παραγωγή
```

Δημιουργία κλειδιού για το `TITAN_GARTH_TOKEN_KEY`:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Δοκιμή σύνδεσης:
```bash
python -c "from titan.integrations.garmin_sync import GarminSync; g = GarminSync(); print('✅ Connected' if g.connect() else '❌ Failed')"
```

Άλλοι αθλητές (Φάση 4, ADR-0067 D9): ο καθένας έχει δικό του token στο
`<data>/garmin/<athlete_id>/.garth_token`, κρυπτογραφημένο με ένα κλειδί Fernet που ζει σε αρχείο
**έξω** από τον φάκελο δεδομένων:
```bash
TITAN_TOKEN_KEY_FILE=/etc/titan/athlete_token.key   # mode 0600, όχι μέσα στο TITAN_DATA_DIR
```
Αν η μεταβλητή λείπει, το αρχείο είναι μέσα στα δεδομένα, είναι αναγνώσιμο από άλλους ή δεν είναι
έγκυρο κλειδί, κανένας άλλος αθλητής δεν συγχρονίζεται και το token του δεν σβήνεται. Ο owner δεν
επηρεάζεται. Το κλειδί το γράφει μία φορά το `python scripts/athletes.py new-key`. Στο Docker το
`docker-compose.yml` βάζει το κλειδί και το αρχείο διαγραφών στο volume `titan-secrets` (`/secrets`).

Πρώτος συγχρονισμός:
```bash
python << 'EOF'
from titan.integrations.garmin_sync import GarminSync

garmin = GarminSync()
if garmin.connect():
    data = garmin.sync_all()
    print(f"✅ Synced {len(data['activities'])} activities")
    print(f"✅ Synced {len(data['weight'])} weight entries")
    print(f"✅ Synced {len(data['sleep'])} sleep sessions")
    print(f"✅ Synced {len(data['hrv'])} HRV measurements")
EOF
```

- ⚠️ Το Garmin Connect έχει rate limits. Αν αποτύχει, περίμενε πριν ξαναδοκιμάσεις.
- ⚠️ Μην κοινοποιήσεις το `.env`.

## 3. Telegram

1. Στο Telegram, μίλησε με τον `@BotFather`, στείλε `/newbot` και κράτα το **Bot Token**.
2. Μίλησε με τον `@userinfobot` και στείλε `/start` για να πάρεις το **Chat ID** σου.
3. Στο `.env`:
   ```bash
   TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN_HERE
   TELEGRAM_CHAT_ID=123456789
   ```
4. Δοκιμή:
   ```bash
   python -c "from titan.integrations.telegram_bot import TitanTelegramBot; print('✅ Sent' if TitanTelegramBot().send_message('🎯 TITAN test') else '❌ Failed')"
   ```

Άλλοι αθλητές (Φάση 4, ADR-0067 D10): το ίδιο bot, με ένα ιδιωτικό chat ο καθένας, δεμένο στο
`athlete_accounts.telegram_chat_id` (ένα chat σε έναν αθλητή, ποτέ το chat του owner). Ο αθλητής
έχει μόνο `/consent` (δείχνει το κείμενο συγκατάθεσης, `docs/consent/v1.md`), `/agree v1`
(καταγράφει τη συγκατάθεσή του σε αυτή την έκδοση), `/sync` (συγχρονίζει μόνο τα δικά του δεδομένα
Garmin) και `/stop` (ανακαλεί τη συγκατάθεσή του)· τα `/start` και `/help` δείχνουν αυτή τη λίστα, και
κάθε άλλη εντολή μένει χωρίς απάντηση, όπως και κάθε chat που δεν έχει δεθεί. Χωρίς συγκατάθεση δεν τρέχει τίποτα για τον αθλητή (ADR-0067 D4).
Το κείμενο v1 είναι προσχέδιο: δεν χρησιμοποιείται για πραγματικό αθλητή πριν το δει δικηγόρος.
Δεν τρέχει δεύτερο bot: τα chat των αθλητών τα ακούει η ίδια διεργασία με τον owner, δηλαδή το
`python -m titan`. Ο `titan-worker` του Docker μόνο στέλνει· δεν ακούει εντολές.

Διαχείριση αθλητών (Φάση 4, ADR-0067 D2, D6, D9, D-097), στο μηχάνημα της ρουτίνας:
```bash
TITAN_DELETION_RECORD_FILE=/etc/titan/deletions.jsonl   # έξω από TITAN_DATA_DIR και TITAN_BACKUP_DIR

python scripts/athletes.py add --name "Maria" --profile maria.json --chat 123456789
python scripts/athletes.py relogin a-1234abcd       # ο αθλητής γράφει ο ίδιος τον κωδικό· δεν κρατιέται
python scripts/athletes.py list
python scripts/athletes.py export a-1234abcd --out a-1234abcd.json   # αρχείο 0600
python scripts/athletes.py remove a-1234abcd        # ζητά να γράψεις το id
```
Το `maria.json` έχει όλα τα πεδία του `athlete_profiles` (ημερομηνία γέννησης, φύλο, βάρος, ύψος,
μέγιστο και κατωφλιακό ΚΣ, φάση, στόχος, πόλη, χώρα). Μετά το `add` και το `relogin` ο αθλητής
στέλνει `/consent` και `/agree v1` στο δικό του chat. Χωρίς `TITAN_DELETION_RECORD_FILE` η διαγραφή
απορρίπτεται. Ο worker σβήνει μόνος του τον αθλητή 30 ημέρες μετά το `/stop`. Στο Docker:
`docker compose exec titan-worker python scripts/athletes.py list`.

Με `TITAN_MULTI_ATHLETE=1` ο worker τρέχει κάθε πρωί από τις 07:00 UTC όλους τους έτοιμους
αθλητές, τον owner πρώτο, τον καθένα σε δική του διεργασία με όριο `WORKER_ROUTINE_BUDGET_S`
(ADR-0067 D8, D-099). Όποιος δεν είναι έτοιμος (συγκατάθεση, προφίλ, Garmin, Telegram) δεν τρέχει,
και ο owner παίρνει ένα μήνυμα την ημέρα με το γιατί. Χωρίς τη μεταβλητή τρέχει μόνο ο owner.

Βήμα βήμα, και τι κάνεις όταν ένας αθλητής δεν πήρε μήνυμα ή έληξε το token του:
[`docs/runbooks/multi-athlete.md`](runbooks/multi-athlete.md).

## 4. Καιρός

Το TITAN χρησιμοποιεί το [Open-Meteo](https://open-meteo.com/): δωρεάν, χωρίς εγγραφή ή API key. Στο `.env` χρειάζεται μόνο η τοποθεσία:

```bash
WEATHER_LOCATION=Athens,GR
```

Δοκιμή:
```bash
python -c "from titan.integrations.weather_api import WeatherAPI; c = WeatherAPI().get_current_conditions(); print(f\"✅ {c['temp_c']}°C, dew point {c['dew_point']}°C\")"
```

## 5. Εκκίνηση

```bash
python launcher/main.py     # με έλεγχο περιβάλλοντος και οδηγό ρύθμισης
# ή
python -m titan             # κατευθείαν
```

Ανοίγει το interactive μενού του TITAN. Όσο τρέχει, προγραμματίζει:

- πρωινή ρουτίνα κάθε μέρα στις **07:00 UTC** (μήνυμα στο Telegram),
- εβδομαδιαίο πλάνο κάθε **Κυριακή στις 20:00 UTC**,
- Garmin sync κάθε 6 ώρες από την εκκίνηση,
- ενημέρωση καιρού κάθε ώρα και λήψη εντολών από το Telegram.

Στο Docker, ο `titan-worker` τρέχει μόνο την πρωινή ρουτίνα, το ημερήσιο backup και, για τους άλλους αθλητές, την επανάληψη των διαγραφών στην εκκίνηση και τη διαγραφή 30 ημέρες μετά το `/stop` (βλ. [`docs/runbooks/docker-deploy.md`](runbooks/docker-deploy.md)).

Logs: με τον launcher, `~/Documents/TITAN/logs/titan.log`· με `python -m titan`, `titan.log` στον τρέχοντα φάκελο (ή ό,τι ορίζει το `TITAN_LOG_PATH`). Του launcher: `~/Documents/TITAN/logs/launcher_YYYY-MM-DD.log`.

## 6. Χειροκίνητη εκτέλεση

Πρωινή ρουτίνα τώρα, με τα ίδια components που χρησιμοποιεί ο worker:
```bash
python -c "from titan.core.database import DatabaseManager; from titan.worker import _build_daily_coach; _build_daily_coach(DatabaseManager()).run_morning_routine()"
```

## 7. Προβλήματα και λύσεις

**Garmin connection failed**
```bash
echo $GARMIN_EMAIL              # υπάρχουν τα credentials στο περιβάλλον;
python -c "from titan.integrations.garmin_sync import GarminSync; GarminSync().connect()"
```
Αν φταίνε τα rate limits, περίμενε μία ώρα. Αναλυτικά: [`docs/runbooks/garmin-sync-failure.md`](runbooks/garmin-sync-failure.md).

**Δεν έρχονται μηνύματα στο Telegram**
```bash
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getMe"   # ισχύει το token;
echo $TELEGRAM_CHAT_ID
```

**Δεν ενημερώνεται ο καιρός**
```bash
echo $WEATHER_LOCATION
curl "https://geocoding-api.open-meteo.com/v1/search?name=Athens&count=1"
```

**Χαλασμένη βάση** → [`docs/runbooks/database-recovery.md`](runbooks/database-recovery.md).

## 8. Συντήρηση

- Ενημέρωση: `git pull`, μετά `pip install -r requirements.txt` και επανεκκίνηση.
- Έλεγχος πριν από ενημέρωση: `python system_check.py`.
- Backups: [`docs/runbooks/database-recovery.md`](runbooks/database-recovery.md).
