# TITAN OS v5.8.0 — Closed-Loop Sovereign Training Intelligence

🏃‍♂️ **Αυτόνομο Σύστημα Προπόνησης με Επιστημονική Νοημοσύνη**

> **Απαιτείται Python ≥ 3.12.** Για παραγωγή, ο προτεινόμενος τρόπος είναι το Docker (βλ. παρακάτω).

## 🎯 Τι Κάνει το TITAN

### 📊 **Αυτόματη Συλλογή Δεδομένων**
- ✅ Συγχρονίζει με Garmin Connect (activities, βάρος, ύπνος, HRV)
- ✅ Λαμβάνει καιρικά δεδομένα από το Open-Meteo (ωριαία πρόγνωση 48 ωρών, χωρίς API key)
- ✅ Παρακολουθεί όλες τις μετρικές προπόνησης

### 🧠 **Έξυπνη Ανάλυση**
- ✅ Αναλύει το γαλακτικό κατώφλι (lactate threshold) από drift patterns
- ✅ Υπολογίζει HRV-guided συστάσεις ανάκαμψης
- ✅ Παρακολουθεί Training Stress Balance (CTL/ATL/TSB)
- ✅ Προβλέπει κίνδυνο τραυματισμού (ACWR monitoring)
- ✅ Κάθε σύσταση περνά από governance gates (hard stops) πριν φτάσει σε σένα

### 📅 **Εβδομαδιαίο Πλάνο Προπόνησης**
- ✅ Βασισμένο σε lactate threshold, drift analysis, HRV trends
- ✅ Προσαρμόζεται στην τρέχουσα κατάσταση ανάκαμψης
- ✅ Λαμβάνει υπόψη την πρόγνωση καιρού

### ⏰ **Βέλτιστη Ώρα Τρεξίματος**
- ✅ Υπολογίζει την καλύτερη ώρα κάθε μέρα
- ✅ Αναλύει dew point, θερμοκρασία, άνεμο
- ✅ Προσαρμόζεται στον τύπο προπόνησης (INTERVALS vs LONG_RUN) και στην κόπωση (TSB)

### 🍽 **Διατροφική Βελτιστοποίηση**
- ✅ Παρακολουθεί την τάση βάρους από Garmin
- ✅ Υπολογίζει carbs/protein/fat βάσει φάσης προπόνησης (Burke, Jeukendrup protocols)
- ✅ Προειδοποιεί για RED-S (ενεργειακή ανεπάρκεια)

### 📱 **Telegram**
- ✅ Πρωινό μήνυμα στις **07:00 UTC** με το σημερινό workout και τη βέλτιστη ώρα
- ✅ Εβδομαδιαίο πλάνο την **Κυριακή στις 20:00 UTC** (στην τοπική λειτουργία, βλ. «Τι τρέχει πού»)
- ✅ Προειδοποιήσεις ανάκαμψης

Όλες οι ώρες είναι σε UTC (07:00 UTC = 10:00 ώρα Ελλάδας το καλοκαίρι, 09:00 τον χειμώνα).

## 🏗 Αρχιτεκτονική

```
titan/
├── api/             # FastAPI (auth, coach/athlete routes) — container titan-api
├── config/          # Ρυθμίσεις (settings.py) και safety thresholds
├── core/            # Athlete profile, database, persistence, schema
├── features/        # Weekly planner, optimal time, nutrition
├── integrations/    # Garmin, Weather (Open-Meteo), Telegram, biometric routing
├── observability/   # Structured metrics
├── orchestration/   # DailyCoach, coaching pipeline, engine registry, scheduler
├── science/         # Επιστημονικές μηχανές (HRV, TSB, ACWR, lactate, drift, governance, ...)
├── ui/              # Μενού και setup wizard της τοπικής λειτουργίας
├── utils/           # Βοηθητικά (math core)
├── worker/          # Background worker — container titan-worker
└── main.py          # Entry point της τοπικής (interactive) λειτουργίας
```

Αναλυτικά, με κάθε module: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## 🚀 Εγκατάσταση

Υπάρχουν δύο τρόποι. Έτοιμο Windows `.exe` / GitHub Release δεν υπάρχει ακόμη (προγραμματίζεται).

### Α. Docker (προτεινόμενο για 24/7 λειτουργία)

```bash
git clone https://github.com/zafiriss-ux/project-mayhem.git
cd project-mayhem
cp .env.example .env      # συμπλήρωσε τα credentials
docker compose up --build -d
```

- `titan-api`: FastAPI στο `http://localhost:8000` (readiness: `GET /readyz` → 200)
- `titan-worker`: τρέχει κάθε μέρα στις 07:00 UTC την πρωινή ρουτίνα (Garmin sync, καιρός, Telegram) και ένα ημερήσιο backup της βάσης
- Βάση: `/data/titan_core.db` στο volume `titan-data`
- Backups: ελεγμένα ημερήσια αντίγραφα στο ξεχωριστό volume `titan-backups` (7 ημερήσια + 4 εβδομαδιαία)

Λεπτομέρειες: [`docs/runbooks/docker-deploy.md`](docs/runbooks/docker-deploy.md). Επαναφορά και έλεγχος αντιγράφων: [`docs/RUNBOOK_DR.md`](docs/RUNBOOK_DR.md). Εκδόσεις με tag, εικόνες στο `ghcr.io` και επιστροφή σε προηγούμενη έκδοση: [`docs/RUNBOOK_ROLLBACK.md`](docs/RUNBOOK_ROLLBACK.md).

### Β. Τοπικά με Python (Windows / Linux / macOS)

```bash
git clone https://github.com/zafiriss-ux/project-mayhem.git
cd project-mayhem
python --version                  # πρέπει να δείχνει 3.12 ή νεότερη
pip install -r requirements.txt
python launcher/main.py
```

Ο launcher:
- ελέγχει το περιβάλλον (Python, δίσκος, φάκελος δεδομένων),
- τρέχει τον οδηγό πρώτης ρύθμισης αν λείπει το `.env`,
- φτιάχνει τη βάση στο `~/Documents/TITAN/titan_core.db`,
- ξεκινά το TITAN.

Εναλλακτικά, χωρίς launcher: `python -m titan` (ή `python main.py`). Τότε τα credentials διαβάζονται από το `.env` στη ρίζα του repo ή από μεταβλητές περιβάλλοντος, και αν λείπουν ανοίγει ο οδηγός ρύθμισης.

Πλήρης οδηγός πρώτης ρύθμισης (Garmin, Telegram, καιρός, δοκιμές, προβλήματα): [`docs/DEPLOYMENT_GUIDE.md`](docs/DEPLOYMENT_GUIDE.md).

### Τι τρέχει πού

| | Docker (`titan-worker`) | Τοπικά (`python -m titan` / launcher) |
|---|---|---|
| Πρωινή ρουτίνα 07:00 UTC | ✅ | ✅ |
| Εβδομαδιαίο πλάνο Κυριακή 20:00 UTC | — | ✅ |
| Garmin sync κάθε 6 ώρες | — (sync μέσα στην πρωινή ρουτίνα) | ✅ |
| Εντολές Telegram (polling) | — | ✅ |
| Ημερήσιο backup βάσης | ✅ | — |
| Interactive μενού | — | ✅ |

### Ρυθμίσεις (.env)

| Πού | Πότε |
|---|---|
| `~/Documents/TITAN/.env` | Το γράφει και το διαβάζει ο launcher (`python launcher/main.py`) |
| `.env` στη ρίζα του repo | Για `python -m titan` και για το Docker (`docker compose`) |

> **Windows:** το TITAN δεν μπορεί να επιβάλει δικαιώματα τύπου Unix `0600` στο `.env`. Αν ο υπολογιστής είναι κοινόχρηστος, έλεγξε τα ACL του φακέλου.

Βασικά κλειδιά (πλήρες παράδειγμα στο [`.env.example`](.env.example)):

```bash
# Garmin Connect
GARMIN_EMAIL=your_email@example.com
GARMIN_PASSWORD=your_password
TITAN_GARTH_TOKEN_KEY=           # κλειδί Fernet για κρυπτογράφηση του Garmin token (απαραίτητο σε παραγωγή)

# Telegram Bot
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN_HERE   # από τον @BotFather
TELEGRAM_CHAT_ID=123456789               # από τον @userinfobot

# Καιρός (Open-Meteo, χωρίς API key)
WEATHER_LOCATION=Athens,GR

# Αθλητής
ATHLETE_MAX_HR=185

# Προαιρετικά (εμφανίζονται οι προεπιλογές)
# TITAN_DATA_DIR=/data          # φάκελος βάσης στο Docker
# TITAN_LOG_PATH=titan.log
# TITAN_ML_KILL_SWITCH=1        # 1 = ML μοντέλα μόνο σε shadow mode (ασφαλής προεπιλογή)

# Phase 7 ML promotion control
# Η προεπιλογή (1) είναι η ασφαλής. Βάλε 0 μόνο για athlete-facing Stage 1+ deployment,
# αφού εγκριθούν τα promotion gates και ενημερωθούν τα ADR evidence (ADR-0014):
# TITAN_ML_KILL_SWITCH=0
```

Όλες οι ρυθμίσεις που διαβάζει ο κώδικας: [`titan/config/settings.py`](titan/config/settings.py).

### Troubleshooting εγκατάστασης

**"Python version 3.X is not supported"** → Εγκατάστησε Python 3.12+ από το [python.org](https://www.python.org/downloads/).

**"Cannot write to data directory"** → Διάλεξε άλλο φάκελο ή δώσε δικαιώματα εγγραφής.

**"Garmin authentication failed"** → Βλ. [`docs/runbooks/garmin-sync-failure.md`](docs/runbooks/garmin-sync-failure.md).

**"Database is corrupted"** → Βλ. [`docs/runbooks/database-recovery.md`](docs/runbooks/database-recovery.md).

Logs του launcher: `~/Documents/TITAN/logs/launcher_YYYY-MM-DD.log`. Log του TITAN: `titan.log` (ή ό,τι ορίζει το `TITAN_LOG_PATH`).

## 📋 Χρήση

### Καθημερινή Ροή
**Κάθε πρωί στις 07:00 UTC** (παράδειγμα μηνύματος):
```
📱 Telegram Message:
🌅 GOOD MORNING!
Monday, February 16, 2026

🏃 Today's Workout:
TEMPO - 12 km

⏰ Optimal Running Time:
06:30 (Dew point: 13.2°C, Comfortable conditions)

💊 Recovery Status:
• HRV: ✅ NORMAL (48.5 → Proceed)
• Sleep: 8/10
• Readiness: 85/100

🍽 Nutrition Focus:
450g carbs, 135g protein
```

### Εβδομαδιαία Ροή (τοπική λειτουργία)
**Κάθε Κυριακή στις 20:00 UTC** (παράδειγμα μηνύματος):
```
📱 Telegram Message:
🎯 WEEKLY TRAINING PLAN
Week of: 2026-02-17

📊 Training Summary:
• Total Volume: 77 km
• Quality Sessions: 2
• Easy Days: 4
• Rest Days: 1

💡 Key Insights:
• Lactate Threshold: 168 bpm
• Avg Drift: 3.2%
• HRV Baseline: 48.5
• TSB Status: 💪 PRODUCTIVE OVERLOAD

📅 Daily Breakdown:
[Detailed 7-day plan...]
```

## 🔧 Ρύθμιση Telegram Bot

### 1. Δημιουργία Bot
```
1. Άνοιξε το Telegram και μίλησε με @BotFather
2. Στείλε /newbot
3. Ακολούθησε τις οδηγίες
4. Κράτα το Bot Token
```

### 2. Εύρεση Chat ID
```
1. Μίλησε με το @userinfobot
2. Θα σου δώσει το Chat ID σου
```

### 3. Προσθήκη στο .env
```bash
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN_HERE
TELEGRAM_CHAT_ID=123456789
```

## 📊 Βασικές Μετρικές

Οι τιμές είναι αυτές του κώδικα (`titan/science/tsb_engine.py`, `titan/config/thresholds.py`, `titan/integrations/weather_api.py`).

### Training Stress Balance (TSB)
- **> +25**: ⚠️ σοβαρή αποπροπόνηση (detraining)
- **+15 έως +25**: αποπροπόνηση
- **+5 έως +15**: 🟢 FRESH
- **−10 έως +5**: 🎯 RACE FORM
- **−30 έως −10**: 💪 PRODUCTIVE OVERLOAD — χτίζεις fitness
- **−50 έως −30**: ⚠️ FUNCTIONAL OVERREACH — χρειάζεται ανάκαμψη
- **< −50**: 🛑 OVERTRAINED

### ACWR (Injury Risk)
- **1.0–1.3**: ✅ SWEET SPOT — βέλτιστη προσαρμογή
- **1.3–1.5**: ⚠️ MODERATE RISK
- **> 1.5**: 🛑 HIGH INJURY RISK

### HRV Status
- **≥ Baseline**: ✅ Proceed with plan
- **< Baseline − 1 SD**: ⚠️ Downgrade intensity
- **< Baseline − 2 SD**: 🛑 Force rest

### Dew Point Guide
- **≤ 8°C**: 🟪 DRY / COLD
- **8–12°C**: 🟦 PLEASANT
- **12–15°C**: 🟩 COMFORTABLE
- **15–18°C**: 🟨 STICKY
- **18–21°C**: 🟧 UNCOMFORTABLE — μείωσε τον ρυθμό 10–15 sec/km
- **21–24°C**: 🟥 OPPRESSIVE — μείωσε την ένταση 20–30%
- **> 24°C**: 🔥 EXTREME — απόφυγε την προπόνηση

## 🧪 Για προγραμματιστές

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest --no-cov -q     # όλα τα τεστ (φάκελος tests/)
bash scripts/titan_ci.sh         # το πλήρες CI τοπικά (gates G1–G6)
```

Κανόνες συνεισφοράς και governance: [`AGENTS.md`](AGENTS.md), [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md). Πρόοδος του refactor: [`PROGRESS.md`](PROGRESS.md).

## 📚 Επιστημονική Τεκμηρίωση

Όλες οι μηχανές βασίζονται σε peer-reviewed έρευνα:

- **HRV**: Kiviniemi 2007, Plews 2013
- **TSB**: Banister 1975, Coggan 2010
- **ACWR**: Gabbett 2016 (28,000+ athletes)
- **Nutrition**: Burke et al. 2011, Jeukendrup 2014
- **Lactate**: Seiler 2007, San-Millan 2017

## 🐛 Troubleshooting

### Garmin Sync Failed
```bash
# Έλεγξε credentials
echo $GARMIN_EMAIL
echo $GARMIN_PASSWORD

# Δοκίμασε manual login
python -c "from titan.integrations.garmin_sync import GarminSync; g = GarminSync(); g.connect()"
```
Αναλυτικά: [`docs/runbooks/garmin-sync-failure.md`](docs/runbooks/garmin-sync-failure.md).

### Telegram Not Sending
```bash
# Έλεγξε bot token
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getMe"

# Έλεγξε chat ID
echo $TELEGRAM_CHAT_ID
```

### Weather API Issues
```bash
# TITAN χρησιμοποιεί Open-Meteo (δωρεάν, χωρίς API key)
# Test geocoding API
curl "https://geocoding-api.open-meteo.com/v1/search?name=Athens&count=1"

# Test forecast API
curl "https://api.open-meteo.com/v1/forecast?latitude=37.98&longitude=23.73&current=temperature_2m"
```

## 📖 Αναλυτικό Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — αρχιτεκτονική, modules, ροές δεδομένων
- [`docs/DEPLOYMENT_GUIDE.md`](docs/DEPLOYMENT_GUIDE.md) — εγκατάσταση και πρώτη ρύθμιση
- [`docs/runbooks/`](docs/runbooks/) — Docker, ανάκτηση βάσης, Garmin, governance
- [`docs/ROADMAP.MD`](docs/ROADMAP.MD) — φάσεις και τι ακολουθεί
- [`docs/adr/`](docs/adr/) — αρχιτεκτονικές αποφάσεις (ADR)
- [`titan/QUICK_REFERENCE.md`](titan/QUICK_REFERENCE.md) — developer quick reference

## 📄 Άδεια

Δεν υπάρχει ακόμη αρχείο άδειας (`LICENSE`) στο repo.

## 👨‍💻 Author

TITAN OS v5.8.0 — Developed with Claude Code
