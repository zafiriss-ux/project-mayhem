import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from titan.config.settings import get_settings  # noqa: E402

data_dir = Path(get_settings().TITAN_DATA_DIR)
db_alembic = sqlite3.connect(data_dir / 'titan_alembic.db')
db_core = sqlite3.connect(data_dir / 'titan_core.db')
print('Alembic DB tables:', [r[0] for r in db_alembic.execute('SELECT name FROM sqlite_master WHERE type="table" ORDER BY name').fetchall()])
print('Core DB tables:', [r[0] for r in db_core.execute('SELECT name FROM sqlite_master WHERE type="table" ORDER BY name').fetchall()])
