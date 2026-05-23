import os
import sys

sys.path.insert(0, '.')
os.environ['TITAN_DATA_DIR'] = '/data'
from pathlib import Path

from titan.core.database import DatabaseManager

db = DatabaseManager(db_dir=Path('/data'))
result = db.conn.execute(
    "INSERT INTO sync_metadata (source, last_success_ts, last_sync_ok, last_error_class) VALUES ('smoke_test_marker', '2025-01-01T00:00:00', 1, NULL)"
).rowcount
db.conn.commit()
print(f"marker written: {result} rows")
