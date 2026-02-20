# TITAN Build Script — Minimal Production Version
# Builds TITAN.exe deterministically with Python 3.11.9 + PyInstaller 6.4.0

$ErrorActionPreference = "Stop"

# Enforce Python 3.11.x
$pythonVersion = & python --version 2>&1
if ($pythonVersion -notmatch "Python 3\.11\.") {
    Write-Host "ERROR: Python 3.11.x is required. Found: $pythonVersion" -ForegroundColor Red
    Write-Host "       Install Python 3.11.x from https://www.python.org/downloads/" -ForegroundColor Red
    exit 1
}
Write-Host "Python version OK: $pythonVersion" -ForegroundColor Green

# Clean previous build
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }

# Build with PyInstaller
pyinstaller launcher\build.spec --clean

# Verify output
if (-not (Test-Path "dist\TITAN.exe")) {
    Write-Host "ERROR: Build failed. dist\TITAN.exe not found." -ForegroundColor Red
    exit 1
}

# Generate SHA256 checksum
$sha256 = (Get-FileHash "dist\TITAN.exe" -Algorithm SHA256).Hash
"$sha256 *TITAN.exe" | Out-File -FilePath "dist\TITAN.exe.sha256" -Encoding ASCII

# Display build info
$fileSize = [math]::Round((Get-Item "dist\TITAN.exe").Length / 1MB, 2)
Write-Host "BUILD COMPLETE" -ForegroundColor Green
Write-Host "  Output: dist\TITAN.exe ($fileSize MB)"
Write-Host "  SHA256: $sha256"
