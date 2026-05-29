#!/usr/bin/env python3
"""
API entrypoint — reviewable composition root. Replaces inline Dockerfile CMD.
"""
import os
from pathlib import Path

import uvicorn

from titan.core.database import DatabaseManager
from titan.api.auth import AuthStore
from titan.api.main import create_app

DATA_DIR = os.environ.get("TITAN_DATA_DIR", "/data")
db = DatabaseManager("titan_core.db", db_dir=Path(DATA_DIR))
auth_store = AuthStore(db=db)
app = create_app(db=db, auth_store=auth_store)

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_config=None,
    )
