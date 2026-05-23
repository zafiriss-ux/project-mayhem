#!/usr/bin/env bash
# Generates RS256 JWT key pair and appends
# to .env if not already present.
# Usage: bash scripts/generate_jwt_keys.sh

set -euo pipefail
ENV_FILE=".env"

if grep -q "TITAN_JWT_PRIVATE_KEY" \
    "$ENV_FILE" 2>/dev/null; then
  echo "JWT keys already in $ENV_FILE — skip"
  exit 0
fi

echo "Generating RS256 key pair..."
PRIV=$(openssl genrsa 2048 2>/dev/null)
PUB=$(echo "$PRIV" | \
  openssl rsa -pubout 2>/dev/null)

# Single-line with literal \n
PRIV_LINE=$(echo "$PRIV" | \
  awk '{printf "%s\\n",$0}')
PUB_LINE=$(echo "$PUB" | \
  awk '{printf "%s\\n",$0}')

echo "" >> "$ENV_FILE"
echo "TITAN_JWT_PRIVATE_KEY=$PRIV_LINE" \
  >> "$ENV_FILE"
echo "TITAN_JWT_PUBLIC_KEY=$PUB_LINE" \
  >> "$ENV_FILE"

echo "✅ JWT keys written to $ENV_FILE"
