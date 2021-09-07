#!/bin/bash
set -eux

[ ! -d /out ] && echo 'Please mount /out: e.g. with -v "/path/to/local/data:/out"' && exit 1

cd /scripts

export POSTGRES_USER="${PGUSER:-postgres}"
export POSTGRES_DATABASE="${PGDATABASE:-postgres}"
export POSTGRES_PASWORD=12345678
export POSTGRES_HOST_AUTH_METHOD=trust

/usr/local/bin/docker-entrypoint.sh postgres &

psql=( psql -U "$POSTGRES_USER" -d "$POSTGRES_DATABASE" -v ON_ERROR_STOP=1 )

wget --progress=dot:giga -O data.osm.pbf http://download.geofabrik.de/russia-latest.osm.pbf
osmium tags-filter data.osm.pbf w/highway place -o fdata.osm.pbf
rm data.osm.pbf

for i in `seq 1 120`; do
  echo "Waiting for PostgreSQL start, attempt $i..."
  ${psql[@]} -c 'select 1;' && break
  sleep 1
done

osm2pgsql --slim --drop --number-processes 4 -G --style=highways-and-places.style \
    -U ${POSTGRES_USER} -d ${POSTGRES_DATABASE} fdata.osm.pbf

DATE=$(date -d yesterday +%y%m%d_%H%M)
"${psql[@]}" -f post_import.sql
"${psql[@]}" -f data_center.sql > /out/data_center_$DATE.csv
"${psql[@]}" -f data_overall.sql > /out/data_overall_$DATE.csv
