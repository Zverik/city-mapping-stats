FROM postgis/postgis:13-master

RUN apt-get update && apt-get install -y --no-install-recommends osm2pgsql wget

COPY ./scripts /scripts

CMD ["/scripts/process.sh"]
