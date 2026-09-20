import json
import os
import boto3

ec2 = boto3.client("ec2")
route53 = boto3.client("route53")
ecs = boto3.client("ecs")
autoscaling = boto3.client("autoscaling")

VOLUME_ID = os.environ["VOLUME_ID"]
HOSTED_ZONE_ID = os.environ["HOSTED_ZONE_ID"]
RECORD_NAME = os.environ["RECORD_NAME"]
ECS_CLUSTER_NAME = os.environ["ECS_CLUSTER_NAME"]
ECS_SERVICE_NAMES = os.environ["ECS_SERVICE_NAMES"]


def lambda_handler(event, context):
    print("=== ASG Lifecycle Orchestrator Lambda Started ===")
    print(json.dumps(event))

    detail = event.get("detail", {})
    transition = detail.get("LifecycleTransition")
    instance_id = detail.get("EC2InstanceId")
    token = detail.get("LifecycleActionToken")
    asg_name = detail.get("AutoScalingGroupName")
    hook_name = detail.get("LifecycleHookName")

    if not transition:
        print("No LifecycleTransition found in event. Exiting.")
        return {"status": "ignored"}

    service_names_list = ECS_SERVICE_NAMES.split(",") if ECS_SERVICE_NAMES else []

    try:
        if transition == "autoscaling:EC2_INSTANCE_TERMINATING":
            print(f"Handling TERMINATING event for instance: {instance_id}")

            # 1. Scale down ECS services to drain connections
            switch_ecs_services(
                cluster_name=ECS_CLUSTER_NAME,
                service_names=[],
                desired_count=0
            )

            # 2. Tell ASG to continue termination (this releases the EBS volume)
            complete_lifecycle_action(token, asg_name, hook_name, "CONTINUE")

        elif transition == "autoscaling:EC2_INSTANCE_LAUNCHING":
            print(f"Handling LAUNCHING event for instance: {instance_id}")

            # 1. Wait for EBS to detach from the old terminating instance
            wait_for_volume_available(VOLUME_ID)

            # 2. Attach EBS to the new instance
            attach_volume(instance_id, VOLUME_ID)

            # 3. Wait for EC2 instance to be fully healthy and UserData to finish
            wait_for_instance_status_ok(instance_id)

            # 4. Update Route 53 with the new instance's Private IP
            private_ip = get_ip(instance_id)
            update_dns(private_ip)

            # 5. Turn ECS services back on
            switch_ecs_services(
                cluster_name=ECS_CLUSTER_NAME,
                service_names=service_names_list,
                desired_count=1
            )

            # 6. Tell ASG to put the instance InService
            complete_lifecycle_action(token, asg_name, hook_name, "CONTINUE")

        else:
            print(f"Unhandled transition: {transition}")

        return {"status": "success", "transition": transition, "instanceId": instance_id}

    except Exception as e:
        print(f"Error processing lifecycle hook: {e}")
        # If launching fails/times out, tell the ASG to abandon this instance
        if transition == "autoscaling:EC2_INSTANCE_LAUNCHING":
            complete_lifecycle_action(token, asg_name, hook_name, "ABORT")
        raise e


def complete_lifecycle_action(token, asg_name, hook_name, result):
    print(f"Completing lifecycle hook {hook_name} for ASG {asg_name} with result {result}")
    autoscaling.complete_lifecycle_action(
        LifecycleHookName=hook_name,
        AutoScalingGroupName=asg_name,
        LifecycleActionToken=token,
        LifecycleActionResult=result
    )


def wait_for_volume_available(volume_id):
    print(f"Waiting for volume {volume_id} to become available...")
    waiter = ec2.get_waiter("volume_available")
    waiter.wait(
        VolumeIds=[volume_id],
        WaiterConfig={
            "Delay": 5,
            "MaxAttempts": 60  # 5 minutes timeout
        }
    )
    print(f"{volume_id} is available")


def attach_volume(instance_id, volume_id):
    print(f"Attaching volume {volume_id} to instance {instance_id}")
    ec2.attach_volume(
        VolumeId=volume_id,
        InstanceId=instance_id,
        Device="/dev/xvdbb"
    )

    print(f"Waiting for volume {volume_id} to be in-use...")
    waiter = ec2.get_waiter("volume_in_use")
    waiter.wait(
        VolumeIds=[volume_id],
        WaiterConfig={
            "Delay": 3,
            "MaxAttempts": 40  # 2 minutes timeout
        }
    )
    print("Volume attached successfully")


def wait_for_instance_status_ok(instance_id):
    print(f"Waiting for EC2 status checks on {instance_id}")
    waiter = ec2.get_waiter("instance_status_ok")
    waiter.wait(
        InstanceIds=[instance_id],
        WaiterConfig={
            "Delay": 10,
            "MaxAttempts": 60  # 10 minutes timeout
        }
    )
    print("Status checks passed")


def get_ip(instance_id):
    response = ec2.describe_instances(InstanceIds=[instance_id])
    return response["Reservations"][0]["Instances"][0]["PrivateIpAddress"]


def update_dns(ip_address):
    print(f"Updating Route53: {RECORD_NAME} -> {ip_address}")
    route53.change_resource_record_sets(
        HostedZoneId=HOSTED_ZONE_ID,
        ChangeBatch={
            "Comment": "Immich PostgreSQL-Cache ASG Failover",
            "Changes": [
                {
                    "Action": "UPSERT",
                    "ResourceRecordSet": {
                        "Name": RECORD_NAME,
                        "Type": "A",
                        "TTL": 10,
                        "ResourceRecords": [{"Value": ip_address}]
                    }
                }
            ]
        }
    )
    print("Route53 updated")


def switch_ecs_services(cluster_name: str, service_names: list, desired_count: int = 0):
    paginator = ecs.get_paginator('list_services')

    try:
        for page in paginator.paginate(cluster=cluster_name):
            service_arns = page.get('serviceArns', [])
            if not service_arns:
                continue

            for i in range(0, len(service_arns), 10):
                batch_arns = service_arns[i:i + 10]
                response = ecs.describe_services(cluster=cluster_name, services=batch_arns)

                for service in response.get('services', []):
                    service_name = service['serviceName']
                    current_count = service['desiredCount']

                    if not service_names or service_name in service_names:
                        if current_count == desired_count:
                            print(f"Service '{service_name}' is already at desiredCount={desired_count}. Skipping.")
                            continue

                        print(
                            f"Scaling service '{service_name}' (Current count: {current_count}) to {desired_count}...")

                        ecs.update_service(
                            cluster=cluster_name,
                            service=service_name,
                            desiredCount=desired_count
                        )
                        print(f"Successfully switched '{service_name}'.")
                    else:
                        print(f"Service '{service_name}' is not supposed to change.")

    except Exception as e:
        print(f"An error occurred switching service: {e}")