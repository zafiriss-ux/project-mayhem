# 🚀 TITAN v51 - Οδηγίες Εγκατάστασης και Χρήσης

## 📋 Περιεχόμενα

1. [Απαιτήσεις Συστήματος](#απαιτήσεις-συστήματος)
2. [Εγκατάσταση Βήμα-Βήμα](#εγκατάσταση-βήμα-βήμα)
3. [Ρύθμιση Garmin](#ρύθμιση-garmin)
4. [Ρύθμιση Telegram Bot](#ρύθμιση-telegram-bot)
5. [Ρύθμιση Weather API](#ρύθμιση-weather-api)
6. [Πρώτη Εκκίνηση](#πρώτη-εκκίνηση)
7. [Καθημερινή Χρήση](#καθημερινή-χρήση)
8. [Προβλήματα και Λύσεις](#προβλήματα-και-λύσεις)
9. [Συντήρηση](#συντήρηση)

---

## Απαιτήσεις Συστήματος

### Software
- **Python**: 3.11+
- **OS**: Linux, macOS, ή Windows (με WSL)
- **Git**: Για version control
- **Internet**: Για API calls (Garmin, Weather, Telegram)

### Hardware
- **RAM**: Τουλάχιστον 2GB
- **Disk**: 500MB ελεύθερος χώρος
- **Network**: Σταθερή σύνδεση internet

---

## Εγκατάσταση Βήμα-Βήμα

### 1. Clone το Repository
```bash
cd ~/
git clone https://github.com/zafiriss-ux/project-mayhem.git
cd project-mayhem
git checkout main
```

### 2. Δημιουργία Virtual Environment
```bash
# Δημιουργία venv
python3 -m venv venv

# Ενεργοποίηση
source venv/bin/activate  # Linux/macOS
# ή
.\venv\Scripts\activate  # Windows
```

### 3. Εγκατάσταση Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Δημιουργία Directories
```bash
mkdir -p data/logs data/database data/cache
```

### 5. Ρύθμιση Environment Variables
```bash
cp .env.example .env
nano .env  # ή χρησιμοποίησε το editor που προτιμάς
```

---

## Ρύθμιση Garmin

### Βήμα 1: Garmin Connect Credentials
Άνοιξε το `.env` και πρόσθεσε τα credentials σου:
```bash
GARMIN_EMAIL=your_email@example.com
GARMIN_PASSWORD=your_password
```

### Βήμα 2: Test Connection
```bash
python -c "from titan.integrations.garmin_sync import GarminSync; g = GarminSync(); print('✅ Connected' if g.connect() else '❌ Failed')"
```

### Βήμα 3: First Sync
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

### Σημαντικά Σημεία:
- ⚠️ Το Garmin Connect μπορεί να έχει rate limits
- ⚠️ Χρησιμοποίησε δυνατό password
- ⚠️ Μην κοινοποιήσεις το `.env` file

---

## Ρύθμιση Telegram Bot

### Βήμα 1: Δημιουργία Bot

1. Άνοιξε το Telegram
2. Ψάξε για `@BotFather`
3. Στείλε `/newbot`
4. Ακολούθησε τις οδηγίες:
   ```
   Name: TITAN Coach
   Username: your_titan_bot
   ```
5. Κράτα το **Bot Token** που θα σου δώσει

### Βήμα 2: Εύρεση Chat ID

1. Ψάξε για `@userinfobot` στο Telegram
2. Στείλε `/start`
3. Θα σου δώσει το **Chat ID** σου (π.χ., 123456789)

### Βήμα 3: Προσθήκη στο .env
```bash
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN_HERE
TELEGRAM_CHAT_ID=123456789
```

### Βήμα 4: Test Bot
```bash
python << 'EOF'
from titan.integrations.telegram_bot import TitanTelegramBot

bot = TitanTelegramBot()
success = bot.send_message("🎯 TITAN Bot is online!")
print("✅ Message sent!" if success else "❌ Failed")
EOF
```

---

## Ρύθμιση Weather API

### Βήμα 1: Open-Meteo (δωρεάν, χωρίς API key)

TITAN χρησιμοποιεί το [Open-Meteo](https://open-meteo.com/) — δωρεάν, χωρίς εγγραφή ή API key.

### Βήμα 2: Προσθήκη στο .env
```bash
# WEATHER_API_KEY — δεν απαιτείται, το TITAN χρησιμοποιεί Open-Meteo (δωρεάν, χωρίς key)
WEATHER_LOCATION=Athens,GR  # ή το location σου
```

### Βήμα 3: Test Weather API
```bash
python << 'EOF'
from titan.integrations.weather_api import WeatherAPI

weather = WeatherAPI()
current = weather.get_current_conditions()
print(f"✅ Weather: {current['temp_c']}°C, Dew: {current['dew_point']}°C")
EOF
```

---

## Πρώτη Εκκίνηση

### 1. Έλεγχος Ρυθμίσεων
```bash
# Έλεγξε ότι όλα τα environment variables είναι σωστά
cat .env
```

### 2. Εκκίνηση TITAN
```bash
cd titan
python main.py
```

### 3. Τι θα δεις:
```
╔═══════════════════════════════════════════════════════════╗
║                    TITAN v51.0                            ║
║          AI-Powered Training Intelligence System          ║
╚═══════════════════════════════════════════════════════════╝

🔧 Initializing TITAN components...
✅ All components initialized!

🚀 Starting background services...
✅ Background services started!

📅 Scheduled tasks:
  • Morning coaching: Daily at 07:00
  • Weekly plan: Sunday at 20:00
  • Garmin sync: Every 6 hours
  • Weather updates: Every hour

🎯 TITAN is ready! Running in background...
Press Ctrl+C to stop.
```

### 4. Επιβεβαίωση
Θα λάβεις test μήνυμα στο Telegram:
```
🎯 TITAN Bot is online!
```

---

## Καθημερινή Χρήση

### Αυτόματα Μηνύματα

#### Κάθε Πρωί (07:00)
```
🌅 GOOD MORNING!
Monday, February 16, 2026

🏃 Today's Workout:
TEMPO - 12 km

⏰ Optimal Running Time:
06:30 (Dew point: 13.2°C, Comfortable)

💊 Recovery Status:
• HRV: ✅ NORMAL (48.5 → Proceed)
• Sleep: 8/10
• Readiness: 85/100

🍽 Nutrition Focus:
450g carbs, 135g protein
```

#### Κάθε Κυριακή (20:00)
```
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
[7-day detailed plan...]
```

### Background Processes

Το TITAN τρέχει αυτόματα:
- ✅ **Garmin Sync**: Κάθε 6 ώρες (01:00, 07:00, 13:00, 19:00)
- ✅ **Weather Update**: Κάθε ώρα
- ✅ **Morning Coach**: Κάθε πρωί 07:00
- ✅ **Weekly Planner**: Κυριακή 20:00

### Χειροκίνητη Εκτέλεση

#### Test Morning Routine
```bash
python << 'EOF'
from titan.orchestration.daily_coach import DailyCoach
# ... initialize components ...
coach = DailyCoach(...)
coach.run_morning_routine()
EOF
```

#### Generate Weekly Plan
```bash
python << 'EOF'
from titan.features.weekly_planner import WeeklyPlanGenerator
# ... initialize engines ...
planner = WeeklyPlanGenerator(hrv_engine, tsb_engine, acwr_engine)
plan = planner.generate_weekly_plan(athlete_profile, phase='BUILD')
print(plan)
EOF
```

---

## Προβλήματα και Λύσεις

### Garmin Connection Failed
```bash
# Πρόβλημα: "❌ Garmin connection failed"

# Λύση 1: Έλεγξε credentials
echo $GARMIN_EMAIL
echo $GARMIN_PASSWORD

# Λύση 2: Δοκίμασε manual login
python -c "from titan.integrations.garmin_sync import GarminSync; g = GarminSync(); g.connect()"

# Λύση 3: Έλεγξε rate limits
# Περίμενε 1 ώρα και δοκίμασε ξανά
```

### Telegram Not Sending
```bash
# Πρόβλημα: Δεν λαμβάνεις μηνύματα

# Λύση 1: Έλεγξε bot token
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getMe"

# Λύση 2: Έλεγξε chat ID
echo $TELEGRAM_CHAT_ID

# Λύση 3: Στείλε test message
python -c "from titan.integrations.telegram_bot import TitanTelegramBot; bot = TitanTelegramBot(); bot.send_message('Test')"
```

### Weather API Issues
```bash
# Πρόβλημα: Weather data not updating

# Open-Meteo δεν απαιτεί API key.
# Λύση 1: Έλεγξε το WEATHER_LOCATION στο .env
echo $WEATHER_LOCATION

# Λύση 2: Test API
python -c "from titan.integrations.weather_api import WeatherAPI; w = WeatherAPI(); print(w.get_current_conditions())"
```

### Memory Issues
```bash
# Πρόβλημα: High memory usage

# Λύση: Clear logs
rm -rf data/logs/*
```

---

## Συντήρηση

### Καθημερινή
- ✅ Έλεγχος Telegram για notifications
- ✅ Βεβαίωση ότι το TITAN τρέχει

### Εβδομαδιαία
- ✅ Review εβδομαδιαίου πλάνου
- ✅ Έλεγχος logs για errors

### Μηνιαία
- ✅ Backup database
```bash
cp data/database/titan.db data/database/titan_backup_$(date +%Y%m%d).db
```
- ✅ Clear old logs
```bash
find data/logs -type f -mtime +30 -delete
```

### Updates
```bash
# Pull latest changes
git pull origin main

# Restart TITAN
pkill -f "python main.py"
cd titan && python main.py
```

---

## 🎯 System Check Script

Δημιούργησε ένα `check_titan.sh`:
```bash
#!/bin/bash
echo "🔍 TITAN System Check"
echo "===================="

# Check Python
python3 --version && echo "✅ Python OK" || echo "❌ Python missing"

# Check venv
[[ -d "venv" ]] && echo "✅ venv OK" || echo "❌ venv missing"

# Check .env
[[ -f ".env" ]] && echo "✅ .env OK" || echo "❌ .env missing"

# Check running process
pgrep -f "python main.py" > /dev/null && echo "✅ TITAN running" || echo "⚠️ TITAN not running"

# Check last log
if [[ -f "data/logs/titan.log" ]]; then
    echo "📄 Last log entry:"
    tail -n 1 data/logs/titan.log
fi

echo "===================="
```

```bash
chmod +x check_titan.sh
./check_titan.sh
```

---

## 📞 Support

- **Documentation**: README.md, ARCHITECTURE.md, CHANGES.md
- **Issues**: GitHub Issues
- **Email**: [your-email]

---

**TITAN v51.0** - Το πλήρες AI προπονητικό σύστημα 🚀
