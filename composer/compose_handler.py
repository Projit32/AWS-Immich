import json
import os
import time

import boto3

ec2 = boto3.client("ec2")
route53 = boto3.client("route53")
events = boto3.client("events")
ecs = boto3.client("ecs")
autoscaling = boto3.client("autoscaling")

VOLUME_ID = os.environ["VOLUME_ID"]

HOSTED_ZONE_ID = os.environ["HOSTED_ZONE_ID"]
RECORD_NAME = os.environ["RECORD_NAME"]

SPOT_LAUNCH_TEMPLATE_ID = os.environ["SPOT_LAUNCH_TEMPLATE_ID"]

ECS_CLUSTER_NAME = os.environ["ECS_CLUSTER_NAME"]
ECS_SERVICE_NAMES = os.environ["ECS_SERVICE_NAMES"]
SD_ASG_NAME = os.environ["SD_ASG_NAME"]

INSTANCE_STATUS_TIMEOUT = 600
VOLUME_TIMEOUT = 120


def lambda_handler(event, context):
    if bool(event.get("start")):
        start_service()
    elif bool(event.get("stop")):
        stop_service()

def start_service():
    print("Switching on ECS Services...")

    switch_ecs_services(cluster_name=ECS_CLUSTER_NAME, service_names=ECS_SERVICE_NAMES.split(","),
                               desired_count=1)

    print("ECS updated")

    print("Switching on Service Discovery ASG...")
    set_asg_desired_capacity(asg_name=SD_ASG_NAME, desired_capacity=1)

def stop_service():
    print("Switching off ECS Services...")

    switch_ecs_services(cluster_name=ECS_CLUSTER_NAME, service_names=ECS_SERVICE_NAMES.split(","),
                               desired_count=0)

    print("ECS shut down")

    print("Switching off Service Discovery ASG...")
    set_asg_desired_capacity(asg_name=SD_ASG_NAME, desired_capacity=0)

def set_asg_desired_capacity(asg_name: str, desired_capacity: int):
    """
    Updates the desired capacity of a specified Auto Scaling Group.
    """
    if not asg_name:
        print("No ASG name provided. Skipping ASG update.")
        return

    try:
        print(f"Setting ASG '{asg_name}' desired capacity to {desired_capacity}...")
        autoscaling.update_auto_scaling_group(
            AutoScalingGroupName=asg_name,
            DesiredCapacity=desired_capacity
        )
        print(f"Successfully set ASG '{asg_name}' desired capacity to {desired_capacity}.")
    except Exception as e:
        print(f"An error occurred while updating ASG '{asg_name}': {e}")

def switch_ecs_services(cluster_name: str, service_names:list[str] = list(), desired_count: int = 0):

    # Use paginator in case there are a large number of services
    paginator = ecs.get_paginator('list_services')

    try:
        for page in paginator.paginate(cluster=cluster_name):
            service_arns = page.get('serviceArns', [])

            if not service_arns:
                continue

            # The describe_services API can only process 10 services at a time
            for i in range(0, len(service_arns), 10):
                batch_arns = service_arns[i:i + 10]

                response = ecs.describe_services(
                    cluster=cluster_name,
                    services=batch_arns,
                )

                for service in response.get('services', []):
                    service_name = service['serviceName']
                    current_count = service['desiredCount']

                    if (service_name in service_names) or not service_names:

                        if current_count == desired_count:
                            print(f"Service '{service_name}' is already at desiredCount={desired_count}. Skipping.")
                            continue

                        print(f"Scaling service '{service_name}' (Current count: {current_count}) to {desired_count}...")

                        # Update the service
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