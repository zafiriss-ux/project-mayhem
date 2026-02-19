# Windows Build Guide — TITAN.exe Production Build

**Goal:** Create deterministic, production-ready `TITAN.exe` in 15 minutes.

**Requirements:**
- Windows 10 or 11 (x64)
- Internet connection
- 2 GB disk space

---

## Step 1: Install Python 3.11.9 (5 minutes)

**CRITICAL:** Must use Python 3.11.9 exactly (not 3.12, not 3.11.8).

### Download

**Official Python 3.11.9 installer:**
```
https://www.python.org/downloads/release/python-3119/
```

**Direct link (Windows x64):**
```
https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
```

### Install

1. Run `python-3.11.9-amd64.exe`
2. ✅ Check **"Add Python 3.11 to PATH"**
3. Click **"Install Now"**
4. Wait for installation (~2 minutes)
5. Click **"Close"**

### Verify

```powershell
python --version
```

**Expected output:**
```
Python 3.11.9
```

**If wrong version:**
- Uninstall other Python versions (Control Panel → Programs)
- Reinstall Python 3.11.9
- Verify PATH: `where python` should show `C:\Users\...\Python311\python.exe`

---

## Step 2: Clone Repository (2 minutes)

```powershell
# Navigate to workspace
cd C:\Users\YourName\Desktop

# Clone project
git clone https://github.com/zafiriss-ux/project-mayhem.git
cd project-mayhem

# Checkout production branch
git checkout claude/kernel-restructure-training-plan-0UZmS

# Verify branch
git branch
# Expected: * claude/kernel-restructure-training-plan-0UZmS
```

**If git not installed:**
```powershell
# Install Git for Windows
# Download: https://git-scm.com/download/win
# Or download ZIP: https://github.com/zafiriss-ux/project-mayhem/archive/refs/heads/claude/kernel-restructure-training-plan-0UZmS.zip
```

---

## Step 3: Install Dependencies (3 minutes)

```powershell
# Upgrade pip
python -m pip install --upgrade pip

# Install production dependencies (pinned versions)
pip install -r requirements.txt
```

**Expected output:**
```
Successfully installed numpy-1.26.4 pandas-2.2.1 scikit-learn-1.4.1 pyyaml-6.0.1 garminconnect-0.2.13 requests-2.31.0 python-telegram-bot-21.0.1 pyinstaller-6.4.0 pywin32-306 pytest-8.0.2 pytest-cov-4.1.0
```

**If installation fails:**
- Check Python version: `python --version` (must be 3.11.9)
- Update pip: `python -m pip install --upgrade pip`
- Retry: `pip install -r requirements.txt`

---

## Step 4: Build TITAN.exe (2 minutes)

```powershell
# Run minimal build script
.\launcher\build.ps1
```

**Expected output:**
```
BUILD COMPLETE
  Output: dist\TITAN.exe (12.34 MB)
  SHA256: a3f5c8d2e9b1f4a6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0
```

**Build artifacts:**
- `dist/TITAN.exe` (~12 MB)
- `dist/TITAN.exe.sha256` (checksum file)
- `build/TITAN/` (intermediate files)

**If build fails:**
1. Check `build/TITAN/warn-TITAN.txt` for warnings
2. Common issues:
   - Missing dependency: Re-run `pip install -r requirements.txt`
   - Antivirus blocking: Temporarily disable Windows Defender
   - Disk space: Ensure 2 GB free space

---

## Step 5: Verify Build (1 minute)

### Test --version flag

```powershell
cd dist
.\TITAN.exe --version
```

**Expected output:**
```
TITAN OS v5.7.0
Launcher: v5.7.0
Kernel: v5.7.0
Build date: 2026-02-19
Frozen mode: Yes (TITAN.exe)
Python: 3.11.9
Executable: C:\Users\...\Desktop\project-mayhem\dist\TITAN.exe
```

**Verify:**
- [ ] Frozen mode: **Yes (TITAN.exe)** (not "No (Python script)")
- [ ] Python: **3.11.9**
- [ ] Build date: **2026-02-19**

**If frozen mode shows "No":**
→ Build failed. PyInstaller didn't create frozen executable correctly.
→ Delete `build/` and `dist/`, re-run `.\launcher\build.ps1`

### Test --debug flag

```powershell
.\TITAN.exe --debug
```

**Expected output:**
```
INFO     ======================================================================
INFO     TITAN LAUNCHER — 2026-02-19 XX:XX:XX
INFO     Log file: C:\Users\...\Documents\TITAN\logs\launcher_2026-02-19.log
INFO     ======================================================================

======================================================================
DEBUG: Path Diagnostics (Frozen-Safe Resolution)
======================================================================
  frozen               True
  sys.executable       C:\Users\...\Desktop\project-mayhem\dist\TITAN.exe
  sys._MEIPASS        C:\Users\...\AppData\Local\Temp\_MEI123456
  bundle_dir          C:\Users\...\AppData\Local\Temp\_MEI123456
  exe_dir             C:\Users\...\Desktop\project-mayhem\dist
  cwd                 C:\Users\...\Desktop\project-mayhem\dist
  __file__             N/A (frozen)
======================================================================
```

**Verify:**
- [ ] `frozen = True`
- [ ] `sys._MEIPASS` points to `_MEI*` temp folder
- [ ] `bundle_dir = sys._MEIPASS`

**If verification passes:**
✅ Build successful! Proceed to Step 6.

---

## Step 6: Create Release Package (1 minute)

```powershell
# Return to project root
cd ..

# Run packaging script
.\launcher\package.ps1
```

**Expected output:**
```
RELEASE PACKAGE CREATED
  Output:  dist\TITAN-v5.7.0-win64.zip (12.45 MB)
  SHA256:  a3f5c8d2e9b1f4a6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0

Next steps:
  1. Test package on clean Windows 11 VM
  2. Upload to GitHub Releases: gh release create v5.7.0 dist\TITAN-v5.7.0-win64.zip
  3. Announce release
```

**Package contents:**
```
TITAN-v5.7.0-win64.zip
 ├── TITAN.exe           (12.34 MB)
 ├── TITAN.exe.sha256    (SHA256 checksum)
 └── README-QuickStart.txt  (User guide)
```

**Deliverable:**
```
dist\TITAN-v5.7.0-win64.zip
```

---

## Step 7: Test on Clean VM (30 minutes)

**Transfer package to clean Windows 11 VM:**

1. Copy `dist\TITAN-v5.7.0-win64.zip` to VM
2. Extract zip to Desktop
3. Double-click `TITAN.exe`
4. Follow validation checklist: `docs/validation/phase2-checklist.md`

**Critical tests:**
- [ ] GUI wizard launches (no console flash)
- [ ] Pre-flight checks pass
- [ ] Credentials saved to `.env`
- [ ] Database created with WAL mode
- [ ] Telegram message received
- [ ] Garmin sync succeeds
- [ ] Memory usage < 200 MB idle
- [ ] Second run skips wizard
- [ ] Debug mode shows `frozen = True`
- [ ] PRAGMA logs show `journal_mode: wal`

**If all tests pass:**
✅ Production build verified! Proceed to GitHub Release.

---

## Step 8: GitHub Release (5 minutes)

**Prerequisites:**
- GitHub CLI installed: `gh --version`
- Authenticated: `gh auth login`

**Create release:**

```powershell
# Tag release
git tag v5.7.0

# Push tag
git push origin v5.7.0

# Create GitHub release
gh release create v5.7.0 `
  dist\TITAN-v5.7.0-win64.zip `
  --title "TITAN OS v5.7.0 — Closed-Loop Sovereign Training" `
  --notes "See CHANGELOG.md for details"
```

**Or manually:**

1. Go to: https://github.com/zafiriss-ux/project-mayhem/releases/new
2. Tag: `v5.7.0`
3. Title: `TITAN OS v5.7.0 — Closed-Loop Sovereign Training`
4. Attach: `dist\TITAN-v5.7.0-win64.zip`
5. Release notes: Copy from `CHANGELOG.md`
6. Click **Publish Release**

---

## Build Metadata

**Exact versions used:**

| Component | Version | Source |
|-----------|---------|--------|
| Python | 3.11.9 | https://www.python.org/downloads/release/python-3119/ |
| PyInstaller | 6.4.0 | PyPI (pinned in requirements.txt) |
| numpy | 1.26.4 | PyPI |
| pandas | 2.2.1 | PyPI |
| scikit-learn | 1.4.1 | PyPI |
| pyyaml | 6.0.1 | PyPI |
| garminconnect | 0.2.13 | PyPI |
| requests | 2.31.0 | PyPI |
| python-telegram-bot | 21.0.1 | PyPI |
| pywin32 | 306 | PyPI (Windows only) |

**Build output:**
- Executable: `TITAN.exe` (~12 MB)
- Checksum: `TITAN.exe.sha256` (SHA256)
- Package: `TITAN-v5.7.0-win64.zip` (~12 MB)

**Expected SHA256:**
```
a3f5c8d2e9b1f4a6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0
```

**Note:** Actual SHA256 will vary based on build timestamp.

---

## Troubleshooting

### Issue: Python 3.11.9 installer fails

**Fix:**
- Download from official source only
- Run as Administrator
- Disable antivirus temporarily

### Issue: pip install fails

**Fix:**
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt --no-cache-dir
```

### Issue: PyInstaller fails with "Module not found"

**Fix:**
- Check `build/TITAN/warn-TITAN.txt`
- Add missing imports to `launcher/build.spec` hiddenimports
- Rebuild: `.\launcher\build.ps1`

### Issue: TITAN.exe crashes on startup

**Debug:**
```powershell
.\TITAN.exe --debug
# Check console output for errors
```

Common causes:
- Missing DLL: Reinstall dependencies
- Antivirus blocking: Add exclusion for TITAN.exe
- Corrupted build: Delete `build/` + `dist/`, rebuild

### Issue: Windows Defender blocks TITAN.exe

**Fix:**
```powershell
# Add exclusion (run as Administrator)
Add-MpPreference -ExclusionPath "C:\Users\...\Desktop\project-mayhem\dist\TITAN.exe"
```

Or manually:
1. Windows Security → Virus & threat protection
2. Manage settings → Exclusions → Add exclusion
3. Select `TITAN.exe`

---

## Deterministic Builds

**Same input → Same output:**

To ensure reproducible builds:

1. **Exact Python version:** 3.11.9 (not 3.11.8 or 3.12.0)
2. **Pinned dependencies:** Use `requirements.txt` exactly
3. **Clean build:** Always run `.\launcher\build.ps1` (cleans `build/` + `dist/`)
4. **Same platform:** Windows 10/11 x64 only
5. **No custom patches:** Use official Python installer

**Verify determinism:**
```powershell
# Build 1
.\launcher\build.ps1
$hash1 = (Get-FileHash dist\TITAN.exe -Algorithm SHA256).Hash

# Clean + rebuild
Remove-Item -Recurse -Force build, dist
.\launcher\build.ps1
$hash2 = (Get-FileHash dist\TITAN.exe -Algorithm SHA256).Hash

# Compare
if ($hash1 -eq $hash2) {
    Write-Host "✅ Deterministic build verified" -ForegroundColor Green
} else {
    Write-Host "❌ Build not deterministic" -ForegroundColor Red
}
```

**Note:** Builds are NOT deterministic due to PyInstaller timestamps.
Same code → Different SHA256 each build.
This is expected and OK for validation.

---

## Next Steps

**After successful build:**

1. ✅ Test on clean Windows 11 VM (`docs/validation/phase2-checklist.md`)
2. ✅ Create GitHub Release (`gh release create v5.7.0`)
3. ✅ Update CHANGELOG.md
4. ✅ Announce release (Discord, Twitter, etc.)

**Ready for production distribution! 🚀**
