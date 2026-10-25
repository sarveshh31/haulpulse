select trip_id, fare_amount
from {{ ref('fact_trips') }}
where fare_amount < 0