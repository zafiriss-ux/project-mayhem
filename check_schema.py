import os
import sys

sys.path.insert(0, '.')
os.environ['TITAN_DATA_DIR'] = '/data'
from pathlib import Path

from titan.core.database import DatabaseManager

db = DatabaseManager(db_dir=Path('/data'))
cursor = db.conn.execute("PRAGMA table_info(sync_metadata)")
print("sync_metadata schema:")
for row in cursor:
    print(f"  {row}")
