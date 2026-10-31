#!/usr/bin/env python3
"""
API entrypoint — reviewable composition root. Replaces inline Dockerfile CMD.
"""
from pathlib import Path

import uvicorn

from titan.api.auth import AuthStore
from titan.api.main import create_app
from titan.config.settings import get_settings
from titan.core.database import DatabaseManager
from titan.utils.secrets import install_root_log_redaction

# M0-17: every API log line passes the redaction filter before it reaches docker logs.
install_root_log_redaction()
db = DatabaseManager("titan_core.db", db_dir=Path(get_settings().TITAN_DATA_DIR))
auth_store = AuthStore(db=db)
app = create_app(db=db, auth_store=auth_store)

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_config=None,
    )
