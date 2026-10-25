"""Load reference data (drivers): bronze -> silver. Used by the Airflow DAG.

Usage: python -m pipeline.load_reference
"""
from pipeline.db import get_engine
from pipeline.load_bronze import RAW_DIR, load_file
from pipeline.run_silver import process_drivers


def main() -> None:
    engine = get_engine()
    path = RAW_DIR / "drivers.csv"
    if not path.exists():
        raise SystemExit("data/raw/drivers.csv not found. Run the generator once first.")

    rows, ms = load_file(engine, path, "drivers")
    print(f"OK     drivers.csv bronze  {rows} rows  {ms} ms")

    n = process_drivers(engine)
    print(f"OK     drivers silver      {n} drivers validated and upserted")


if __name__ == "__main__":
    main()