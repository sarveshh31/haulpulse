select 'mart_daily_kpis' as model, trip_date::text as record_key
from {{ ref('mart_daily_kpis') }}
where cancellation_rate not between 0 and 1
   or no_driver_rate    not between 0 and 1
   or on_time_rate      not between 0 and 1

union all

select 'mart_driver_performance' as model, driver_id as record_key
from {{ ref('mart_driver_performance') }}
where completion_rate  not between 0 and 1
   or on_time_rate     not between 0 and 1
   or utilization_rate not between 0 and 1