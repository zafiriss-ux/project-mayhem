import os
import sys

sys.path.insert(0, '.')
os.environ['TITAN_DATA_DIR'] = '/data'
from pathlib import Path

from titan.core.database import DatabaseManager

db = DatabaseManager(db_dir=Path('/data'))
row = db.conn.execute(
    "SELECT last_sync_ok FROM sync_metadata WHERE source='smoke_test_marker'"
).fetchone()
assert row and row[0] == 1, f'Persistence FAILED — marker lost (got {row})'
print('Persistence OK')
