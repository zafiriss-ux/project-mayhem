import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from titan.config.settings import get_settings  # noqa: E402
from titan.core.database import DatabaseManager  # noqa: E402

db = DatabaseManager(db_dir=Path(get_settings().TITAN_DATA_DIR))
row = db.conn.execute(
    "SELECT last_sync_ok FROM sync_metadata WHERE source='smoke_test_marker'"
).fetchone()
assert row and row[0] == 1, f'Persistence FAILED — marker lost (got {row})'
print('Persistence OK')
