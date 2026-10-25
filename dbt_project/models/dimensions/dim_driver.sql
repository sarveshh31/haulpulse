select
    md5(driver_id) as driver_key,
    driver_id,
    driver_name,
    city,
    vehicle_type,
    vehicle_number,
    rating,
    joined_date
from {{ ref('stg_drivers') }}