-- Two versions of the same driver must never be valid at the same time
select a.driver_id, a.valid_from, b.valid_from as overlapping_from
from {{ ref('dim_driver') }} a
join {{ ref('dim_driver') }} b
  on a.driver_id = b.driver_id
 and a.driver_key <> b.driver_key
 and a.valid_from < b.valid_to
 and b.valid_from < a.valid_to