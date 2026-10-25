# HaulPulse query benchmarks

- Generated: 2026-10-26 00:18
- Table: `fact_trips` copy, **1,016,628 rows**, 8 monthly partitions in the partitioned stages
- Engine: 15.18 (Debian 15.18-1.pgdg13+1) (Docker, laptop, default config)
- Method: `EXPLAIN (ANALYZE, BUFFERS)`, 2 warm-ups, median of 7 runs

| Query | Stage | Median ms | Speedup vs stage 1 | Scan type | Partitions scanned | Buffers | Total size |
|---|---|---:|---:|---|---:|---:|---|
| Q1 city revenue, 1 week | 1. heap, no index | 54.57 | 1.0x | Seq Scan | - | 37,674 | 293 MB |
| Q2 all cities, 1 month | 1. heap, no index | 65.89 | 1.0x | Seq Scan | - | 37,578 | 293 MB |
| Q3 single trip lookup | 1. heap, no index | 63.68 | 1.0x | Seq Scan | - | 37,562 | 293 MB |
| Q1 city revenue, 1 week | 2. heap + indexes | 3.56 | 15.3x | Bitmap Heap Scan, Bitmap Index Scan | - | 1,288 | 420 MB |
| Q2 all cities, 1 month | 2. heap + indexes | 48.61 | 1.4x | Bitmap Heap Scan, Bitmap Index Scan | - | 8,693 | 420 MB |
| Q3 single trip lookup | 2. heap + indexes | 0.02 | 3032.4x | Index Scan | - | 4 | 420 MB |
| Q1 city revenue, 1 week | 3. partitioned | 13.86 | 3.9x | Seq Scan | 1 | 5,502 | 294 MB |
| Q2 all cities, 1 month | 3. partitioned | 36.44 | 1.8x | Seq Scan | 1 | 5,504 | 294 MB |
| Q3 single trip lookup | 3. partitioned | 71.10 | 0.9x | Seq Scan | 8 | 37,536 | 294 MB |
| Q1 city revenue, 1 week | 4. partitioned + indexes | 13.03 | 4.2x | Index Scan | 1 | 33,511 | 421 MB |
| Q2 all cities, 1 month | 4. partitioned + indexes | 43.85 | 1.5x | Seq Scan | 1 | 5,504 | 421 MB |
| Q3 single trip lookup | 4. partitioned + indexes | 0.09 | 723.6x | Index Scan | 8 | 24 | 421 MB |
