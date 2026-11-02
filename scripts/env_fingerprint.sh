#!/usr/bin/env bash
# Emit machine environment metadata using the canonical runner's interpreter.
set -euo pipefail

PY="${1:-python3}"
exec "$PY" - <<'PYTHON'
import hashlib
import importlib.metadata
import json
import platform
import socket
import sys

distributions = sorted(
    (distribution.metadata["Name"], distribution.version)
    for distribution in importlib.metadata.distributions()
)
venv_metadata = json.dumps(
    {"distributions": distributions, "prefix": sys.prefix},
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")
print(json.dumps({
    "python_version": platform.python_version(),
    "venv_hash": hashlib.sha256(venv_metadata).hexdigest(),
    "host_id": hashlib.sha256(socket.gethostname().encode("utf-8")).hexdigest(),
}, sort_keys=True))
PYTHON
