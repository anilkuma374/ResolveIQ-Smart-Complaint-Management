from pathlib import Path
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
EXPORT_DIR = DATA_DIR / "exports"
GROUND_TRUTH_DIR = DATA_DIR / "ground_truth"
DB_PATH = DATA_DIR / "complaints.db"
SCHEMA_PATH = ROOT / "database" / "schema.sql"
for p in (DATA_DIR, EXPORT_DIR, GROUND_TRUTH_DIR):
    p.mkdir(parents=True, exist_ok=True)
