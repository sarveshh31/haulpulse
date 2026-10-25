-- Grain check: exactly one row per date per city
select trip_date, city, count(*) as n
from {{ ref('mart_daily_kpis') }}
group by trip_date, city
having count(*) > 1