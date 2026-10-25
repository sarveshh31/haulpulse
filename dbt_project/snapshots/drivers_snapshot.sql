{% snapshot drivers_snapshot %}

{{
    config(
        target_schema='analytics',
        unique_key='driver_id',
        strategy='timestamp',
        updated_at='updated_at'
    )
}}

select
    driver_id,
    driver_name,
    city,
    vehicle_type,
    vehicle_number,
    rating,
    joined_date,
    updated_at
from {{ source('silver', 'drivers_clean') }}

{% endsnapshot %}