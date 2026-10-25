"""Print a quick health summary of the latest generated trips file."""
import json
from pathlib import Path

import pandas as pd


def main() -> None:
    files = sorted(Path("data/raw").glob("trips_*.csv"))
    if not files:
        raise SystemExit("No trips_*.csv found. Run: python -m generator.generate first.")

    path = files[-1]
    df = pd.read_csv(path, dtype=str)

    print(f"File: {path.name}")
    print(f"Rows: {len(df)}")
    print(f"Duplicate trip_ids: {df['trip_id'].duplicated().sum()}")

    print("\n--- status counts ---")
    print(df["status"].value_counts(dropna=False).to_string())

    print("\n--- city counts ---")
    print(df["city"].value_counts(dropna=False).to_string())

    print("\n--- columns with missing values ---")
    nulls = df.isna().sum()
    print(nulls[nulls > 0].to_string())

    manifest_path = Path("data/raw") / path.name.replace("trips_", "manifest_").replace(".csv", ".json")
    if manifest_path.exists():
        print("\n--- manifest (ground truth of injected defects) ---")
        print(json.dumps(json.loads(manifest_path.read_text())["injected_defects"], indent=2))


if __name__ == "__main__":
    main()