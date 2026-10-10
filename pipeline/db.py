import sqlite3
from pathlib import Path


def connect(db_path) -> sqlite3.Connection:
    """Open the warehouse (a single SQLite file). Creates parent folders."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def run_sql_file(conn: sqlite3.Connection, path: Path) -> None:
    conn.executescript(Path(path).read_text())


def scalar(conn: sqlite3.Connection, sql: str):
    return conn.execute(sql).fetchone()[0]
