"""Per-domain SQL for DatabaseManager (plan task #18).

Each repository holds the queries of one domain and works on the connection,
lock and closed-state of the DatabaseManager that owns it. DatabaseManager stays
the public facade: its methods keep their names and signatures and delegate here.
"""
