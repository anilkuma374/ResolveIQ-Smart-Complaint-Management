import sqlite3
from config import DB_PATH, SCHEMA_PATH

def connect(db_path=DB_PATH):
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn

def initialize(db_path=DB_PATH):
    conn = connect(db_path)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    from services.operations import ensure_extensions
    ensure_extensions(conn)
    conn.commit()
    return conn
