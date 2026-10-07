import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from titan.config.settings import get_settings  # noqa: E402

db = sqlite3.connect(Path(get_settings().TITAN_DATA_DIR) / 'titan_core.db')
result = [r[0] for r in db.execute('SELECT name FROM sqlite_master WHERE type="table" ORDER BY name').fetchall()]
print(result)
