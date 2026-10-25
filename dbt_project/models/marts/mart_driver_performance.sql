-- Grain: one row per driver (all SCD versions rolled up); attributes come from the CURRENT version
-- Utilization assumes an 8-hour (480 min) working day, capped at 100%
with agg as (
    select
        dd.driver_id,
        count(*)                                                            as trips_assigned,
        count(*) filter (where f.is_completed)                              as completed_trips,
        count(*) filter (where f.status = 'CANCELLED_BY_DRIVER')            as driver_cancellations,
        count(*) filter (where f.is_on_time)                                as on_time_trips,
        coalesce(sum(f.fare_amount) filter (where f.is_completed), 0)       as total_earnings,
        coalesce(sum(f.trip_duration_minutes) filter (where f.is_completed), 0) as busy_minutes,
        count(distinct f.date_key) filter (where f.is_completed)            as active_days
    from {{ ref('fact_trips') }} f
    join {{ ref('dim_driver') }} dd on f.driver_key = dd.driver_key
    group by dd.driver_id
)

select
    d.driver_key,
    d.driver_id,
    d.driver_name,
    d.city,
    d.vehicle_type,
    d.rating,
    a.trips_assigned,
    a.completed_trips,
    a.driver_cancellations,
    round(a.completed_trips::numeric / nullif(a.trips_assigned, 0), 4)  as completion_rate,
    round(a.on_time_trips::numeric / nullif(a.completed_trips, 0), 4)   as on_time_rate,
    a.total_earnings,
    a.active_days,
    round(a.completed_trips::numeric / nullif(a.active_days, 0), 2)     as trips_per_active_day,
    least(1.0, round(a.busy_minutes / nullif(a.active_days * 480.0, 0), 4)) as utilization_rate,
    rank() over (partition by d.city order by a.completed_trips desc)   as city_rank
from agg a
join {{ ref('dim_driver') }} d on a.driver_id = d.driver_id and d.is_current