-- Grain: one row per trip date per city
select
    d.date_key,
    d.full_date as trip_date,
    c.city,

    count(*)                                         as total_trips,
    count(*) filter (where f.is_completed)           as completed_trips,
    count(*) filter (where f.is_cancelled)           as cancelled_trips,
    count(*) filter (where f.is_no_driver)           as no_driver_trips,

    round(count(*) filter (where f.is_cancelled)::numeric / nullif(count(*), 0), 4)  as cancellation_rate,
    round(count(*) filter (where f.is_no_driver)::numeric / nullif(count(*), 0), 4)  as no_driver_rate,

    count(*) filter (where f.is_on_time)             as on_time_trips,
    round(
        count(*) filter (where f.is_on_time)::numeric
        / nullif(count(*) filter (where f.is_completed), 0), 4
    )                                                as on_time_rate,

    coalesce(sum(f.fare_amount) filter (where f.is_completed), 0)           as gross_revenue,
    round(avg(f.fare_amount) filter (where f.is_completed), 2)              as avg_fare,
    round(avg(f.distance_km) filter (where f.is_completed), 2)              as avg_distance_km,
    round(
        sum(f.fare_amount) filter (where f.is_completed)
        / nullif(sum(f.distance_km) filter (where f.is_completed), 0), 2
    )                                                as revenue_per_km,
    round(avg(f.wait_minutes), 1)                    as avg_wait_minutes
from {{ ref('fact_trips') }} f
join {{ ref('dim_date') }} d on f.date_key = d.date_key
join {{ ref('dim_city') }} c on f.city_key = c.city_key
group by d.date_key, d.full_date, c.city