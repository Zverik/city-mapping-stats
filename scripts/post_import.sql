alter table planet_osm_line add column is_road boolean not null default false;
update planet_osm_line set is_road = true where highway in (
  'residential', 'unclassified', 'tertiary', 'secondary', 'primary', 'trunk', 'motorway',
  'secondary_link', 'primary_link', 'tertiary_link', 'trunk_link', 'motorway_link'
);
