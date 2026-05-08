# TITAN Installation Guide — Windows 10/11

**Target Audience:** Complete beginners with zero Python/CLI experience.

**Time Required:** 5 minutes (including setup wizard).

---

## Prerequisites

- Windows 10 or Windows 11 (64-bit)
- Internet connection (for Garmin/Telegram sync)
- 100 MB free disk space
- Garmin Connect account
- Telegram account + bot token (see below)

> **No Python installation needed** — TITAN.exe bundles everything.

---

## Step 1: Download TITAN

1. Go to **[GitHub Releases](https://github.com/zafiriss-ux/project-mayhem/releases)**
2. Find the latest release (e.g., `v5.7.0`)
3. Download `TITAN-v5.7.0-win64.zip`
4. Unzip to a convenient location:
   - Recommended: `C:\Users\YourName\Documents\TITAN\`
   - Or: Desktop, Downloads, anywhere you like

After unzipping, you should see:
```
TITAN/
├── TITAN.exe          ← Double-click this
├── README.txt
└── LICENSE.txt
```

---

## Step 2: Create Telegram Bot

TITAN sends daily briefings via Telegram. You need a bot token.

### 2.1 Open Telegram App

Open Telegram on your phone or [web.telegram.org](https://web.telegram.org).

### 2.2 Create Bot with BotFather

1. Search for **@BotFather** (official bot by Telegram)
2. Send `/start`
3. Send `/newbot`
4. Follow prompts:
   - **Bot name:** `My TITAN Coach` (or any name you like)
   - **Bot username:** `MyTitanCoachBot` (must be unique, must end in `bot`)
5. BotFather replies with your **bot token**:
   ```
   YOUR_TELEGRAM_BOT_TOKEN_HERE
   ```
   **Copy this token** — you'll need it in Step 4.

### 2.3 Get Your Chat ID

1. Send `/start` to your new bot (search for `@MyTitanCoachBot`)
2. Send any message (e.g., "Hello")
3. Open this URL in your browser (replace `YOUR_BOT_TOKEN`):
   ```
   https://api.telegram.org/botYOUR_BOT_TOKEN/getUpdates
   ```
4. Look for `"chat":{"id":123456789}` in the JSON response
5. **Copy the chat ID** (e.g., `123456789`)

---

## Step 3: Run TITAN

1. Navigate to the folder where you unzipped TITAN
2. **Double-click `TITAN.exe`**

A window appears:

```
╔════════════════════════════════════════════════════════════════════╗
║   ▀█▀ █ ▀█▀ ▄▀█ █▄ █   █▀█ █▀   ▀█ █ ▀▀█                         ║
║    █  █  █  █▀█ █ ▀█   █▄█ ▄█    █▄▀     █                        ║
║   Closed-Loop Sovereign Training Intelligence                     ║
╚════════════════════════════════════════════════════════════════════╝

   Version: 5.7.0
   Data Directory: C:\Users\YourName\Documents\TITAN

🔍 Running pre-flight checks...
   ✓ Python version (bundled: 3.11.8)
   ✓ OS compatibility
   ✓ Data directory created
   ✓ Disk space (150 MB free)
```

---

## Step 4: Setup Wizard

Since this is your first run, TITAN opens the **Setup Wizard**.

### 4.1 Garmin Credentials

```
── Garmin Connect ──────────────────────────────────────────────────

   Garmin username or email: your_email@gmail.com
   Garmin password: **********
```

Enter your Garmin Connect login. TITAN syncs your activities, HRV, sleep, weight.

> ⚠️ If you use 2FA (two-factor authentication), follow the on-screen instructions.

### 4.2 Telegram Bot

```
── Telegram Bot ────────────────────────────────────────────────────

   Telegram bot token: YOUR_TELEGRAM_BOT_TOKEN_HERE
   Your Telegram chat ID: 123456789
```

Paste the token and chat ID from Step 2.

### 4.3 OpenAI (Optional)

```
── OpenAI API (Optional) ───────────────────────────────────────────

   TITAN can use GPT-4 for coaching narratives.
   Leave blank to skip (you can add it later).

   OpenAI API key (sk-...): [press Enter to skip]
```

Press **Enter** to skip, or paste your OpenAI API key if you have one.

### 4.4 Weather API (Optional)

```
── Weather API (Optional) ──────────────────────────────────────────

   For real-time weather data (OpenWeatherMap or similar).
   Leave blank to skip.

   Weather API key: [press Enter to skip]
```

Press **Enter** to skip.

### 4.5 Setup Complete

```
════════════════════════════════════════════════════════════════════
   Setup Complete!
════════════════════════════════════════════════════════════════════

✓ Configuration saved to: C:\Users\YourName\Documents\TITAN\.env
```

Click **Start TITAN** button.

---

## Step 5: TITAN is Ready

```
🚀 Starting TITAN kernel...

======================================================================
   Kernel version: 5.7.0
   Status: Kernel initialized successfully.
======================================================================

✅ TITAN is ready.

   Next steps:
   • Check Telegram for your first morning briefing
   • Database: C:\Users\YourName\Documents\TITAN\titan_core.db
   • Logs: C:\Users\YourName\Documents\TITAN\logs\
```

---

## Step 6: Test Telegram

Within 10 seconds, you should receive a Telegram message:

```
📱 TITAN Coach

🌅 GOOD MORNING!
Monday, February 19, 2026

🏃 Today's Workout: REST
   Your body needs recovery. Take the day off.

💤 Sleep: 7.2h (Good)
💓 HRV: 58 ms (Normal)
⚖️ Weight: 70.5 kg

📅 Tomorrow: EASY RUN (5 km)
```

If you **don't** receive a message:
1. Check bot token and chat ID in setup wizard
2. Send `/start` to your bot again
3. Check logs at `C:\Users\YourName\Documents\TITAN\logs\launcher_YYYY-MM-DD.log`

---

## Troubleshooting

### "TITAN.exe won't run — Windows Defender blocked it"

Windows SmartScreen may block unsigned .exe files.

**Fix:**
1. Right-click `TITAN.exe` → **Properties**
2. Check **Unblock** at the bottom → **Apply**
3. Double-click again

Or click **More Info** → **Run Anyway** when SmartScreen appears.

### "Garmin authentication failed"

- Check username/password are correct
- If you use 2FA, approve login on Garmin app
- Try logging into [connect.garmin.com](https://connect.garmin.com) manually first

### "Telegram bot doesn't respond"

- Verify bot token is correct (check BotFather message)
- Verify chat ID is correct (use `/getUpdates` URL from Step 2.3)
- Send `/start` to your bot before running TITAN

### "Database is corrupted"

Rare, but if it happens:
1. Open `C:\Users\YourName\Documents\TITAN\`
2. Rename `titan_core.db` to `titan_core.db.backup`
3. Run TITAN.exe again — it will create a fresh database

---

## Debug Mode

If you encounter issues, run TITAN in debug mode:

1. Open **Command Prompt** (Windows key + R → type `cmd` → Enter)
2. Navigate to TITAN folder:
   ```cmd
   cd C:\Users\YourName\Documents\TITAN
   ```
3. Run with `--debug` flag:
   ```cmd
   TITAN.exe --debug
   ```

This opens a console window with live logs. Keep it open and send screenshots to:
**https://github.com/zafiriss-ux/project-mayhem/issues**

---

## What TITAN Does Daily

**Every morning at 7:00 AM:**
- Syncs Garmin data (yesterday's run, sleep, HRV)
- Calculates readiness (HRV, TSB, sleep quality)
- Fetches today's session from weekly plan
- Calculates optimal running time (weather, fatigue)
- Generates nutrition plan
- Sends Telegram briefing

**Every Sunday at 8:00 PM:**
- Generates next week's training plan
- Sends to Telegram

**After every run:**
- Post-run analysis
- Recovery recommendations
- Nutrition timing

---

## Updating TITAN

When a new version is released:

1. Download `TITAN-v5.8.0-win64.zip` (or latest) from Releases
2. Unzip to the **same folder** (overwrite old files)
3. Your `.env` and database are safe in `Documents\TITAN\` (separate location)
4. Double-click `TITAN.exe` — automatic migration runs if needed

---

## Uninstalling TITAN

1. Delete the TITAN folder (where TITAN.exe is)
2. Delete `C:\Users\YourName\Documents\TITAN\` if you want to remove all data

Done.

---

## Next Steps

- **Configure your athlete profile:** Edit `.env` with max HR, lactate thresholds
- **Add shoes to database:** TITAN tracks shoe mileage and rotation
- **Enable calendar sync:** Export training plan to Google Calendar (future feature)

For full documentation, visit:
**https://github.com/zafiriss-ux/project-mayhem/tree/main/docs**
