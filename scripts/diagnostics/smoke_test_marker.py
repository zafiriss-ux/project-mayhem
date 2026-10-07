import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from titan.config.settings import get_settings  # noqa: E402
from titan.core.database import DatabaseManager  # noqa: E402

db = DatabaseManager(db_dir=Path(get_settings().TITAN_DATA_DIR))
result = db.conn.execute(
    "INSERT INTO sync_metadata (source, last_success_ts, last_sync_ok, last_error_class) VALUES ('smoke_test_marker', '2025-01-01T00:00:00', 1, NULL)"
).rowcount
db.conn.commit()
print(f"marker written: {result} rows")
