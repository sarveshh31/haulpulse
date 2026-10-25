select
    driver_id,
    driver_name,
    city,
    vehicle_type,
    vehicle_number,
    rating,
    joined_date,
    updated_at,
    loaded_at
from {{ source('silver', 'drivers_clean') }}