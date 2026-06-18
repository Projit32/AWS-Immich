import json
import os
import time

import boto3

ec2 = boto3.client("ec2")
route53 = boto3.client("route53")
ssm = boto3.client("ssm")
events = boto3.client("events")

VOLUME_ID = os.environ["VOLUME_ID"]
SPOT_LAUNCH_TEMPLATE_ID = os.environ["SPOT_LAUNCH_TEMPLATE_ID"]

HOSTED_ZONE_ID = os.environ["HOSTED_ZONE_ID"]
RECORD_NAME = os.environ["RECORD_NAME"]

STATE_PARAMETER = os.environ["STATE_PARAMETER"]
RESTORE_RULE_NAME = os.environ["RESTORE_RULE_NAME"]

INSTANCE_STATUS_TIMEOUT = 600
VOLUME_TIMEOUT = 600


def lambda_handler(event, context):

    print("=== Restore Lambda Started ===")
    print(json.dumps(event))

    state = get_state()

    if state.get("state") != "OD_ACTIVE":
        print("OD is not active. Nothing to restore.")

        return {
            "status": "nothing-to-do"
        }

    od_instance_id = state.get("activeInstanceId")

    if not od_instance_id:
        raise Exception(
            "activeInstanceId missing from state"
        )

    update_state("RESTORE_IN_PROGRESS")

    #
    # Launch Spot first
    #
    spot_instance_id = launch_spot_instance()

    wait_for_instance_running(
        spot_instance_id
    )

    #
    # Terminate OD instance
    #
    terminate_instance(
        od_instance_id
    )

    wait_for_instance_terminated(
        od_instance_id
    )

    #
    # Wait for EBS detach
    #
    wait_for_volume_available(
        VOLUME_ID
    )

    #
    # Attach EBS to Spot
    #
    attach_volume(
        instance_id=spot_instance_id,
        volume_id=VOLUME_ID
    )

    #
    # Wait until Spot instance is healthy
    #
    wait_for_instance_status_ok(
        spot_instance_id
    )

    private_ip = get_private_ip(
        spot_instance_id
    )

    update_dns(
        private_ip
    )

    disable_restore_rule()

    update_state(
        state="SPOT_ACTIVE",
        instance_id=spot_instance_id
    )

    print("=== Restore Completed Successfully ===")

    return {
        "status": "success",
        "instanceId": spot_instance_id,
        "privateIp": private_ip
    }


def get_state():

    response = ssm.get_parameter(
        Name=STATE_PARAMETER
    )

    return json.loads(
        response["Parameter"]["Value"]
    )


def update_state(state, instance_id=""):

    payload = {
        "state": state,
        "activeInstanceId": instance_id,
        "updatedAt": int(time.time())
    }

    ssm.put_parameter(
        Name=STATE_PARAMETER,
        Value=json.dumps(payload),
        Type="String",
        Overwrite=True
    )


def launch_spot_instance():

    response = ec2.run_instances(
        LaunchTemplate={
            "LaunchTemplateId": SPOT_LAUNCH_TEMPLATE_ID
        },
        MinCount=1,
        MaxCount=1
    )

    instance_id = response["Instances"][0]["InstanceId"]

    print(
        f"Spot instance launched: {instance_id}"
    )

    return instance_id


def terminate_instance(instance_id):

    print(
        f"Terminating instance: {instance_id}"
    )

    ec2.terminate_instances(
        InstanceIds=[instance_id]
    )


def wait_for_instance_running(instance_id):

    print(
        f"Waiting for {instance_id} running"
    )

    waiter = ec2.get_waiter(
        "instance_running"
    )

    waiter.wait(
        InstanceIds=[instance_id],
        WaiterConfig={
            "Delay": 5,
            "MaxAttempts": 60
        }
    )

    print(
        f"{instance_id} is running"
    )


def wait_for_instance_terminated(instance_id):

    print(
        f"Waiting for {instance_id} termination"
    )

    waiter = ec2.get_waiter(
        "instance_terminated"
    )

    waiter.wait(
        InstanceIds=[instance_id],
        WaiterConfig={
            "Delay": 5,
            "MaxAttempts": 30
        }
    )

    print(
        f"{instance_id} terminated"
    )


def wait_for_volume_available(volume_id):

    start = time.time()

    while True:

        volume = ec2.describe_volumes(
            VolumeIds=[volume_id]
        )["Volumes"][0]

        state = volume["State"]

        print(
            f"Volume state: {state}"
        )

        if state == "available":
            print(
                f"{volume_id} available"
            )
            return

        if (
            time.time() - start
            > VOLUME_TIMEOUT
        ):
            raise TimeoutError(
                f"{volume_id} did not become available"
            )

        time.sleep(5)


def attach_volume(instance_id, volume_id):

    print(
        f"Attaching {volume_id} -> {instance_id}"
    )

    ec2.attach_volume(
        VolumeId=volume_id,
        InstanceId=instance_id,
        Device="/dev/sdf"
    )

    wait_for_volume_in_use(
        volume_id
    )

    print(
        "Volume attached"
    )


def wait_for_volume_in_use(volume_id):

    while True:

        volume = ec2.describe_volumes(
            VolumeIds=[volume_id]
        )["Volumes"][0]

        if volume["State"] == "in-use":
            return

        time.sleep(3)


def wait_for_instance_status_ok(instance_id):

    print(
        f"Waiting for EC2 status checks: {instance_id}"
    )

    start = time.time()

    while True:

        response = ec2.describe_instance_status(
            InstanceIds=[instance_id]
        )

        statuses = response.get(
            "InstanceStatuses",
            []
        )

        if statuses:

            status = statuses[0]

            system_ok = (
                status["SystemStatus"]["Status"]
                == "ok"
            )

            instance_ok = (
                status["InstanceStatus"]["Status"]
                == "ok"
            )

            print(
                f"System={status['SystemStatus']['Status']} "
                f"Instance={status['InstanceStatus']['Status']}"
            )

            if system_ok and instance_ok:
                print(
                    "Status checks passed"
                )
                return

        if (
            time.time() - start
            > INSTANCE_STATUS_TIMEOUT
        ):
            raise TimeoutError(
                f"Status checks timed out for {instance_id}"
            )

        time.sleep(10)


def get_private_ip(instance_id):

    response = ec2.describe_instances(
        InstanceIds=[instance_id]
    )

    return (
        response["Reservations"][0]
        ["Instances"][0]
        ["PrivateIpAddress"]
    )


def update_dns(ip_address):

    print(
        f"Updating Route53: {RECORD_NAME} -> {ip_address}"
    )

    route53.change_resource_record_sets(
        HostedZoneId=HOSTED_ZONE_ID,
        ChangeBatch={
            "Comment": "Immich PostgreSQL Restore",
            "Changes": [
                {
                    "Action": "UPSERT",
                    "ResourceRecordSet": {
                        "Name": RECORD_NAME,
                        "Type": "A",
                        "TTL": 10,
                        "ResourceRecords": [
                            {
                                "Value": ip_address
                            }
                        ]
                    }
                }
            ]
        }
    )

    print(
        "Route53 updated"
    )


def disable_restore_rule():

    print(
        f"Disabling restore rule: {RESTORE_RULE_NAME}"
    )

    events.disable_rule(
        Name=RESTORE_RULE_NAME
    )

    print(
        "Restore rule disabled"
    )