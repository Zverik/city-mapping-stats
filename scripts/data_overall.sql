copy (
with data as (
select city.name as city,
  sum(st_length(st_transform(r.way, 4326)::geography)) as len,
  sum(st_length(st_transform(r.way, 4326)::geography)) filter (where r.lanes is not null or r."lanes:forward" is not null or r."lanes:backward" is not null) as len_lanes,
  sum(st_length(st_transform(r.way, 4326)::geography)) filter (where r.maxspeed is not null or r."maxspeed:forward" is not null or r."maxspeed:backward" is not null) as len_speed
from planet_osm_polygon city
left join planet_osm_line r on st_intersects(city.way, r.way)
where city.place = 'city' and r.is_road
group by 1
), points as (
select city.name as city,
  count(*) filter (where p.highway = 'crossing') as cnt_crossings,
  count(*) filter (where p.highway = 'crossing' and p.crossing = 'traffic_signals') as cnt_crossings_signals,
  count(*) filter (where p.highway = 'crossing' and p.crossing in ('marked', 'uncontrolled', 'zebra')) as cnt_crossings_marked,
  count(*) filter (where p.traffic_calming in ('bump', 'hump', 'table')) as cnt_bumps
from planet_osm_polygon city
left join planet_osm_point p on st_contains(city.way, p.way)
where city.place = 'city'
group by 1
)
select city,
  round(len/1000) as len_km,
  round((100*len_lanes/len)::numeric, 2) as perc_lanes,
  round((100*len_speed/len)::numeric, 2) as perc_speed,
  round((cnt_crossings / len * 1000)::numeric, 4) as crossings_per_km,
  round((cnt_crossings_signals / len * 1000)::numeric, 4) as signals_per_km,
  round((cnt_crossings_marked / len * 1000)::numeric, 4) as marked_per_km,
  round((cnt_bumps / len * 1000)::numeric, 4) as bumps_per_km
from data left join points using (city)
order by city
-- order by len_km desc limit 10
) to stdout (format csv, header);
