#!/bin/bash
set -eu
docker rmi cities || true
docker build . -t cities
docker run --rm -v "$(pwd):/out" -ti cities 
docker rmi cities
ls -t data*.csv|head -n 2
