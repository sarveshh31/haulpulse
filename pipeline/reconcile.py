"""Compare what the validator found against the generator's ground-truth manifests.

Usage: python -m pipeline.reconcile
"""
import json
from collections import Counter
from pathlib import Path

from sqlalchemy import text

from pipeline.db import get_engine

RAW_DIR = Path("data/raw")

# manifest defect -> (kind, key)
#   "reason": number of quarantined rows carrying that reason code
#   "fixed" : number of values auto-corrected (from ops.validation_log)
MAPPING = {
    "duplicate":               ("reason", "DUPLICATE_IN_FILE"),
    "negative_fare":           ("reason", "NEGATIVE_FARE"),
    "delivered_before_pickup": ("reason", "DELIVERED_BEFORE_PICKUP"),
    "missing_driver":          ("reason", "MISSING_DRIVER"),
    "missing_fare":            ("reason", "MISSING_FARE"),
    "bad_status":              ("reason", "INVALID_STATUS"),
    "bad_distance":            ("reason", "BAD_DISTANCE"),
    "gps_out_of_india":        ("reason", "GPS_OUT_OF_INDIA"),
    "unparseable_timestamp":   ("reason", "UNPARSEABLE_TIMESTAMP"),
    "missing_city":            ("reason", "MISSING_CITY"),
    "city_variant":            ("fixed", "city_fixed"),
    "status_case":             ("fixed", "status_fixed"),
}


def main() -> None:
    engine = get_engine()
    with engine.connect() as conn:
        files = [r[0] for r in conn.execute(text("SELECT DISTINCT source_file FROM raw.trips ORDER BY 1"))]
        if not files:
            raise SystemExit("No bronze data found.")

        reasons = dict(
            conn.execute(
                text(
                    "SELECT r, COUNT(*) FROM quarantine.trips_rejected q, unnest(q.reject_reasons) AS r "
                    "WHERE q.source_file = ANY(:files) GROUP BY r"
                ),
                {"files": files},
            ).all()
        )
        fixed = conn.execute(
            text(
                """
                SELECT COALESCE(SUM(city_fixed), 0), COALESCE(SUM(status_fixed), 0),
                       COALESCE(SUM(rows_in), 0), COALESCE(SUM(rows_clean), 0),
                       COALESCE(SUM(rows_rejected), 0)
                FROM (
                    SELECT DISTINCT ON (source_file) *
                    FROM ops.validation_log
                    WHERE source_file = ANY(:files) AND status = 'SUCCESS'
                    ORDER BY source_file, log_id DESC
                ) t
                """
            ),
            {"files": files},
        ).one()

    fixed_map = {"city_fixed": int(fixed[0]), "status_fixed": int(fixed[1])}
    rows_in, rows_clean, rows_rejected = int(fixed[2]), int(fixed[3]), int(fixed[4])

    injected = Counter()
    missing_manifests = []
    for f in files:
        mpath = RAW_DIR / f.replace("trips_", "manifest_").replace(".csv", ".json")
        if not mpath.exists():
            missing_manifests.append(f)
            continue
        injected.update(json.loads(mpath.read_text())["injected_defects"])

    print(f"Files reconciled: {len(files) - len(missing_manifests)} of {len(files)}")
    print(f"{'defect':<26}{'injected':>10}{'detected':>10}   result")
    print("-" * 56)
    all_ok = True
    for defect, (kind, key) in MAPPING.items():
        exp = int(injected.get(defect, 0))
        got = int(reasons.get(key, 0)) if kind == "reason" else fixed_map[key]
        ok = exp == got
        all_ok &= ok
        print(f"{defect:<26}{exp:>10}{got:>10}   {'MATCH' if ok else 'MISMATCH'}")

    print("-" * 56)
    print(f"Rows in: {rows_in} | clean: {rows_clean} | rejected (incl. duplicates): {rows_rejected} "
          f"({rows_rejected / rows_in:.1%})")
    if missing_manifests:
        print(f"WARNING: no manifest for {missing_manifests}")
    print("RESULT: ALL INJECTED DEFECTS ACCOUNTED FOR" if all_ok else "RESULT: MISMATCHES FOUND")
    if not all_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()