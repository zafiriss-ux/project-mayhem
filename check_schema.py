import sys, os
sys.path.insert(0, '.')
os.environ['TITAN_DATA_DIR'] = '/data'
from titan.core.database import DatabaseManager
from pathlib import Path

db = DatabaseManager(db_dir=Path('/data'))
cursor = db.conn.execute("PRAGMA table_info(sync_metadata)")
print("sync_metadata schema:")
for row in cursor:
    print(f"  {row}")
