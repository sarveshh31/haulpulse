"""Apply every SQL file in sql/ddl in order. Safe to re-run (uses IF NOT EXISTS)."""
from pathlib import Path

from pipeline.db import get_engine

DDL_DIR = Path("sql/ddl")


def run_ddl() -> None:
    files = sorted(DDL_DIR.glob("*.sql"))
    if not files:
        raise SystemExit(f"No .sql files found in {DDL_DIR}")

    engine = get_engine()
    with engine.begin() as conn:
        for f in files:
            conn.exec_driver_sql(f.read_text(encoding="utf-8"))
            print(f"Applied {f.name}")
    print("Bootstrap complete.")


if __name__ == "__main__":
    run_ddl()