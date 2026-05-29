import sqlite3
db = sqlite3.connect('/app/data/titan_core.db')
for r in db.execute("SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"):
    print(r)
