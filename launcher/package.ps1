# TITAN Release Packager
# Creates TITAN-v<version>-win64.zip with TITAN.exe + SHA256 + README
# Version is read dynamically from titan.__version__

$ErrorActionPreference = "Stop"

$version = & python -c "import titan; print(titan.__version__)" 2>&1
if ($LASTEXITCODE -ne 0 -or $version -notmatch '^\d+\.\d+') {
    Write-Host "ERROR: Could not read titan.__version__. Got: $version" -ForegroundColor Red
    exit 1
}
$packageName = "TITAN-v$version-win64"
$outputZip = "$packageName.zip"

# Verify dist/TITAN.exe exists
if (-not (Test-Path "dist\TITAN.exe")) {
    Write-Host "ERROR: dist\TITAN.exe not found. Run build.ps1 first." -ForegroundColor Red
    exit 1
}

# Verify SHA256 exists
if (-not (Test-Path "dist\TITAN.exe.sha256")) {
    Write-Host "ERROR: dist\TITAN.exe.sha256 not found. Run build.ps1 first." -ForegroundColor Red
    exit 1
}

# Create temp package folder
$tempDir = "dist\$packageName"
if (Test-Path $tempDir) {
    Remove-Item -Recurse -Force $tempDir
}
New-Item -ItemType Directory -Path $tempDir | Out-Null

# Copy files
Copy-Item "dist\TITAN.exe" -Destination $tempDir
Copy-Item "dist\TITAN.exe.sha256" -Destination $tempDir
Copy-Item "launcher\README-QuickStart.txt" -Destination $tempDir

# Create zip
$zipPath = "dist\$outputZip"
if (Test-Path $zipPath) {
    Remove-Item -Force $zipPath
}
Compress-Archive -Path "$tempDir\*" -DestinationPath $zipPath

# Clean temp folder
Remove-Item -Recurse -Force $tempDir

# Display result
$zipSize = [math]::Round((Get-Item $zipPath).Length / 1MB, 2)
$sha256 = (Get-Content "dist\TITAN.exe.sha256").Split()[0]

Write-Host "RELEASE PACKAGE CREATED" -ForegroundColor Green
Write-Host "  Output:  dist\$outputZip ($zipSize MB)"
Write-Host "  SHA256:  $sha256"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Test package on clean Windows 11 VM"
Write-Host "  2. Upload to GitHub Releases: gh release create v$version dist\$outputZip"
Write-Host "  3. Announce release"
