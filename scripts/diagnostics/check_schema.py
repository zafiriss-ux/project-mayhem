import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from titan.config.settings import get_settings  # noqa: E402
from titan.core.database import DatabaseManager  # noqa: E402

db = DatabaseManager(db_dir=Path(get_settings().TITAN_DATA_DIR))
cursor = db.conn.execute("PRAGMA table_info(sync_metadata)")
print("sync_metadata schema:")
for row in cursor:
    print(f"  {row}")
