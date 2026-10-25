with days as (
    select generate_series(date '2026-01-01', date '2027-12-31', interval '1 day')::date as full_date
)

select
    to_char(full_date, 'YYYYMMDD')::int           as date_key,
    full_date,
    extract(year from full_date)::int             as year,
    extract(quarter from full_date)::int          as quarter,
    extract(month from full_date)::int            as month,
    to_char(full_date, 'FMMonth')                 as month_name,
    extract(day from full_date)::int              as day_of_month,
    extract(isodow from full_date)::int           as iso_day_of_week,
    to_char(full_date, 'FMDay')                   as day_name,
    extract(isodow from full_date) in (6, 7)      as is_weekend,
    extract(week from full_date)::int             as iso_week
from days