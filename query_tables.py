import sqlite3

db = sqlite3.connect('/app/titan_core.db')
result = [r[0] for r in db.execute('SELECT name FROM sqlite_master WHERE type="table" ORDER BY name').fetchall()]
print(result)
