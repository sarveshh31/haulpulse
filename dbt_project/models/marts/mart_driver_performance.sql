-- Grain: one row per driver who was assigned at least one trip
-- Utilization assumes an 8-hour (480 min) working day, capped at 100%
with agg as (
    select
        driver_key,
        count(*)                                                        as trips_assigned,
        count(*) filter (where is_completed)                            as completed_trips,
        count(*) filter (where status = 'CANCELLED_BY_DRIVER')          as driver_cancellations,
        count(*) filter (where is_on_time)                              as on_time_trips,
        coalesce(sum(fare_amount) filter (where is_completed), 0)       as total_earnings,
        coalesce(sum(trip_duration_minutes) filter (where is_completed), 0) as busy_minutes,
        count(distinct date_key) filter (where is_completed)            as active_days
    from {{ ref('fact_trips') }}
    where driver_key is not null
    group by driver_key
)

select
    a.driver_key,
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
join {{ ref('dim_driver') }} d on a.driver_key = d.driver_key