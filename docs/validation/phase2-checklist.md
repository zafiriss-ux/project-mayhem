# Phase 2 Validation Checklist — TITAN.exe

**Goal:** Zero crash on clean Windows 11 machine.

**Pre-Release Validation:** Complete this checklist before GitHub Release.

---

## Pre-Validation Setup

### 1. Clean Windows 11 VM

**Requirements:**
- [ ] Windows 11 64-bit (up-to-date)
- [ ] **NO** Python installed (test standalone .exe)
- [ ] **NO** existing TITAN data (`C:\Users\*\Documents\TITAN\` should NOT exist)
- [ ] Internet connection (for Garmin/Telegram sync)
- [ ] 1 GB free disk space
- [ ] Telegram app + bot token ready (see setup guide)

**VM Snapshot:**
- [ ] Create VM snapshot "Clean State" (rollback point for re-testing)

---

### 2. Build TITAN.exe

**On Windows 11 build machine (can be same VM or separate):**

```cmd
# Clone repository
git clone https://github.com/zafiriss-ux/project-mayhem.git
cd project-mayhem
git checkout claude/kernel-restructure-training-plan-0UZmS

# Install Python 3.11+ (if not already installed)
# Download from https://www.python.org/downloads/

# Verify Python version
python --version
# Expected: Python 3.11.X or 3.12.X

# Install dependencies
pip install -r requirements.txt
pip install pyinstaller

# Build TITAN.exe
pyinstaller launcher/build.spec

# Verify output
dir dist\TITAN.exe
```

**Checklist:**
- [ ] Build completes without errors
- [ ] `dist/TITAN.exe` exists
- [ ] File size: **10-15 MB** (expected range with UPX compression)
- [ ] No warnings in `build/TITAN/warn-TITAN.txt` (or only harmless warnings)

---

### 3. Generate SHA256 Checksum

```cmd
cd dist
certutil -hashfile TITAN.exe SHA256
```

**Record checksum:**
```
SHA256: ________________________________
```

**Document file size:**
```
File size: _________ MB (__________bytes)
```

---

## Validation Tests (Clean VM)

### Test 1: First Run (No .env)

**Steps:**
1. [ ] Copy `TITAN.exe` to Desktop
2. [ ] Double-click `TITAN.exe`
3. [ ] Observe: GUI wizard window appears (no console flash)

**Expected Behavior:**
- [ ] ✅ No console window flashes before GUI appears
- [ ] ✅ GUI window opens within 3 seconds
- [ ] ✅ Title: "TITAN Setup Wizard v5.7.0"
- [ ] ✅ Welcome screen shows logo + version

**If Failed:**
- [ ] Capture screenshot
- [ ] Check `%USERPROFILE%\Documents\TITAN\logs\launcher_YYYY-MM-DD.log`
- [ ] Note error message:
  ```
  ___________________________________________________
  ```

---

### Test 2: Pre-Flight Checks

**Steps:**
1. [ ] Click "Continue →" button
2. [ ] Observe progress bar

**Expected Behavior:**
- [ ] ✅ Progress frame appears
- [ ] ✅ Status label updates: "Checking Python version..."
- [ ] ✅ Progress bar animates (0% → 100%)
- [ ] ✅ All checks pass within 5 seconds
- [ ] ✅ Status shows: "✅ All checks passed!"
- [ ] ✅ Automatically transitions to credentials frame

**If Failed:**
- [ ] Screenshot of failed check
- [ ] Error message:
  ```
  ___________________________________________________
  ```

---

### Test 3: Wizard Flow (Credentials)

**Steps:**
1. [ ] Enter Garmin credentials (valid account)
   - Username: `_________________`
   - Password: `*********`
2. [ ] Enter Telegram bot token (from @BotFather)
   - Token: `123456789:ABC...`
   - Chat ID: `_________`
3. [ ] Skip OpenAI key (leave blank)
4. [ ] Skip Weather key (leave blank)
5. [ ] Click "Save & Continue"

**Expected Behavior:**
- [ ] ✅ Form validates inputs (email format, token prefix)
- [ ] ✅ No error messages for valid inputs
- [ ] ✅ Transitions to success frame

**If Validation Fails:**
- [ ] Screenshot of error dialog
- [ ] Error text:
  ```
  ___________________________________________________
  ```

---

### Test 4: Configuration Persistence (.env Creation)

**Steps:**
1. [ ] Open File Explorer
2. [ ] Navigate to `%USERPROFILE%\Documents\TITAN\`
3. [ ] Verify `.env` file exists
4. [ ] Open `.env` in Notepad

**Expected Behavior:**
- [ ] ✅ Directory `C:\Users\[YourName]\Documents\TITAN\` exists
- [ ] ✅ `.env` file exists
- [ ] ✅ `.env` contains:
  ```
  GARMIN_USERNAME=...
  GARMIN_PASSWORD=...
  TELEGRAM_BOT_TOKEN=...
  TELEGRAM_CHAT_ID=...
  ```
- [ ] ✅ No plaintext password visible (OK if stored — security note for future)

---

### Test 5: Success Frame & Kernel Launch

**Steps:**
1. [ ] Click "Start TITAN" button
2. [ ] Observe console output (if any)

**Expected Behavior:**
- [ ] ✅ GUI window closes
- [ ] ✅ No error dialogs
- [ ] ✅ Console window may appear briefly (launcher output)
- [ ] ✅ Process continues running (check Task Manager)

**Task Manager Check:**
- [ ] Open Task Manager (Ctrl+Shift+Esc)
- [ ] Verify `TITAN.exe` is running
- [ ] Memory usage: **__________ MB** (record baseline)
- [ ] CPU usage: **< 5%** (idle state)

---

### Test 6: Database Creation

**Steps:**
1. [ ] Navigate to `%USERPROFILE%\Documents\TITAN\`
2. [ ] Verify database files exist

**Expected Behavior:**
- [ ] ✅ `titan_core.db` exists
- [ ] ✅ `titan_core.db-wal` exists (WAL mode enabled)
- [ ] ✅ `titan_core.db-shm` may exist (shared memory)

**Validate WAL Mode:**
```cmd
# If sqlite3.exe available on PATH
sqlite3 C:\Users\[YourName]\Documents\TITAN\titan_core.db "PRAGMA journal_mode;"
# Expected output: wal
```

- [ ] ✅ PRAGMA journal_mode returns `wal`

---

### Test 7: Logging

**Steps:**
1. [ ] Navigate to `%USERPROFILE%\Documents\TITAN\logs\`
2. [ ] Verify log file exists
3. [ ] Open log in Notepad

**Expected Behavior:**
- [ ] ✅ `logs/` directory exists
- [ ] ✅ `launcher_YYYY-MM-DD.log` exists (today's date)
- [ ] ✅ Log contains startup messages:
  ```
  [2026-02-19 XX:XX:XX] INFO     ======================================================================
  [2026-02-19 XX:XX:XX] INFO     TITAN LAUNCHER — 2026-02-19 XX:XX:XX
  [2026-02-19 XX:XX:XX] INFO     Log file: C:\Users\...\TITAN\logs\launcher_2026-02-19.log
  ```
- [ ] ✅ No ERROR or CRITICAL messages (unless expected)

---

### Test 8: Telegram Test Message

**Steps:**
1. [ ] Open Telegram app (phone or web)
2. [ ] Check bot chat
3. [ ] Wait up to 30 seconds

**Expected Behavior:**
- [ ] ✅ Message received within 30 seconds
- [ ] ✅ Message format:
  ```
  📱 TITAN Coach

  🌅 GOOD MORNING!
  [Date]

  🏃 Today's Workout: ...
  💤 Sleep: ...
  💓 HRV: ...
  ⚖️ Weight: ...
  ```

**If No Message:**
- [ ] Check logs for Telegram errors
- [ ] Verify bot token is correct (send `/start` to bot)
- [ ] Verify chat ID is correct (check BotFather `/getUpdates`)
- [ ] Error in logs:
  ```
  ___________________________________________________
  ```

---

### Test 9: Garmin Sync

**Steps:**
1. [ ] Check logs for Garmin sync activity
2. [ ] Verify no authentication errors

**Expected Behavior:**
- [ ] ✅ Logs show: `Garmin sync started...`
- [ ] ✅ No `GARMIN_AUTH_FAILED` errors
- [ ] ✅ Activities synced (if recent runs exist)

**If 2FA Required:**
- [ ] Logs show prompt for 2FA code
- [ ] Follow on-screen instructions (console or Telegram)

**Error Handling:**
- [ ] ❌ If Garmin auth fails:
  ```
  Error message: _______________________________
  Remediation suggested: _______________________
  ```

---

### Test 10: Second Run (Existing .env)

**Steps:**
1. [ ] Close TITAN (if running)
2. [ ] Delete `TITAN.exe` from Desktop
3. [ ] Copy fresh `TITAN.exe` again (simulate update)
4. [ ] Double-click `TITAN.exe`

**Expected Behavior:**
- [ ] ✅ Wizard does NOT appear (`.env` already exists)
- [ ] ✅ Launcher proceeds directly to kernel
- [ ] ✅ Console shows: `✓ Configuration found.`
- [ ] ✅ Kernel starts successfully
- [ ] ✅ Database reused (no data loss)

---

### Test 11: Debug Mode (--debug Flag)

**Steps:**
1. [ ] Open Command Prompt
2. [ ] Navigate to Desktop
3. [ ] Run:
   ```cmd
   TITAN.exe --debug
   ```
4. [ ] Observe console output

**Expected Behavior:**
- [ ] ✅ Console window opens immediately
- [ ] ✅ Live logs stream to console:
  ```
  INFO     ======================================================================
  INFO     TITAN LAUNCHER — ...
  DEBUG    Launcher started with args: ['TITAN.exe', '--debug']
  ```
- [ ] ✅ Console stays open (doesn't close automatically)
- [ ] ✅ Verbose output visible

---

### Test 12: Frozen Path Resolution

**Steps:**
1. [ ] Open log file
2. [ ] Search for path-related messages

**Expected Behavior:**
- [ ] ✅ No `FileNotFoundError` for bundled modules
- [ ] ✅ Data directory path is `C:\Users\[Name]\Documents\TITAN\`
- [ ] ✅ Database path is `C:\Users\[Name]\Documents\TITAN\titan_core.db`
- [ ] ✅ No references to `_MEI*` temp folders in user-facing paths

**Validate with Debug Mode:**
```python
# Add temporary debug print to launcher/main.py
from launcher.paths import get_path_info
print(get_path_info())
```

Expected output:
```json
{
  "frozen": true,
  "sys.executable": "C:\\Users\\...\\Desktop\\TITAN.exe",
  "sys._MEIPASS": "C:\\Users\\...\\AppData\\Local\\Temp\\_MEI123456",
  "bundle_dir": "C:\\Users\\...\\AppData\\Local\\Temp\\_MEI123456",
  "exe_dir": "C:\\Users\\...\\Desktop"
}
```

- [ ] ✅ `frozen: true`
- [ ] ✅ `sys._MEIPASS` points to temp extraction folder

---

### Test 13: Memory Usage Baseline

**Steps:**
1. [ ] Open Task Manager → Performance → Memory
2. [ ] Launch TITAN.exe
3. [ ] Wait 60 seconds (idle state)
4. [ ] Record memory usage

**Expected Behavior:**
- [ ] ✅ Initial launch: < 100 MB
- [ ] ✅ After 60 seconds idle: < 150 MB
- [ ] ✅ After Garmin sync: < 200 MB
- [ ] ✅ No memory leaks (usage stable after 5 minutes)

**Record:**
```
Initial:    _____ MB
Idle (60s): _____ MB
After sync: _____ MB
```

---

### Test 14: No Console Flash (Windowed Mode)

**Steps:**
1. [ ] Restart VM (fresh state)
2. [ ] Double-click `TITAN.exe`
3. [ ] Watch carefully for console window

**Expected Behavior:**
- [ ] ✅ **NO** black console window appears before GUI
- [ ] ✅ GUI appears directly (smooth UX)
- [ ] ✅ No "cmd.exe" flash (common PyInstaller issue)

**If Console Flash Detected:**
- [ ] Duration: _______ seconds
- [ ] Content visible: Yes / No
- [ ] Issue: Likely `console=False` not applied correctly

---

### Test 15: Crash Recovery

**Steps:**
1. [ ] Forcefully terminate TITAN.exe (Task Manager → End Task)
2. [ ] Relaunch TITAN.exe
3. [ ] Verify recovery

**Expected Behavior:**
- [ ] ✅ Launches successfully (no corruption)
- [ ] ✅ Database intact (WAL mode handles crash recovery)
- [ ] ✅ No "database is locked" errors
- [ ] ✅ Logs show clean restart

---

## Post-Validation

### Checklist Summary

**Critical Tests (Must Pass):**
- [ ] First run: Wizard appears, no console flash
- [ ] Pre-flight checks: All pass
- [ ] .env created: Credentials saved
- [ ] Database created: titan_core.db + WAL mode
- [ ] Telegram message: Received within 30 seconds
- [ ] Garmin sync: No auth errors
- [ ] Second run: Skips wizard, reuses .env
- [ ] Debug mode: Console logs visible
- [ ] Memory usage: < 200 MB idle
- [ ] No console flash: Windowed mode works

**Optional Tests (Nice to Have):**
- [ ] Frozen path resolution: Correct _MEIPASS handling
- [ ] Crash recovery: WAL mode handles termination

---

### Artifacts to Document

**1. SHA256 Checksum:**
```
SHA256: _______________________________________________
```

**2. File Size:**
```
File size: __________ MB (__________bytes)
```

**3. Memory Usage:**
```
Initial:    _____ MB
Idle (60s): _____ MB
After sync: _____ MB
```

**4. Startup Time:**
```
GUI launch: _______ seconds
Kernel ready: _______ seconds
```

**5. Screenshots:**
- [ ] Welcome screen
- [ ] Pre-flight checks (progress bar)
- [ ] Credentials form
- [ ] Success screen
- [ ] Telegram message
- [ ] Task Manager (memory usage)

---

### Release Approval

**Sign-Off:**
- [ ] All critical tests passed
- [ ] Zero crashes observed
- [ ] Telegram + Garmin working
- [ ] Memory usage acceptable
- [ ] No console flash
- [ ] Ready for GitHub Release

**Signed by:** _________________
**Date:** _____________________

---

## Appendix: Troubleshooting Common Issues

### Issue: "Wizard doesn't open, TITAN.exe crashes immediately"

**Debug:**
1. Run `TITAN.exe --debug` in Command Prompt
2. Check logs at `%USERPROFILE%\Documents\TITAN\logs\`
3. Look for Python version error, missing DLL, or import error

**Common Causes:**
- PyInstaller excluded a critical dependency → Add to `hiddenimports` in `build.spec`
- Windows Defender blocked .exe → Unblock via Properties
- Corrupted build → Rebuild with `pyinstaller --clean`

---

### Issue: "Telegram message not received"

**Debug:**
1. Check logs for `TELEGRAM_SEND_FAILED`
2. Verify bot token with `/getUpdates` URL:
   ```
   https://api.telegram.org/bot[TOKEN]/getUpdates
   ```
3. Verify chat ID matches the ID from `/getUpdates`

**Common Causes:**
- Wrong bot token → Copy again from @BotFather
- Chat ID mismatch → Send `/start` to bot first
- Firewall blocking Telegram API → Check Windows Firewall

---

### Issue: "Garmin authentication failed"

**Debug:**
1. Check logs for `GARMIN_AUTH_FAILED`
2. Verify username/password are correct
3. Try logging into https://connect.garmin.com manually

**Common Causes:**
- 2FA enabled → Approve login on Garmin app
- Wrong password → Re-enter in wizard
- Captcha required → Use `garth` library with captcha solver (future feature)

---

### Issue: "Database is locked"

**Debug:**
1. Check `PRAGMA journal_mode` (should be `wal`, not `delete`)
2. Verify no other TITAN instances running
3. Check `titan_core.db-wal` exists

**Common Causes:**
- WAL mode not enabled → Fixed in database.py (commit d9289ae)
- Multiple instances → Kill old processes

---

### Issue: "Memory usage > 300 MB"

**Debug:**
1. Check Task Manager → Details → TITAN.exe
2. Check logs for Garmin sync activity (may spike temporarily)
3. Wait 5 minutes — should stabilize

**Common Causes:**
- Garmin sync downloading large history → Expected, temporary
- Memory leak in science modules → Profile with `memory_profiler`

---

**For issues not covered here:**
**https://github.com/zafiriss-ux/project-mayhem/issues**
