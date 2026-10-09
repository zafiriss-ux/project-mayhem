# TITAN Build Script — Minimal Production Version
# Builds TITAN.exe deterministically with Python 3.12 + PyInstaller 6.4.0

$ErrorActionPreference = "Stop"

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

# Smoke: the exe must start and print to its console. A windowed build prints
# nothing, which is how v5.8.0 and v5.8.1 shipped a menu nobody could see.
$expected = "TITAN OS v" + (Select-String -Path "pyproject.toml" -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value
$smoke = (& "dist\TITAN.exe" --version | Out-String)
if ($LASTEXITCODE -ne 0 -or -not $smoke.Contains($expected)) {
    Write-Host "ERROR: dist\TITAN.exe --version did not print '$expected' (exit $LASTEXITCODE):" -ForegroundColor Red
    Write-Host $smoke
    exit 1
}
Write-Host "Smoke OK: $($smoke.Trim().Split([Environment]::NewLine)[0])"

# Generate SHA256 checksum
$sha256 = (Get-FileHash "dist\TITAN.exe" -Algorithm SHA256).Hash
"$sha256 *TITAN.exe" | Out-File -FilePath "dist\TITAN.exe.sha256" -Encoding ASCII

# Display build info
$fileSize = [math]::Round((Get-Item "dist\TITAN.exe").Length / 1MB, 2)
Write-Host "BUILD COMPLETE" -ForegroundColor Green
Write-Host "  Output: dist\TITAN.exe ($fileSize MB)"
Write-Host "  SHA256: $sha256"
