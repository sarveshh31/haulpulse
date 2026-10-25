-- Fails if the fact table and the silver layer disagree on how many trips exist
select f.n as fact_rows, s.n as silver_rows
from (select count(*) as n from {{ ref('fact_trips') }}) f
cross join (select count(*) as n from {{ source('silver', 'trips_clean') }}) s
where f.n <> s.n