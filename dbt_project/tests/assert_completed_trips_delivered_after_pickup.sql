select trip_id, pickup_at, delivered_at
from {{ ref('fact_trips') }}
where is_completed
  and delivered_at < pickup_at