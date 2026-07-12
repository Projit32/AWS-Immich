docker run -d \
  --name immich-api \
  --restart unless-stopped \
  -p 2283:2283 \
  -e DB_HOSTNAME=backend.immich.internal \
  -e DB_PORT=5432 \
  -e DB_USERNAME=immich \
  -e DB_PASSWORD='IamBatman!01' \
  -e DB_DATABASE_NAME=immich \
  -e REDIS_HOSTNAME=backend.immich.internal \
  -e REDIS_PORT=6379 \
  -e IMMICH_WORKERS_INCLUDE=api \
  -v /mnt/immich:/usr/src/app/upload \
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



docker run -d \
  --name valkey \
  -p 6379:6379 \
  valkey/valkey:9


docker buildx build \
  --platform linux/arm64 \
  -t valkey/valkey:9 \
  --load .


docker run -d \
  --name valkey-server \
  --restart always \
  -p 6379:6379 \
  -v /data/valkey:/data \
  --cpus="0.5" \
  --memory="512m" \
  valkey/valkey:latest \
  valkey-server --save 900 1 --save 300 10 --save 60 10000 --appendonly yes


docker run \
  --name postgres \
  --restart=no \
  -p 5432:5432 \
  -e POSTGRES_USER=immich \
  -e POSTGRES_PASSWORD=Agentppp32 \
  -e POSTGRES_DB=immich \
  -v /home/ec2-user/db/data:/var/lib/postgresql/data \
  ghcr.io/immich-app/postgres:14-vectorchord0.4.3-pgvectors0.2.0@sha256:bcf63357191b76a916ae5eb93464d65c07511da41e3bf7a8416db519b40b1c23