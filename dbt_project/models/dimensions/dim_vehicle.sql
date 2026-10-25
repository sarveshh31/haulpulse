select
    md5(vehicle_type) as vehicle_key,
    vehicle_type,
    vehicle_label,
    capacity_kg
from {{ ref('vehicle_reference') }}