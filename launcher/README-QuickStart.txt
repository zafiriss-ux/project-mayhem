═══════════════════════════════════════════════════════════════════════════════
   TITAN OS — Closed-Loop Sovereign Training Intelligence
═══════════════════════════════════════════════════════════════════════════════

  📦 Package Contents:
     • TITAN.exe           Windows executable (Python 3.12 frozen build)
     • TITAN.exe.sha256    Checksum for integrity verification
     • README-QuickStart.txt   This file

  🚀 Quick Start (30 seconds):

     1. Double-click TITAN.exe
     2. Wait for GUI setup wizard to launch (~3 seconds)
     3. Click "Continue" through pre-flight checks
     4. Enter your credentials:
        • Telegram Bot Token (from @BotFather)
        • Garmin Connect username & password
     5. Click "Save & Continue"
     6. Click "Start TITAN"

     That's it! The TITAN menu runs in the black console window.
     Keep that window open while you use TITAN.

  📁 Data Location:

     All data stored in:   C:\Users\YourName\Documents\TITAN\
     (if Windows blocks that folder: %LOCALAPPDATA%\TITAN\)

     Folder structure:
        TITAN\
         ├── .env                 Your configuration (encrypted credentials)
         ├── titan_core.db        Training database (SQLite with WAL mode)
         └── logs\                Log files (launcher + kernel)

  🔒 Security:

     • Credentials stored in .env (NOT in the .exe)
     • Database uses AES encryption for sensitive data
     • Logs do NOT contain passwords or API tokens
     • Safe to share TITAN.exe (no secrets embedded)

  🐛 Troubleshooting:

     Issue: Windows Defender blocks TITAN.exe
     Fix:   Right-click → Properties → Check "Unblock" → Apply
            Or click "More Info" → "Run Anyway" when prompted

     Issue: GUI doesn't appear
     Fix:   Run from Command Prompt: TITAN.exe --debug
            Check output for errors

     Issue: Telegram messages not received
     Fix:   1. Verify bot token: https://t.me/BotFather → /token
            2. Send /start to your bot first
            3. Check logs: Documents\TITAN\logs\launcher_YYYY-MM-DD.log

     Issue: Database locked errors
     Fix:   Close all TITAN instances. Only run one at a time.

  📊 Advanced Options:

     Debug mode:        TITAN.exe --debug
                        (Shows path diagnostics + verbose logs)

     Console wizard:    TITAN.exe --console
                        (Text-based setup, no GUI)

     Version info:      TITAN.exe --version
                        (Shows build metadata)

  📖 Full Documentation:

     GitHub: https://github.com/zafiriss-ux/project-mayhem
     Docs:   https://github.com/zafiriss-ux/project-mayhem/tree/main/docs

  🆘 Support:

     • GitHub Issues: https://github.com/zafiriss-ux/project-mayhem/issues
     • Discord:       (coming soon)
     • Email:         (see GitHub profile)

  ⚙️ Technical Specifications:

     Build Info:
       • Version:      in the zip name (TITAN-vX.Y.Z-win64.zip) and the GitHub Release
       • Python:       3.12 (frozen with PyInstaller, see requirements-build.txt)
       • Platform:     Windows x64, built by .github/workflows/release.yml

     System Requirements:
       • Windows 10 or 11 (x64)
       • 4 GB RAM minimum (8 GB recommended)
       • 500 MB disk space
       • Internet connection (for Garmin sync + Telegram)
       • No Python installation required!

     Database:
       • SQLite 3 with WAL mode
       • Concurrent read/write safe
       • Auto-backup on schema changes
       • Compression recovery tracking

  ✅ Verification (Optional):

     To verify download integrity:

     1. Open PowerShell in this folder
     2. Run:
        (Get-FileHash TITAN.exe -Algorithm SHA256).Hash
     3. Compare with TITAN.exe.sha256 contents
     4. Hashes must match exactly

  📜 License:

     MIT License — Free to use, modify, distribute
     See: https://github.com/zafiriss-ux/project-mayhem/blob/main/LICENSE

═══════════════════════════════════════════════════════════════════════════════

  Ready to transform your training? Double-click TITAN.exe to begin! 🚀

═══════════════════════════════════════════════════════════════════════════════
