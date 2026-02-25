# Windows 11 VM Validation — Quick Start

**Goal:** Build TITAN.exe and run validation checklist in < 1 hour.

---

## Pre-Requisites

- [ ] Windows 11 VM (clean install, no Python)
- [ ] Internet connection
- [ ] Telegram bot token ready (see docs/install/windows.md step 2)
- [ ] Garmin Connect credentials

---

## Step 1: Build TITAN.exe (10 minutes)

**On Windows build machine:**

```powershell
# Clone repository
git clone https://github.com/zafiriss-ux/project-mayhem.git
cd project-mayhem
git checkout claude/kernel-restructure-training-plan-0UZmS

# Install Python 3.11+ (if needed)
# Download: https://www.python.org/downloads/

# Verify Python version
python --version
# Expected: Python 3.11.X or 3.12.X

# Install dependencies
pip install -r requirements.txt
pip install pyinstaller

# Build TITAN.exe (automated script)
.\launcher\build.ps1
```

**Expected Output:**
```
═══════════════════════════════════════════════════════════════
   BUILD COMPLETE
═══════════════════════════════════════════════════════════════

  Output:      dist\TITAN.exe
  Size:        12.3 MB
  SHA256:      a3f5c8d2e9b1...
  Build time:  47.2s
```

**Artifacts:**
- `dist/TITAN.exe` (executable)
- `dist/TITAN.exe.sha256` (checksum)

---

## Step 2: Debug Mode Test (2 minutes)

**Before testing on clean VM, verify debug mode works:**

```cmd
cd dist
TITAN.exe --debug
```

**Expected Output:**
```
INFO     ======================================================================
INFO     TITAN LAUNCHER — 2026-02-19 XX:XX:XX
INFO     Log file: C:\Users\...\Documents\TITAN\logs\launcher_2026-02-19.log
INFO     ======================================================================

======================================================================
DEBUG: Path Diagnostics (Frozen-Safe Resolution)
======================================================================
  frozen               True
  sys.executable       C:\Users\Build\Desktop\dist\TITAN.exe
  sys._MEIPASS        C:\Users\Build\AppData\Local\Temp\_MEI123456
  bundle_dir          C:\Users\Build\AppData\Local\Temp\_MEI123456
  exe_dir             C:\Users\Build\Desktop\dist
  cwd                 C:\Users\Build\Desktop\dist
  __file__             N/A (frozen)
======================================================================
```

**Verify:**
- [ ] `frozen = True` (not False)
- [ ] `sys._MEIPASS` points to `_MEI*` temp folder
- [ ] `bundle_dir = sys._MEIPASS`
- [ ] `exe_dir = C:\Users\...\Desktop\dist` (where TITAN.exe is)

**If frozen = False:**
→ Build failed. Check `build/TITAN/warn-TITAN.txt` for errors.

---

## Step 3: Copy to Clean VM (1 minute)

**Transfer files:**
```
TITAN.exe              → C:\Users\Test\Desktop\
TITAN.exe.sha256       → C:\Users\Test\Desktop\
```

**Verify checksum (optional):**
```cmd
certutil -hashfile TITAN.exe SHA256
# Compare with TITAN.exe.sha256 contents
```

---

## Step 4: Run Validation Checklist (30 minutes)

**Open checklist:**
```cmd
notepad C:\path\to\project-mayhem\docs\validation\phase2-checklist.md
```

**Execute tests 1-15:**

### Critical Tests (Must Pass)

| # | Test | Time | Action |
|---|------|------|--------|
| 1 | First run | 1 min | Double-click TITAN.exe → GUI wizard appears |
| 2 | Pre-flight checks | 1 min | Click Continue → Progress bar 100% |
| 3 | Wizard flow | 2 min | Enter credentials → Save & Continue |
| 4 | .env creation | 1 min | Check `%USERPROFILE%\Documents\TITAN\.env` exists |
| 5 | Kernel launch | 1 min | Click "Start TITAN" → Process runs |
| 6 | Database creation | 1 min | Check `titan_core.db` + `titan_core.db-wal` exist |
| 7 | Logging | 1 min | Open `logs\launcher_YYYY-MM-DD.log` |
| 8 | Telegram test | 30 sec | Check Telegram for message |
| 9 | Garmin sync | 2 min | Check logs for sync activity |
| 10 | Second run | 1 min | Close TITAN → Relaunch → Skips wizard |
| 11 | Debug mode | 2 min | Run `TITAN.exe --debug` → Console logs visible |
| 12 | Frozen paths | 1 min | Verify `frozen = True` in --debug output |
| 13 | Memory usage | 2 min | Task Manager → Record memory |
| 14 | No console flash | 1 min | Watch for console window before GUI |
| 15 | Crash recovery | 2 min | Force-kill → Relaunch → No errors |

**Total:** ~20 minutes for critical tests.

---

## Step 5: Use Diagnostics Button (Optional)

**After setup completes:**

1. [ ] Click **"📊 Diagnostics"** button (Success screen)
2. [ ] Dialog appears with path info:
   ```
   TITAN Diagnostics
   ==================================================

   Frozen mode: Yes (TITAN.exe)
   Executable: C:\Users\Test\Desktop\TITAN.exe
   Bundle dir: C:\Users\Test\AppData\Local\Temp\_MEI123456
   Data directory: C:\Users\Test\Documents\TITAN
   Logs directory: C:\Users\Test\Documents\TITAN\logs

   Click OK to open logs folder.
   ```
3. [ ] Click OK → Windows Explorer opens `C:\Users\Test\Documents\TITAN\logs\`
4. [ ] Verify `launcher_2026-02-19.log` exists

**Purpose:** Help beginners locate logs for troubleshooting.

---

## Step 6: Document Results

**Fill in checklist artifacts:**

```
SHA256: _______________________________________________
  (from TITAN.exe.sha256 file)

File size: __________ MB (__________bytes)
  (Right-click TITAN.exe → Properties → Size)

Memory usage:
  Initial:    _____ MB  (Task Manager after launch)
  Idle (60s): _____ MB  (Task Manager after 1 minute)
  After sync: _____ MB  (Task Manager after Garmin sync)

Startup time:
  GUI launch:    _______ seconds  (double-click to wizard)
  Kernel ready:  _______ seconds  (wizard complete to logs)
```

**Screenshots to capture:**
1. Welcome screen (wizard)
2. Pre-flight checks (progress bar at 100%)
3. Credentials form (with placeholders — no real passwords!)
4. Success screen (with Diagnostics button)
5. Telegram message
6. Task Manager (memory usage)
7. Diagnostics dialog (path info)
8. Logs folder (Windows Explorer)

---

## Step 7: Check Logs for PRAGMA Results

**Open log file:**
```cmd
notepad C:\Users\Test\Documents\TITAN\logs\launcher_2026-02-19.log
```

**Search for:**
```
PRAGMA journal_mode: wal
PRAGMA synchronous: 1
```

**Verify:**
- [ ] `journal_mode = wal` (not "delete" or "truncate")
- [ ] `synchronous = 1` (NORMAL mode)

**If not found:**
→ Database initialization didn't log. Check for errors earlier in log.

---

## Troubleshooting

### Issue: TITAN.exe won't run — Windows Defender blocks it

**Fix:**
1. Right-click `TITAN.exe` → Properties
2. Check **Unblock** at bottom → Apply
3. Double-click again

Or click **More Info** → **Run Anyway** when SmartScreen appears.

---

### Issue: Wizard doesn't open, crashes immediately

**Debug:**
```cmd
TITAN.exe --debug
```

Check console output for error. Common causes:
- Missing Python DLL → Rebuild with `pyinstaller --clean`
- Missing hiddenimport → Add to `build.spec`

---

### Issue: frozen = False in --debug output

**Cause:** Build didn't create frozen executable correctly.

**Fix:**
1. Check `dist/TITAN.exe` exists (not `dist/TITAN/TITAN.exe`)
2. Rebuild: `.\launcher\build.ps1`
3. Verify onefile mode in `build.spec`: `exe = EXE(..., name='TITAN', ...)`

---

### Issue: Telegram message not received

**Debug:**
1. Check logs for `TELEGRAM_SEND_FAILED`
2. Verify bot token: https://api.telegram.org/bot[TOKEN]/getUpdates
3. Send `/start` to bot first

---

### Issue: Database locked error

**Debug:**
Check log for:
```
PRAGMA journal_mode: wal
```

If missing or shows "delete":
→ WAL mode didn't enable. Check database.py line 83-84.

---

## Success Criteria

**All critical tests pass:**
- [x] GUI wizard appears (no console flash)
- [x] Pre-flight checks pass
- [x] .env created
- [x] Database created with WAL mode
- [x] Telegram message received
- [x] Garmin sync succeeds (or fails gracefully with clear error)
- [x] Second run skips wizard
- [x] Debug mode shows frozen = True
- [x] Memory usage < 200 MB idle
- [x] PRAGMA journal_mode = wal logged

**Sign-Off:**
```
Tested by: _________________
Date: _____________________
Windows version: ___________
TITAN.exe SHA256: __________
Status: ✅ PASSED / ❌ FAILED
```

---

## Next Steps (After Validation)

**If all tests pass:**

1. Create release package:
   ```powershell
   Compress-Archive -Path TITAN.exe -DestinationPath TITAN-v5.7.0-win64.zip
   ```

2. Upload to GitHub Releases:
   - Tag: `v5.7.0`
   - Title: `TITAN OS v5.7.0 — Closed-Loop Sovereign Training`
   - Attach: `TITAN-v5.7.0-win64.zip` + `TITAN.exe.sha256`

3. Update CHANGELOG.md with release notes

4. Announce on Discord/Twitter/etc.

**If tests fail:**
- Document failures in checklist
- Check logs (`launcher_YYYY-MM-DD.log`)
- Create GitHub issue with:
  - Error message
  - Log excerpt
  - Screenshots
  - System info (Windows version, Python version if applicable)

---

**Estimated Total Time:** 45 minutes (build 10min + validation 30min + documentation 5min)

**Good luck! 🚀**
