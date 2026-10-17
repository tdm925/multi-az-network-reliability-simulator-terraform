import json
import os

import boto3

ecs = boto3.client("ecs")


def handler(event, context):
    cluster = os.environ["CLUSTER_NAME"]
    service = os.environ["SERVICE_NAME"]

    print(f"Remediation triggered for {service} in {cluster}")
    print(f"Event: {json.dumps(event)}")

    response = ecs.update_service(
        cluster=cluster,
        service=service,
        forceNewDeployment=True,
    )

    print(f"Forced new deployment: {response['service']['deployments']}")

    return {
        "statusCode": 200,
        "body": f"Forced redeployment of {service}",
    }
    