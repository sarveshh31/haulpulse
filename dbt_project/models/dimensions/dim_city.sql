select
    md5(city) as city_key,
    city,
    state,
    region,
    tier
from {{ ref('city_reference') }}