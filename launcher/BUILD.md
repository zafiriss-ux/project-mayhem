# Building TITAN.exe with PyInstaller

This guide explains how to build a standalone Windows executable.

---

## Prerequisites

- **Python 3.11+** installed
- **PyInstaller** package:
  ```bash
  pip install pyinstaller
  ```
- Windows 10/11 (for building Windows .exe)

---

## Build Process

### 1. Clean Previous Builds (Optional)

```bash
rm -rf build/ dist/
```

### 2. Run PyInstaller

```bash
pyinstaller launcher/build.spec
```

**What happens:**
- PyInstaller analyzes `launcher/main.py` and all dependencies
- Bundles Python 3.11.8 runtime + TITAN code + dependencies
- Creates `dist/TITAN.exe` (single-file executable, ~25-30 MB)

**Build time:** ~60 seconds (first build), ~30 seconds (incremental)

### 3. Test the Build

```bash
cd dist
./TITAN.exe
```

Should open the GUI setup wizard if `.env` is missing, or start TITAN kernel otherwise.

---

## Build Spec Configuration

**File:** `launcher/build.spec`

**Key Settings:**
```python
name='TITAN'               # Output filename
console=False             # Windowed mode (no console)
onefile=True              # Single .exe (vs. folder with DLLs)
upx=True                  # Compress with UPX (~30% size reduction)
icon=None                 # TODO: Add titan.ico
```

**Hidden Imports:**
PyInstaller auto-detects most imports, but some need manual declaration:
- `titan.*` modules (all subpackages)
- `tkinter` (GUI wizard)
- `sqlite3` (database)

**Excluded Packages:**
Heavy unused packages are excluded to reduce size:
- `matplotlib`, `pandas`, `numpy`, `scipy`, `pytest`, `IPython`

---

## Testing

### Test on Clean Machine

**Windows VM or clean install:**
1. Copy `TITAN.exe` to Desktop
2. Double-click
3. Wizard appears → enter credentials → "TITAN is ready"
4. Check Telegram for morning briefing

**Expected file structure after first run:**
```
C:\Users\YourName\Documents\TITAN\
├── .env                     # Credentials
├── titan_core.db            # SQLite database
└── logs\
    └── launcher_2026-02-19.log
```

### Debug Mode

```cmd
TITAN.exe --debug
```

Opens console window with live logs. Useful for troubleshooting.

---

## Troubleshooting

### "Failed to execute script 'main'"

**Cause:** PyInstaller couldn't find a dependency.

**Fix:**
1. Check `build/TITAN/warn-TITAN.txt` for missing imports
2. Add to `hiddenimports` in `build.spec`
3. Rebuild

### ".exe is 100+ MB"

**Cause:** Large dependencies included (e.g., numpy, pandas).

**Fix:**
1. Ensure `excludes` list in `build.spec` is active
2. Check `build/TITAN/Analysis-00.toc` for unexpected packages
3. Rebuild

### "Windows Defender blocks .exe"

**Cause:** Unsigned executable triggers SmartScreen.

**Fix (for users):**
1. Right-click `TITAN.exe` → Properties → Unblock
2. Or click "More Info" → "Run Anyway" when SmartScreen appears

**Fix (for distribution):**
Sign the .exe with a code-signing certificate (costs ~$100/year).

---

## Distribution

### Create Release Package

Releases are built by `.github/workflows/release.yml` when a `vX.Y.Z` tag is
pushed (see `docs/RUNBOOK_ROLLBACK.md`). Its Windows job runs `build.ps1`, then
`package.ps1`, and attaches `TITAN-vX.Y.Z-win64.zip` to the GitHub Release.

To package by hand after a local build, pass the version from `pyproject.toml`:

```powershell
.\launcher\package.ps1 -Version 5.8.0   # writes dist\TITAN-v5.8.0-win64.zip
```

---

## Advanced: Code Signing (Optional)

To avoid Windows Defender warnings, sign the .exe:

1. Buy a code-signing certificate (e.g., Sectigo, DigiCert)
2. Install certificate on build machine
3. Sign .exe:
   ```powershell
   signtool sign /tr http://timestamp.digicert.com /td sha256 /fd sha256 /a TITAN.exe
   ```

**Cost:** ~$100-200/year

**Benefit:** Users won't see SmartScreen warnings.

---

## Future: macOS / Linux Builds

PyInstaller supports macOS and Linux.

**macOS:**
```bash
pyinstaller launcher/build.spec
# Output: dist/TITAN (macOS app)
```

**Linux:**
```bash
pyinstaller launcher/build.spec
# Output: dist/TITAN (Linux binary)
```

**Note:** Each platform must be built on its native OS (can't cross-compile).

---

## Dependencies Size Breakdown

| Package | Size (MB) | Included? |
|---------|-----------|-----------|
| Python 3.11 runtime | 8 | ✅ |
| tkinter | 3 | ✅ |
| sqlite3 | 1 | ✅ |
| TITAN kernel | 2 | ✅ |
| launcher | 0.5 | ✅ |
| **Total** | **~14 MB** | |
| UPX compressed | **~10 MB** | |

**Final .exe size:** ~10-12 MB (with UPX compression)

---

For questions, issues, or contributions:
**https://github.com/zafiriss-ux/project-mayhem/issues**
