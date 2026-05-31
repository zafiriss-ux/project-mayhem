import sqlite3

db_alembic = sqlite3.connect('/app/titan_alembic.db')
db_core = sqlite3.connect('/app/titan_core.db')
print('Alembic DB tables:', [r[0] for r in db_alembic.execute('SELECT name FROM sqlite_master WHERE type="table" ORDER BY name').fetchall()])
print('Core DB tables:', [r[0] for r in db_core.execute('SELECT name FROM sqlite_master WHERE type="table" ORDER BY name').fetchall()])
