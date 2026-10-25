"""Quick check that Python can talk to the HaulPulse warehouse."""
from sqlalchemy import text

from pipeline.db import get_engine


def main() -> None:
    engine = get_engine()
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version()")).scalar()
        print("Connected to:", version)

        schemas = conn.execute(
            text(
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE schema_name IN ('raw','staging','quarantine','analytics','ops') "
                "ORDER BY schema_name"
            )
        ).scalars().all()
        print("HaulPulse schemas found:", schemas)

        expected = {"raw", "staging", "quarantine", "analytics", "ops"}
        missing = expected - set(schemas)
        if missing:
            raise SystemExit(f"Missing schemas: {sorted(missing)}")
        print("All 5 schemas exist. Phase 1 database check PASSED.")


if __name__ == "__main__":
    main()