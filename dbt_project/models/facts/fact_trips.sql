{{
    config(
        materialized='incremental',
        unique_key='trip_id',
        incremental_strategy='delete+insert',
        on_schema_change='append_new_columns'
    )
}}

with trips as (

    select * from {{ ref('stg_trips') }}

    {% if is_incremental() %}
    -- Watermark on ingestion time (loaded_at), NOT business time (updated_at),
    -- so late-arriving corrections are never skipped.
    where loaded_at > (select max(loaded_at) from {{ this }})
    {% endif %}

)

select
    t.trip_id,
    to_char(t.trip_date, 'YYYYMMDD')::int as date_key,
    c.city_key,
    v.vehicle_key,
    d.driver_key,
    t.customer_id,

    t.requested_at,
    t.pickup_at,
    t.delivered_at,
    t.request_hour,

    t.status,
    t.is_completed,
    t.is_cancelled,
    t.is_no_driver,
    t.payment_mode,
    t.cancellation_reason,

    t.distance_km,
    t.eta_minutes,
    t.wait_minutes,
    t.trip_duration_minutes,
    case when t.is_completed then t.trip_duration_minutes <= t.eta_minutes end as is_on_time,

    t.fare_amount,
    case when t.is_completed and t.distance_km > 0
         then round(t.fare_amount / t.distance_km, 2) end as fare_per_km,

    t.source_file,
    t.updated_at,
    t.loaded_at
from trips t
left join {{ ref('dim_city') }}    c on t.city = c.city
left join {{ ref('dim_vehicle') }} v on t.vehicle_type = v.vehicle_type
left join {{ ref('dim_driver') }}  d
       on t.driver_id    = d.driver_id
      and t.requested_at >= d.valid_from
      and t.requested_at <  d.valid_to