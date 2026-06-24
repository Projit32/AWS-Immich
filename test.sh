docker run -d \
  --name immich-api \
  --restart unless-stopped \
  -p 2283:2283 \
  -e DB_HOSTNAME=44.197.3.132 \
  -e DB_PORT=5432 \
  -e DB_USERNAME=immich \
  -e DB_PASSWORD='SuperPassword^69' \
  -e DB_DATABASE_NAME=immich \
  -e REDIS_HOSTNAME=192.168.1.19 \
  -e REDIS_PORT=6379 \
  -e IMMICH_WORKERS_INCLUDE=api \
  -v /Users/projit32/Desktop/uploads:/usr/src/app/upload \
  ghcr.io/immich-app/immich-server:release


  docker run -d \
  --name immich-microservices \
  --restart unless-stopped \
  -e DB_HOSTNAME=44.197.3.132 \
  -e DB_PORT=5432 \
  -e DB_USERNAME=immich \
  -e DB_PASSWORD='SuperPassword^69' \
  -e DB_DATABASE_NAME=immich \
  -e REDIS_HOSTNAME=192.168.1.19 \
  -e REDIS_PORT=6379 \
  -e IMMICH_WORKERS_EXCLUDE=api \
  -v /Users/projit32/Desktop/uploads:/usr/src/app/upload \
  ghcr.io/immich-app/immich-server:release

docker run -d \
  --name immich \
  --restart unless-stopped \
  -p 2283:2283 \
  -e DB_HOSTNAME=172.31.27.107 \
  -e DB_PORT=5432 \
  -e DB_USERNAME=immich \
  -e DB_PASSWORD='SuperPassword^69' \
  -e DB_DATABASE_NAME=immich \
  -e REDIS_HOSTNAME=master.immich-cache-prod.e1vtkg.use1.cache.amazonaws.com \
  -e REDIS_PORT=6379 \
  -v /mnt/immich/uploads:/usr/src/app/upload \
  ghcr.io/immich-app/immich-server:release