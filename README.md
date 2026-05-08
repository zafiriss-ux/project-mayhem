# TITAN OS v5.8.0 — Closed-Loop Sovereign Training Intelligence

🏃‍♂️ **Αυτόνομο Σύστημα Προπόνησης με Επιστημονική Νοημοσύνη**

> **Python ≥3.11 Required** — UTF-8 mode, tomllib stdlib, enhanced error messages

## 🎯 Τι Κάνει το TITAN

Το TITAN είναι ένα ολοκληρωμένο σύστημα προπονητικής νοημοσύνης που:

### 📊 **Αυτόματη Συλλογή Δεδομένων**
- ✅ Συγχρονίζει με Garmin Connect (activities, βάρος, ύπνος, HRV)
- ✅ Λαμβάνει καιρικά δεδομένα (ωριαία πρόγνωση 48 ωρών)
- ✅ Παρακολουθεί όλες τις μετρικές προπόνησης

### 🧠 **Έξυπνη Ανάλυση**
- ✅ Αναλύει το γαλακτικό κατώφλι (lactate threshold) από drift patterns
- ✅ Υπολογίζει HRV-guided συστάσεις ανάκαμψης
- ✅ Παρακολουθεί Training Stress Balance (CTL/ATL/TSB)
- ✅ Προβλέπει κίνδυνο τραυματισμού (ACWR monitoring)

### 📅 **Εβδομαδιαίο Πλάνο Προπόνησης**
- ✅ Δημιουργεί αυτόματα εβδομαδιαίο πλάνο κάθε Κυριακή
- ✅ Βασισμένο σε lactate threshold, drift analysis, HRV trends
- ✅ Προσαρμόζεται στην τρέχουσα κατάσταση ανάκαμψης
- ✅ Λαμβάνει υπόψη την πρόγνωση καιρού

### ⏰ **Βέλτιστη Ώρα Τρεξίματος**
- ✅ Υπολογίζει την καλύτερη ώρα κάθε μέρα
- ✅ Αναλύει dew point, θερμοκρασία, άνεμο
- ✅ Προσαρμόζεται στον τύπο προπόνησης (INTERVALS vs LONG_RUN)
- ✅ Λαμβάνει υπόψη την κόπωση (TSB status)

### 🍽 **Διατροφική Βελτιστοποίηση**
- ✅ Παρακολουθεί την τάση βάρους από Garmin
- ✅ Υπολογίζει carbs/protein/fat βάσει φάσης προπόνησης
- ✅ Επιστημονικά τεκμηριωμένο (Burke, Jeukendrup protocols)
- ✅ Προειδοποιεί για RED-S (ενεργειακή ανεπάρκεια)

### 📱 **Telegram Bot Notifications**
- ✅ Καθημερινό μήνυμα στις 07:00 με σημερινό workout + optimal time
- ✅ Εβδομαδιαίο πλάνο κάθε Κυριακή στις 20:00
- ✅ Post-run ανάλυση μετά από κάθε προπόνηση
- ✅ Προειδοποιήσεις ανάκαμψης

## 🏗 Αρχιτεκτονική

```
titan/
├── core/              # Βασική λειτουργικότητα (athlete, database, config)
├── science/           # Επιστημονικές μηχανές (HRV, TSB, ACWR, lactate, drift)
├── features/          # Χαρακτηριστικά (weekly planner, optimal time, nutrition)
├── integrations/      # Εξωτερικές ενοποιήσεις (Garmin, Weather, Telegram)
├── orchestration/     # Υψηλού επιπέδου ορχήστρωση (daily coach)
└── main.py           # Κύριο entry point
```

### Πλήρης Λίστα Modules

#### Core Modules (7)
1. `core/athlete.py` - UniversalAthleteProfile
2. `core/database.py` - DatabaseManager + SQLite
3. `core/equipment.py` - Shoe tracking
4. `core/periodization.py` - Training phases

#### Science Modules (15)
1. `science/hrv_engine.py` - HRV-guided training
2. `science/tsb_engine.py` - Training Stress Balance
3. `science/acwr_engine.py` - Injury prevention
4. `science/lactate_logic.py` - LT1/LT2 estimation
5. `science/drift_engine.py` - HR drift analysis
6. `science/glycogen_model.py` - Fuel management
7. `science/fatigue_engine.py` - Fatigue classification
8. `science/readiness_engine.py` - Daily readiness
9. Plus 7 more...

#### Feature Modules (8)
1. `features/weekly_planner.py` - **🆕 Εβδομαδιαίο πλάνο**
2. `features/optimal_time_calculator.py` - **🆕 Βέλτιστη ώρα**
3. `features/nutrition_optimizer.py` - **🆕 Διατροφή**
4. Plus 5 more...

#### Integration Modules (4)
1. `integrations/garmin_sync.py` - **🆕 Live Garmin API**
2. `integrations/weather_api.py` - **🆕 Weather + dew point**
3. `integrations/telegram_bot.py` - **🆕 Telegram notifications**
   _(Wearable data — heart rate, HRV, sleep, weight — flows through `garmin_sync.py`)_

## 🚀 Installation

### System Requirements

| Requirement | Minimum | Recommended | Why |
|------------|---------|-------------|-----|
| **Python** | **3.11.0** | 3.12+ | UTF-8 mode (PEP 686), tomllib stdlib, better errors |
| **OS** | Windows 10 | Windows 11 | Fully tested on Win10/11; Linux/macOS experimental |
| **RAM** | 512 MB | 1 GB | SQLite + science engines |
| **Disk** | 100 MB | 500 MB | Database + logs |

> ⚠️ **Python 3.11+ is mandatory.** Older versions are not supported.

---

### Option 1: One-Click Launcher (Beginners — Windows)

**Download pre-built executable:**
```
1. Go to Releases: https://github.com/zafiriss-ux/project-mayhem/releases
2. Download TITAN-v5.8.0-win64.zip
3. Unzip to Desktop or Documents
4. Double-click TITAN.exe
5. Follow setup wizard (Garmin, Telegram credentials)
6. Done! Check Telegram for morning briefing.
```

No Python installation needed — everything is bundled.

---

### Option 2: Python CLI (Advanced Users)

**1. Clone Repository**
```bash
git clone https://github.com/zafiriss-ux/project-mayhem.git
cd project-mayhem
```

**2. Verify Python Version**
```bash
python --version  # Must show 3.11.0 or higher
```

If you have Python <3.11, install from [python.org](https://www.python.org/downloads/).

**3. Install Dependencies**
```bash
pip install -r requirements.txt
```

**4. Run Launcher**
```bash
python launcher/main.py
```

The launcher will:
- Validate environment (Python, disk, data directory)
- Run first-time setup wizard (if `.env` missing)
- Create database at `~/Documents/TITAN/titan_core.db`
- Start TITAN kernel

**5. Alternative: Direct Kernel Mode (Power Users)**
```bash
python -m titan
```

Skips launcher validation. Use only if you've already configured `.env`.

---

### Configuration (.env)

The launcher wizard creates `.env` automatically. If configuring manually:

**Location:** `~/Documents/TITAN/.env` (Windows: `%USERPROFILE%\Documents\TITAN\.env`)

> **Windows note:** TITAN cannot enforce Unix-style `0600` permissions on `.env` under Windows. Review file/folder ACLs manually if the system is shared.

**Required Keys:**
```bash
# Garmin Connect
GARMIN_USERNAME=your_email@example.com
GARMIN_PASSWORD=your_password

# Telegram Bot
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN_HERE  # Get from @BotFather
TELEGRAM_CHAT_ID=123456789                   # Send /start to your bot

# OpenAI (Optional — for LLM coaching narratives)
OPENAI_API_KEY=sk-...

# Weather API — Open-Meteo (no key needed; leave blank or omit)
# WEATHER_API_KEY is ignored; Open-Meteo is free and requires no authentication.

# Phase 7 ML promotion control
# Default is safe/blocking (1). Set to 0 only for athlete-facing Stage 1+ deployments
# after promotion gates and ADR evidence updates are approved.
TITAN_ML_KILL_SWITCH=0
```

---

### Troubleshooting

**"Python version 3.X is not supported"**
→ Install Python 3.11+ from [python.org](https://www.python.org/downloads/)

**"Cannot write to data directory"**
→ Run as administrator or choose a different folder

**"Garmin authentication failed"**
→ Enable 2FA on Garmin Connect if required

**"Database is corrupted"**
→ Backup `~/Documents/TITAN/titan_core.db` and delete it. TITAN will create a fresh one.

Check logs at `~/Documents/TITAN/logs/launcher_YYYY-MM-DD.log` for detailed errors.

## 📋 Χρήση

### Πρώτη Εκκίνηση
Το TITAN θα:
1. Συνδεθεί στο Garmin και θα κάνει sync όλα τα δεδομένα
2. Θα αρχίσει να παρακολουθεί τον καιρό
3. Θα στείλει test μήνυμα στο Telegram
4. Θα προγραμματίσει τα καθημερινά/εβδομαδιαία tasks

### Καθημερινή Ροή
**Κάθε πρωί στις 07:00:**
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

### Εβδομαδιαία Ροή
**Κάθε Κυριακή στις 20:00:**
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

### Training Stress Balance (TSB)
- **+5 to +10**: 🎯 RACE FORM - Ιδανικό για αγώνα
- **-10 to +5**: 💪 PRODUCTIVE OVERLOAD - Χτίζεις fitness
- **< -30**: ⚠️ OVERREACH - Χρειάζεται ανάκαμψη

### ACWR (Injury Risk)
- **1.0-1.3**: ✅ SWEET SPOT - Βέλτιστη προσαρμογή
- **> 1.5**: 🛑 HIGH RISK - Κίνδυνος τραυματισμού

### HRV Status
- **≥ Baseline**: ✅ Proceed with plan
- **< Baseline - 1 SD**: ⚠️ Downgrade intensity
- **< Baseline - 2 SD**: 🛑 Force rest

### Dew Point Guide
- **< 12°C**: 🟩 COMFORTABLE
- **15-18°C**: 🟨 STICKY
- **> 21°C**: 🔥 OPPRESSIVE - Reduce pace

## 🧵 Background Threads

Το TITAN τρέχει 5 background threads:

1. **Garmin Sync** - Κάθε 6 ώρες
2. **Weather Update** - Κάθε 1 ώρα
3. **Telegram Bot Listener** - Συνεχώς
4. **Daily Coach** - Κάθε πρωί 07:00
5. **Weekly Planner** - Κυριακή 20:00

## 📚 Επιστημονική Τεκμηρίωση

Όλες οι μηχανές βασίζονται σε peer-reviewed έρευνα:

- **HRV**: Kiviniemi 2007, Plews 2013
- **TSB**: Banister 1975, Coggan 2010
- **ACWR**: Gabbett 2016 (28,000+ athletes)
- **Nutrition**: Burke et al. 2011, Jeukendrup 2014
- **Lactate**: Seiler 2007, San-Millan 2017

## 🔄 Μετάπτωση από v50

Το TITAN v51 διατηρεί **ΟΛΕΣ** τις 54 classes του v50:
- ✅ Όλες οι science engines μεταφέρθηκαν
- ✅ Όλες οι λειτουργίες διατηρήθηκαν
- ✅ Database schema συμβατό
- ✅ Προστέθηκαν νέες δυνατότητες

## 🆕 Επερχόμενες Αναβαθμίσεις

### Phase 5: ML Enhancement
- LSTM για πρόβλεψη performance
- Injury risk ML model
- Automated periodization

### Phase 6: Web UI
- Streamlit dashboard
- Interactive charts
- Training calendar

### Phase 7: Mobile App
- React Native app
- Push notifications
- GPS tracking

## 🐛 Troubleshooting

### Garmin Sync Failed
```bash
# Έλεγξε credentials
echo $GARMIN_EMAIL
echo $GARMIN_PASSWORD

# Δοκίμασε manual login
python -c "from titan.integrations.garmin_sync import GarminSync; g = GarminSync(); g.connect()"
```

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

- `ARCHITECTURE.md` - Αρχιτεκτονική σχεδίαση
- `titan/MIGRATION_CORE_MODULES.md` - Technical migration details
- `titan/QUICK_REFERENCE.md` - Developer quick reference

## 📄 License

MIT License - Ελεύθερο για προσωπική χρήση

## 👨‍💻 Author

TITAN v51.0 - Αναδομημένο σύστημα με πλήρη AI capabilities
Developed with Claude Code
