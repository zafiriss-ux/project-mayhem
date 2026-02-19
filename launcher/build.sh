#!/usr/bin/env bash
# TITAN Build Script — Linux/macOS
# Automates PyInstaller build + checksum generation + validation

set -euo pipefail

echo "═══════════════════════════════════════════════════════════════"
echo "   TITAN Build Script v5.7.0"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# ──────────────────────────────────────────────────────────────────────────────
# 1. Pre-Build Checks
# ──────────────────────────────────────────────────────────────────────────────

echo "→ Step 1: Pre-build checks..."

# Check Python version
echo "  Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1)
if [[ "$PYTHON_VERSION" =~ Python\ 3\.(1[1-9]|[2-9][0-9]) ]]; then
    echo "  ✓ $PYTHON_VERSION"
else
    echo "  ✗ Python 3.11+ required. Found: $PYTHON_VERSION"
    exit 1
fi

# Check PyInstaller
echo "  Checking PyInstaller..."
if command -v pyinstaller &> /dev/null; then
    echo "  ✓ PyInstaller found"
else
    echo "  ✗ PyInstaller not found. Installing..."
    pip3 install pyinstaller
fi

echo ""

# ──────────────────────────────────────────────────────────────────────────────
# 2. Clean Previous Build
# ──────────────────────────────────────────────────────────────────────────────

echo "→ Step 2: Cleaning previous build..."

if [ -d "build" ]; then
    rm -rf build
    echo "  ✓ Removed build/"
fi

if [ -d "dist" ]; then
    rm -rf dist
    echo "  ✓ Removed dist/"
fi

echo ""

# ──────────────────────────────────────────────────────────────────────────────
# 3. Run PyInstaller
# ──────────────────────────────────────────────────────────────────────────────

echo "→ Step 3: Building TITAN..."
echo "  This may take 60-90 seconds..."

START_TIME=$(date +%s)
pyinstaller launcher/build.spec
END_TIME=$(date +%s)
BUILD_TIME=$((END_TIME - START_TIME))

# Determine executable name based on OS
if [[ "$OSTYPE" == "darwin"* ]]; then
    EXE_PATH="dist/TITAN"
    EXE_NAME="TITAN"
else
    EXE_PATH="dist/TITAN"
    EXE_NAME="TITAN"
fi

if [ -f "$EXE_PATH" ]; then
    echo "  ✓ Build completed in ${BUILD_TIME}s"
else
    echo "  ✗ Build failed. Check output above."
    exit 1
fi

echo ""

# ──────────────────────────────────────────────────────────────────────────────
# 4. File Size & Checksum
# ──────────────────────────────────────────────────────────────────────────────

echo "→ Step 4: Generating checksums..."

FILE_SIZE=$(stat -c%s "$EXE_PATH" 2>/dev/null || stat -f%z "$EXE_PATH")
FILE_SIZE_MB=$(awk "BEGIN {printf \"%.2f\", $FILE_SIZE / 1048576}")

echo "  File size: ${FILE_SIZE_MB} MB ($FILE_SIZE bytes)"

# SHA256
if command -v sha256sum &> /dev/null; then
    SHA256=$(sha256sum "$EXE_PATH" | awk '{print $1}')
elif command -v shasum &> /dev/null; then
    SHA256=$(shasum -a 256 "$EXE_PATH" | awk '{print $1}')
else
    echo "  ✗ sha256sum or shasum not found"
    exit 1
fi

echo "  SHA256: $SHA256"

# Save to file
echo "$SHA256 *$EXE_NAME" > "${EXE_PATH}.sha256"
echo "  ✓ Checksum saved to ${EXE_PATH}.sha256"

echo ""

# ──────────────────────────────────────────────────────────────────────────────
# 5. Validation
# ──────────────────────────────────────────────────────────────────────────────

echo "→ Step 5: Build validation..."

# Check warnings
if [ -f "build/TITAN/warn-TITAN.txt" ]; then
    WARNINGS=$(wc -l < "build/TITAN/warn-TITAN.txt")
    if [ "$WARNINGS" -gt 0 ]; then
        echo "  ⚠ $WARNINGS warnings found (see build/TITAN/warn-TITAN.txt)"
        head -5 "build/TITAN/warn-TITAN.txt" | sed 's/^/    /'
    else
        echo "  ✓ No build warnings"
    fi
fi

# Size check
if (( $(echo "$FILE_SIZE_MB < 8.0 || $FILE_SIZE_MB > 20.0" | bc -l) )); then
    echo "  ⚠ Unexpected file size: ${FILE_SIZE_MB} MB (expected 10-15 MB)"
else
    echo "  ✓ File size within expected range"
fi

echo ""

# ──────────────────────────────────────────────────────────────────────────────
# 6. Summary
# ──────────────────────────────────────────────────────────────────────────────

echo "═══════════════════════════════════════════════════════════════"
echo "   BUILD COMPLETE"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "  Output:      $EXE_PATH"
echo "  Size:        ${FILE_SIZE_MB} MB"
echo "  SHA256:      $SHA256"
echo "  Build time:  ${BUILD_TIME}s"
echo ""
echo "Next steps:"
echo "  1. Test on clean environment (see docs/validation/phase2-checklist.md)"
echo "  2. Create release package:"
echo "     zip TITAN-v5.7.0-$(uname -s | tr '[:upper:]' '[:lower:]').zip $EXE_PATH"
echo "  3. Upload to GitHub Releases"
echo ""
