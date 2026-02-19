# TITAN Build Script — Windows PowerShell
# Automates PyInstaller build + checksum generation + validation

$ErrorActionPreference = "Stop"

Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "   TITAN.exe Build Script v5.7.0" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# ──────────────────────────────────────────────────────────────────────────────
# 1. Pre-Build Checks
# ──────────────────────────────────────────────────────────────────────────────

Write-Host "→ Step 1: Pre-build checks..." -ForegroundColor Yellow

# Check Python version
Write-Host "  Checking Python version..."
$pythonVersion = python --version 2>&1
if ($pythonVersion -match "Python 3\.1[1-9]|Python 3\.[2-9]") {
    Write-Host "  ✓ $pythonVersion" -ForegroundColor Green
} else {
    Write-Host "  ✗ Python 3.11+ required. Found: $pythonVersion" -ForegroundColor Red
    exit 1
}

# Check PyInstaller
Write-Host "  Checking PyInstaller..."
$pyinstaller = Get-Command pyinstaller -ErrorAction SilentlyContinue
if ($pyinstaller) {
    Write-Host "  ✓ PyInstaller found" -ForegroundColor Green
} else {
    Write-Host "  ✗ PyInstaller not found. Installing..." -ForegroundColor Red
    pip install pyinstaller
}

Write-Host ""

# ──────────────────────────────────────────────────────────────────────────────
# 2. Clean Previous Build
# ──────────────────────────────────────────────────────────────────────────────

Write-Host "→ Step 2: Cleaning previous build..." -ForegroundColor Yellow

if (Test-Path "build") {
    Remove-Item -Recurse -Force "build"
    Write-Host "  ✓ Removed build/" -ForegroundColor Green
}

if (Test-Path "dist") {
    Remove-Item -Recurse -Force "dist"
    Write-Host "  ✓ Removed dist/" -ForegroundColor Green
}

Write-Host ""

# ──────────────────────────────────────────────────────────────────────────────
# 3. Run PyInstaller
# ──────────────────────────────────────────────────────────────────────────────

Write-Host "→ Step 3: Building TITAN.exe..." -ForegroundColor Yellow
Write-Host "  This may take 60-90 seconds..."

$startTime = Get-Date
pyinstaller launcher\build.spec
$endTime = Get-Date
$buildTime = ($endTime - $startTime).TotalSeconds

if (Test-Path "dist\TITAN.exe") {
    Write-Host "  ✓ Build completed in $([math]::Round($buildTime, 1))s" -ForegroundColor Green
} else {
    Write-Host "  ✗ Build failed. Check output above." -ForegroundColor Red
    exit 1
}

Write-Host ""

# ──────────────────────────────────────────────────────────────────────────────
# 4. File Size & Checksum
# ──────────────────────────────────────────────────────────────────────────────

Write-Host "→ Step 4: Generating checksums..." -ForegroundColor Yellow

$exePath = "dist\TITAN.exe"
$fileSize = (Get-Item $exePath).Length
$fileSizeMB = [math]::Round($fileSize / 1MB, 2)

Write-Host "  File size: $fileSizeMB MB ($fileSize bytes)" -ForegroundColor Cyan

# SHA256
$sha256 = (Get-FileHash $exePath -Algorithm SHA256).Hash
Write-Host "  SHA256: $sha256" -ForegroundColor Cyan

# Save to file
$checksumFile = "dist\TITAN.exe.sha256"
"$sha256 *TITAN.exe" | Out-File -FilePath $checksumFile -Encoding ASCII
Write-Host "  ✓ Checksum saved to $checksumFile" -ForegroundColor Green

Write-Host ""

# ──────────────────────────────────────────────────────────────────────────────
# 5. Validation
# ──────────────────────────────────────────────────────────────────────────────

Write-Host "→ Step 5: Build validation..." -ForegroundColor Yellow

# Check warnings
if (Test-Path "build\TITAN\warn-TITAN.txt") {
    $warnings = Get-Content "build\TITAN\warn-TITAN.txt"
    if ($warnings.Length -gt 0) {
        Write-Host "  ⚠ Warnings found (see build\TITAN\warn-TITAN.txt):" -ForegroundColor Yellow
        $warnings | Select-Object -First 5 | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
    } else {
        Write-Host "  ✓ No build warnings" -ForegroundColor Green
    }
}

# Size check
if ($fileSizeMB -lt 8 -or $fileSizeMB -gt 20) {
    Write-Host "  ⚠ Unexpected file size: $fileSizeMB MB (expected 10-15 MB)" -ForegroundColor Yellow
} else {
    Write-Host "  ✓ File size within expected range" -ForegroundColor Green
}

Write-Host ""

# ──────────────────────────────────────────────────────────────────────────────
# 6. Summary
# ──────────────────────────────────────────────────────────────────────────────

Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "   BUILD COMPLETE" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Output:      dist\TITAN.exe" -ForegroundColor Cyan
Write-Host "  Size:        $fileSizeMB MB" -ForegroundColor Cyan
Write-Host "  SHA256:      $sha256" -ForegroundColor Cyan
Write-Host "  Build time:  $([math]::Round($buildTime, 1))s" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Test on clean Windows VM (see docs/validation/phase2-checklist.md)" -ForegroundColor Gray
Write-Host "  2. Create release package:" -ForegroundColor Gray
Write-Host "     Compress-Archive -Path dist\TITAN.exe -DestinationPath TITAN-v5.7.0-win64.zip" -ForegroundColor Gray
Write-Host "  3. Upload to GitHub Releases" -ForegroundColor Gray
Write-Host ""
