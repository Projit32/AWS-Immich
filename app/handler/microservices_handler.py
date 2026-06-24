import os
import boto3
from redis import Redis

ecs = boto3.client("ecs")
ssm = boto3.client("ssm")

REDIS_HOST = os.environ["REDIS_HOST"]
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))

ECS_CLUSTER = os.environ["ECS_CLUSTER"]
WORKER_SERVICE = os.environ["WORKER_SERVICE"]

IDLE_THRESHOLD_MINUTES = int(
    os.environ.get("IDLE_THRESHOLD_MINUTES", "10")
)

IDLE_COUNTER_PARAMETER = os.environ[
    "IDLE_COUNTER_PARAMETER"
]


def get_idle_counter() -> int:
    try:
        response = ssm.get_parameter(
            Name=IDLE_COUNTER_PARAMETER
        )
        return int(response["Parameter"]["Value"])
    except ssm.exceptions.ParameterNotFound:
        return 0


def save_idle_counter(value: int) -> None:
    ssm.put_parameter(
        Name=IDLE_COUNTER_PARAMETER,
        Value=str(value),
        Type="String",
        Overwrite=True
    )


def get_worker_desired_count() -> int:
    response = ecs.describe_services(
        cluster=ECS_CLUSTER,
        services=[WORKER_SERVICE]
    )

    services = response["services"]

    if not services:
        raise RuntimeError(
            f"Service {WORKER_SERVICE} not found"
        )

    return services[0]["desiredCount"]


def set_worker_desired_count(value: int) -> None:
    ecs.update_service(
        cluster=ECS_CLUSTER,
        service=WORKER_SERVICE,
        desiredCount=value
    )


def get_queue_depth(redis_client: Redis) -> int:
    """
    Calculate total BullMQ work outstanding.
    """

    total = 0

    for key in redis_client.scan_iter("bull:*"):

        key_name = key.decode() if isinstance(key, bytes) else key

        try:
            if key_name.endswith(":wait"):
                total += redis_client.llen(key)

            elif key_name.endswith(":active"):
                total += redis_client.scard(key)

            elif key_name.endswith(":delayed"):
                total += redis_client.zcard(key)

        except Exception as exc:
            print(
                f"Failed reading {key_name}: {exc}"
            )

    return total


def lambda_handler(event, context):

    redis_client = Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        decode_responses=False
    )

    queue_depth = get_queue_depth(redis_client)

    print(f"Queue depth: {queue_depth}")

    current_desired = get_worker_desired_count()

    if queue_depth > 0:

        save_idle_counter(0)

        if current_desired == 0:
            print("Scaling worker service to 1")

            set_worker_desired_count(1)

        return {
            "action": "scale_up",
            "queue_depth": queue_depth,
            "desired_count": 1
        }

    idle_counter = get_idle_counter() + 1

    save_idle_counter(idle_counter)

    if idle_counter >= IDLE_THRESHOLD_MINUTES:

        if current_desired != 0:

            print(
                f"Scaling worker service to 0 "
                f"after {idle_counter} minutes idle"
            )

            set_worker_desired_count(0)

        return {
            "action": "scale_down",
            "idle_minutes": idle_counter,
            "desired_count": 0
        }

    return {
        "action": "idle",
        "idle_minutes": idle_counter,
        "queue_depth": 0
    }