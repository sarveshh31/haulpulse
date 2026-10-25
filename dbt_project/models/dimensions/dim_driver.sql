-- SCD Type 2: one row per driver per version, built from the dbt snapshot
select
    md5(driver_id || '|' || dbt_valid_from::text)        as driver_key,
    driver_id,
    driver_name,
    city,
    vehicle_type,
    vehicle_number,
    rating,
    joined_date,
    dbt_valid_from                                       as valid_from,
    coalesce(dbt_valid_to, timestamp '9999-12-31')       as valid_to,
    dbt_valid_to is null                                 as is_current
from {{ ref('drivers_snapshot') }}