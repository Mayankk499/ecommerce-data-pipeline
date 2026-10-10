from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAW_DIR = ROOT / "data" / "raw"
DEFAULT_DB = ROOT / "data" / "warehouse.db"
SQL_DIR = ROOT / "sql"
SEEDS_DIR = ROOT / "seeds"
