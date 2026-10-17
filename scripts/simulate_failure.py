#!/usr/bin/env python3
"""
simulate_failure.py - Multi-AZ Network Reliability Simulator (Terraform version)

Breaks connectivity from the ALB to the ECS tasks by revoking the ingress rule
on the service security group, then watches while the system reacts:

    ALB marks targets unhealthy
      -> CloudWatch alarm fires
        -> SNS sends an email and triggers the remediation Lambda
          -> Lambda forces a new ECS deployment

Unlike the CloudFormation version, this script does NOT restore the rule.
The rule is managed by Terraform, so recovery is `terraform apply`:
Terraform notices the missing rule (drift) and creates it again.

Requires: boto3, Terraform on PATH, an AWS profile (default: nrst-deployer),
and the infrastructure already applied (the script reads `terraform output`).
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import boto3

DEFAULT_PROJECT = "nrst"
DEFAULT_PROFILE = "nrst-deployer"
DEFAULT_REGION = "eu-north-1"
DEFAULT_PORT = 80
DEFAULT_OBSERVE_SECONDS = 180
POLL_INTERVAL = 15


def terraform_outputs(tf_dir: Path) -> dict:
    """Read all outputs from the Terraform state as {name: value}."""
    result = subprocess.run(
        ["terraform", "output", "-json"],
        cwd=tf_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.exit(f"'terraform output' failed in {tf_dir}:\n{result.stderr}")
    return {name: item["value"] for name, item in json.loads(result.stdout).items()}


def find_ingress_rule(ec2_client, security_group_id: str, port: int):
    """Return the ingress rule on this security group for the given port, or None."""
    response = ec2_client.describe_security_groups(GroupIds=[security_group_id])
    for perm in response["SecurityGroups"][0]["IpPermissions"]:
        if perm.get("FromPort") == port and perm.get("ToPort") == port:
            return perm
    return None


def print_target_health(elbv2_client, target_group_arn: str):
    resp = elbv2_client.describe_target_health(TargetGroupArn=target_group_arn)
    for t in resp["TargetHealthDescriptions"]:
        target = t["Target"]["Id"]
        state = t["TargetHealth"]["State"]
        reason = t["TargetHealth"].get("Reason", "")
        print(f"    {target}: {state} {('(' + reason + ')') if reason else ''}")


def print_alarm_state(cloudwatch_client, alarm_name: str):
    alarms = cloudwatch_client.describe_alarms(AlarmNames=[alarm_name])["MetricAlarms"]
    state = alarms[0]["StateValue"] if alarms else "NOT FOUND"
    print(f"    alarm {alarm_name}: {state}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=DEFAULT_PROJECT,
                        help="Resource name prefix (default: nrst)")
    parser.add_argument("--profile", default=DEFAULT_PROFILE,
                        help="AWS CLI profile (default: nrst-deployer)")
    parser.add_argument("--region", default=DEFAULT_REGION,
                        help="AWS region (default: eu-north-1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help="Container port to break (default: 80)")
    parser.add_argument("--observe-seconds", type=int, default=DEFAULT_OBSERVE_SECONDS,
                        help="How long to watch after breaking (default: 180)")
    parser.add_argument("--terraform-dir", type=Path,
                        default=Path(__file__).resolve().parent.parent,
                        help="Folder with the Terraform code (default: parent of scripts/)")
    args = parser.parse_args()

    print("== Multi-AZ Network Reliability Simulator (Terraform) - Failure Injection ==\n")

    print("Reading Terraform outputs...")
    outputs = terraform_outputs(args.terraform_dir)
    sg_id = outputs["service_security_group_id"]
    tg_arn = outputs["target_group_arn"]
    print(f"  Service security group: {sg_id}")
    print(f"  Target group:           {tg_arn}\n")

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    ec2 = session.client("ec2")
    elbv2 = session.client("elbv2")
    cloudwatch = session.client("cloudwatch")
    alarm_name = f"{args.project}-unhealthy-hosts"

    rule = find_ingress_rule(ec2, sg_id, args.port)
    if rule is None:
        sys.exit(f"No ingress rule for port {args.port} on {sg_id}. "
                 f"Already revoked by a previous run? Run 'terraform apply' to restore it.")

    print("State before injection:")
    print_target_health(elbv2, tg_arn)
    print_alarm_state(cloudwatch, alarm_name)

    input("\nPress Enter to BREAK connectivity (revoke the ingress rule)...")

    ec2.revoke_security_group_ingress(GroupId=sg_id, IpPermissions=[rule])
    print(f"\n[{time.strftime('%H:%M:%S')}] Ingress rule revoked. "
          f"ALB traffic to the ECS tasks on port {args.port} is now blocked.\n")

    print(f"Watching for {args.observe_seconds}s. Also check:")
    print("  - your email for the SNS alert")
    print(f"  - CloudWatch > Alarms > {alarm_name}")
    print(f"  - CloudWatch > Log groups > /aws/lambda/{args.project}-remediation\n")

    elapsed = 0
    while elapsed < args.observe_seconds:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        print(f"[{elapsed}s]")
        print_target_health(elbv2, tg_arn)
        print_alarm_state(cloudwatch, alarm_name)

    print(f"\n[{time.strftime('%H:%M:%S')}] Observation finished. The rule is STILL REVOKED.")
    print("To see the drift:   terraform plan")
    print("To restore it:      terraform apply")


if __name__ == "__main__":
    main()
