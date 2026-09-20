#!/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# --- CONFIGURATION ---
ECS_CLUSTER_NAME=$1     # <-- Replace with your ECS Cluster name
ECS_SERVICE_NAME=$2       # <-- Replace with your ECS Service name
CACHE_HOST=localhost

# --- 2. EVALUATE VALKEY QUEUES ---
TOTAL_JOBS=0
QUEUES=(
    "thumbnailGeneration"
    "metadataExtraction"
    "videoConversion"
    "duplicateDetection"
    "backgroundTask"
    "smartSearch"
    "faceDetection"
    "ocr"
    "library"
    "migration"
    "sidecar"
    "search"
    "notifications"
)

for queue in "${QUEUES[@]}"; do
  WAIT=$(valkey-cli -h $CACHE_HOST LLEN immich_bull:$queue:wait 2>/dev/null || echo 0)
  PRIORITIZED=$(valkey-cli -h $CACHE_HOST ZCARD immich_bull:$queue:prioritized 2>/dev/null || echo 0)
  ACTIVE=$(valkey-cli -h $CACHE_HOST LLEN immich_bull:$queue:active 2>/dev/null || echo 0)

  TOTAL_JOBS=$((TOTAL_JOBS + WAIT + PRIORITIZED + ACTIVE))
done

echo "Total Microservices Jobs: $TOTAL_JOBS"

# --- 3. SCALE ECS SERVICE ---
# Fetch the current desired count from ECS
CURRENT_DESIRED=$(aws ecs describe-services --cluster "$ECS_CLUSTER_NAME" --services "$ECS_SERVICE_NAME" --query "services[0].desiredCount" --output text 2>/dev/null)

if [ -z "$CURRENT_DESIRED" ]; then
    echo "Error: Could not retrieve current desired count for ECS service $ECS_SERVICE_NAME."
    exit 1
fi

echo "Current ECS Desired Count: $CURRENT_DESIRED"

if [ "$TOTAL_JOBS" -gt 0 ]; then
    if [ "$CURRENT_DESIRED" -eq 0 ]; then
        echo "Jobs found in queue. Scaling up ECS service to 1..."
        aws ecs update-service --cluster "$ECS_CLUSTER_NAME" --service "$ECS_SERVICE_NAME" --desired-count 1 --query "service.desiredCount" --output text > /dev/null
    else
        echo "Jobs found, but ECS service is already scaled up (Desired Count: $CURRENT_DESIRED). Doing nothing."
    fi
else
    if [ "$CURRENT_DESIRED" -gt 0 ]; then
        echo "No jobs in queue. Scaling down ECS service to 0..."
        aws ecs update-service --cluster "$ECS_CLUSTER_NAME" --service "$ECS_SERVICE_NAME" --desired-count 0 --query "service.desiredCount" --output text > /dev/null
    else
        echo "No jobs in queue and ECS service is already scaled down to 0. Doing nothing."
    fi
fi