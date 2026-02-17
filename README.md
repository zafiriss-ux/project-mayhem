# TITAN v51.0 - AI Training Intelligence System

🏃‍♂️ **Πλήρως Αναδομημένο Σύστημα Προπόνησης με AI**

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

## 🚀 Εγκατάσταση

### 1. Προαπαιτούμενα
```bash
python >= 3.8
pip install -r requirements.txt
```

### 2. Ρύθμιση Περιβάλλοντος
```bash
cp .env.example .env
# Edit .env με τα credentials σου
```

### 3. Ρύθμιση .env
```bash
# Garmin
GARMIN_EMAIL=your_email@example.com
GARMIN_PASSWORD=your_password

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
TELEGRAM_CHAT_ID=your_chat_id

# Weather
WEATHER_API_KEY=your_openweathermap_key
WEATHER_LOCATION=Athens,GR
```

### 4. Εκκίνηση
```bash
cd titan
python main.py
```

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
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
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
# Έλεγξε API key
echo $WEATHER_API_KEY

# Test API call
curl "https://api.openweathermap.org/data/2.5/weather?q=Athens&appid=<YOUR_KEY>"
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
