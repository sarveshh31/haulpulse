-- Grain: one row per city per hour of day (aggregated over all days in the data)
with hourly as (
    select
        c.city,
        f.request_hour                                   as hour_of_day,
        count(*)                                         as total_trips,
        count(distinct f.date_key)                       as days_observed,
        count(*) filter (where f.is_cancelled)           as cancelled_trips,
        count(*) filter (where f.is_no_driver)           as no_driver_trips,
        round(avg(f.fare_amount) filter (where f.is_completed), 2) as avg_fare
    from {{ ref('fact_trips') }} f
    join {{ ref('dim_city') }} c on f.city_key = c.city_key
    group by c.city, f.request_hour
)

select
    city,
    hour_of_day,
    total_trips,
    days_observed,
    round(total_trips::numeric / nullif(days_observed, 0), 1)       as avg_trips_per_day,
    round(cancelled_trips::numeric / nullif(total_trips, 0), 4)     as cancellation_rate,
    round(no_driver_trips::numeric / nullif(total_trips, 0), 4)     as no_driver_rate,
    avg_fare,
    row_number() over (partition by city order by total_trips desc) as demand_rank,
    row_number() over (partition by city order by total_trips desc) <= 3 as is_peak_hour
from hourly