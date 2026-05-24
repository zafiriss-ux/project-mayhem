#!/usr/bin/env python3
"""
API entrypoint — reviewable composition root. Replaces inline Dockerfile CMD.
"""
import os
from pathlib import Path

import uvicorn

from titan.api.main import create_app
from titan.core.database import DatabaseManager

DATA_DIR = os.environ.get("TITAN_DATA_DIR", "/data")
db = DatabaseManager("titan_core.db", db_dir=Path(DATA_DIR))
app = create_app(db=db)

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_config=None,
    )
