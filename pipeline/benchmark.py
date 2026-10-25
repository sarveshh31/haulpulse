"""Benchmark query performance: heap vs indexed vs partitioned fact table.

Usage: python -m pipeline.benchmark
Copies analytics.fact_trips into scratch schema `bench` and writes docs/benchmarks.md.
"""
from __future__ import annotations

import json
import statistics
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from pipeline.db import get_engine

WARMUPS = 2
RUNS = 7
REPORT_PATH = Path("docs/benchmarks.md")

QUERIES = {
    "Q1 city revenue, 1 week": """
        SELECT date_key, COUNT(*) AS trips,
               SUM(fare_amount) FILTER (WHERE is_completed) AS revenue
        FROM {t}
        WHERE city_key = md5('Mumbai')
          AND requested_at >= '2026-08-01' AND requested_at < '2026-08-08'
        GROUP BY date_key ORDER BY date_key
    """,
    "Q2 all cities, 1 month": """
        SELECT city_key, COUNT(*) AS trips,
               ROUND(AVG(fare_amount) FILTER (WHERE is_completed), 2) AS avg_fare
        FROM {t}
        WHERE requested_at >= '2026-08-01' AND requested_at < '2026-09-01'
        GROUP BY city_key
    """,
    "Q3 single trip lookup": """
        SELECT * FROM {t} WHERE trip_id = '{trip_id}'
    """,
}


def explain(conn, sql: str) -> dict:
    raw = conn.execute(text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql)).scalar()
    doc = raw if isinstance(raw, list) else json.loads(raw)
    return doc[0]


def walk(node: dict, acc: list) -> None:
    acc.append(node)
    for child in node.get("Plans", []):
        walk(child, acc)


def summarize(doc: dict) -> dict:
    nodes: list = []
    walk(doc["Plan"], nodes)
    scans = [n for n in nodes if "Scan" in n["Node Type"]]
    partitions = {
        n["Relation Name"] for n in scans
        if str(n.get("Relation Name", "")).startswith("fact_part_")
    }
    plan = doc["Plan"]
    return {
        "ms": doc["Execution Time"],
        "scans": ", ".join(sorted({n["Node Type"] for n in scans})),
        "partitions": len(partitions),
        "buffers": plan.get("Shared Hit Blocks", 0) + plan.get("Shared Read Blocks", 0),
    }


def run_stage(engine, stage: str, table: str, trip_id: str, results: list, size: str) -> None:
    with engine.connect() as conn:
        for name, template in QUERIES.items():
            sql = template.format(t=table, trip_id=trip_id)
            for _ in range(WARMUPS):
                explain(conn, sql)
            runs = [summarize(explain(conn, sql)) for _ in range(RUNS)]
            ms = statistics.median(r["ms"] for r in runs)
            last = runs[-1]
            results.append({
                "stage": stage, "query": name, "ms": ms, "scans": last["scans"],
                "partitions": last["partitions"], "buffers": last["buffers"], "size": size,
            })
            print(f"{stage:<26} {name:<26} {ms:>9.2f} ms  | {last['scans']}"
                  + (f" | partitions scanned: {last['partitions']}" if last["partitions"] else ""))


def create_indexes(engine, table: str) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(f"CREATE INDEX idx_{table}_trip_id ON bench.{table} (trip_id)")
        conn.exec_driver_sql(f"CREATE INDEX idx_{table}_requested_at ON bench.{table} (requested_at)")
        conn.exec_driver_sql(f"CREATE INDEX idx_{table}_city_requested ON bench.{table} (city_key, requested_at)")
        conn.exec_driver_sql(f"ANALYZE bench.{table}")


def size_flat(engine) -> str:
    with engine.connect() as conn:
        return conn.execute(text("SELECT pg_size_pretty(pg_total_relation_size('bench.fact_flat'))")).scalar()


def size_part(engine) -> str:
    with engine.connect() as conn:
        return conn.execute(text(
            "SELECT pg_size_pretty(SUM(pg_total_relation_size(relid))) "
            "FROM pg_partition_tree('bench.fact_part') WHERE isleaf"
        )).scalar()


def setup_flat(engine) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS bench")
        conn.exec_driver_sql("DROP TABLE IF EXISTS bench.fact_part CASCADE")
        conn.exec_driver_sql("DROP TABLE IF EXISTS bench.fact_flat CASCADE")
        conn.exec_driver_sql("CREATE TABLE bench.fact_flat AS SELECT * FROM analytics.fact_trips")
        conn.exec_driver_sql("ANALYZE bench.fact_flat")


def setup_partitioned(engine) -> int:
    with engine.begin() as conn:
        lo, hi = conn.execute(text(
            "SELECT date_trunc('month', MIN(requested_at)), date_trunc('month', MAX(requested_at)) "
            "FROM bench.fact_flat"
        )).one()
        conn.exec_driver_sql(
            "CREATE TABLE bench.fact_part (LIKE bench.fact_flat INCLUDING DEFAULTS) "
            "PARTITION BY RANGE (requested_at)"
        )
        y, m, count = lo.year, lo.month, 0
        while (y, m) <= (hi.year, hi.month):
            ny, nm = (y + m // 12, m % 12 + 1)
            conn.exec_driver_sql(
                f"CREATE TABLE bench.fact_part_{y}_{m:02d} PARTITION OF bench.fact_part "
                f"FOR VALUES FROM ('{y}-{m:02d}-01') TO ('{ny}-{nm:02d}-01')"
            )
            y, m, count = ny, nm, count + 1
        conn.exec_driver_sql("INSERT INTO bench.fact_part SELECT * FROM bench.fact_flat")
        conn.exec_driver_sql("ANALYZE bench.fact_part")
    return count


def write_report(results: list, fact_rows: int, pg_version: str, n_partitions: int) -> None:
    base = {r["query"]: r["ms"] for r in results if r["stage"].startswith("1.")}
    lines = [
        "# HaulPulse query benchmarks",
        "",
        f"- Generated: {datetime.now():%Y-%m-%d %H:%M}",
        f"- Table: `fact_trips` copy, **{fact_rows:,} rows**, {n_partitions} monthly partitions in the partitioned stages",
        f"- Engine: {pg_version} (Docker, laptop, default config)",
        f"- Method: `EXPLAIN (ANALYZE, BUFFERS)`, {WARMUPS} warm-ups, median of {RUNS} runs",
        "",
        "| Query | Stage | Median ms | Speedup vs stage 1 | Scan type | Partitions scanned | Buffers | Total size |",
        "|---|---|---:|---:|---|---:|---:|---|",
    ]
    for r in results:
        speed = base[r["query"]] / r["ms"] if r["ms"] else 0
        parts = r["partitions"] if r["partitions"] else "-"
        lines.append(
            f"| {r['query']} | {r['stage']} | {r['ms']:.2f} | {speed:.1f}x | {r['scans']} | "
            f"{parts} | {r['buffers']:,} | {r['size']} |"
        )
    REPORT_PATH.parent.mkdir(exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nReport written to {REPORT_PATH}")


def main() -> None:
    engine = get_engine()
    results: list = []

    with engine.connect() as conn:
        fact_rows = conn.execute(text("SELECT COUNT(*) FROM analytics.fact_trips")).scalar()
        pg_version = conn.execute(text("SHOW server_version")).scalar()
        trip_id = conn.execute(text(
            "SELECT trip_id FROM analytics.fact_trips WHERE requested_at >= '2026-08-15' "
            "ORDER BY trip_id LIMIT 1 OFFSET 100"
        )).scalar()
    print(f"Benchmarking {fact_rows:,} rows on PostgreSQL {pg_version}. Lookup trip: {trip_id}\n")

    t0 = time.perf_counter()
    setup_flat(engine)
    print(f"Copied fact table in {time.perf_counter() - t0:.1f}s\n")

    run_stage(engine, "1. heap, no index", "bench.fact_flat", trip_id, results, size_flat(engine))

    create_indexes(engine, "fact_flat")
    run_stage(engine, "2. heap + indexes", "bench.fact_flat", trip_id, results, size_flat(engine))

    n_partitions = setup_partitioned(engine)
    run_stage(engine, "3. partitioned", "bench.fact_part", trip_id, results, size_part(engine))

    create_indexes(engine, "fact_part")
    run_stage(engine, "4. partitioned + indexes", "bench.fact_part", trip_id, results, size_part(engine))

    write_report(results, fact_rows, pg_version, n_partitions)


if __name__ == "__main__":
    main()