-- Bronze: raw data exactly as received
CREATE SCHEMA IF NOT EXISTS raw;

-- Silver: validated, cleaned data
CREATE SCHEMA IF NOT EXISTS staging;

-- Rejected records with the reason they failed
CREATE SCHEMA IF NOT EXISTS quarantine;

-- Gold: star schema + KPI marts (built by dbt)
CREATE SCHEMA IF NOT EXISTS analytics;

-- Pipeline run logs and audit tables
CREATE SCHEMA IF NOT EXISTS ops;