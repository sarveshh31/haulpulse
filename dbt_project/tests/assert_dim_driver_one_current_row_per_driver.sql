select driver_id, count(*) filter (where is_current) as current_versions
from {{ ref('dim_driver') }}
group by driver_id
having count(*) filter (where is_current) <> 1