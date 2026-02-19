#!/usr/bin/env python3
"""
CloudFormation deployment helper for the DynamoDB GSI Export stack.

Usage:
    python deploy.py deploy          # Create or update the stack
    python deploy.py delete          # Delete the stack
    python deploy.py outputs         # Show stack outputs
    python deploy.py status          # Show stack status

Prerequisites:
    pip install boto3
    AWS credentials configured (aws configure / env vars / IAM role)
"""

import sys
import time

import boto3
from botocore.exceptions import ClientError

# ---------------------------------------------------------------------------
# Configuration — edit these to match your deployment
# ---------------------------------------------------------------------------
STACK_NAME = "gsi-export-test"
TEMPLATE_FILE = "dynamo-gsi-scheduled-export.yaml"
REGION = "us-east-1"  # Set explicitly; change to your preferred region

PARAMETERS = {
    "DynamoTableName":          "ConnectViewDataTest",
    "GsiName":                  "Channel-InitiationTimestamp-index",
    "GsiPartitionKeyAttribute": "Channel",
    "GsiPartitionKeyValue":     "CHAT",
    "GsiSortKeyAttribute":      "InitiationTimestamp",
    "DateFormat":               "ISO",
    "S3DataPrefix":             "exports",
    "CronExpression":           "rate(1 day)",
    "DateRangeMode":            "PREVIOUS_DAY",
    "CreateTable":              "true",
    "TablePKName":              "ContactId",
    "TablePKType":              "S",
    "BillingMode":              "PAY_PER_REQUEST",
    "ExtraDateColumn":          "report_date",
}

# S3BucketName defaults to <stack>-<account> if not set here
# Set to "" to use the template default
S3_BUCKET_NAME = ""

CAPABILITIES = ["CAPABILITY_NAMED_IAM"]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _region_kwargs():
    return {"region_name": REGION} if REGION else {}

def get_account_id():
    sts = boto3.client("sts", **_region_kwargs())
    return sts.get_caller_identity()["Account"]

def get_staging_bucket():
    return f"cfn-templates-{get_account_id()}"

def get_clients():
    kwargs = _region_kwargs()
    cfn = boto3.client("cloudformation", **kwargs)
    s3 = boto3.client("s3", **kwargs)
    return cfn, s3


def ensure_staging_bucket(s3, bucket):
    try:
        s3.head_bucket(Bucket=bucket)
        print(f"  Staging bucket exists: {bucket}")
    except ClientError:
        print(f"  Creating staging bucket: {bucket}")
        kwargs = {"Bucket": bucket}
        region = s3.meta.region_name
        if region and region != "us-east-1":
            kwargs["CreateBucketConfiguration"] = {
                "LocationConstraint": region
            }
        s3.create_bucket(**kwargs)


def upload_template(s3, bucket):
    key = f"{STACK_NAME}/template.yaml"
    print(f"  Uploading template to s3://{bucket}/{key}")
    with open(TEMPLATE_FILE, "rb") as f:
        s3.put_object(Bucket=bucket, Key=key, Body=f.read())
    return f"https://{bucket}.s3.amazonaws.com/{key}"


def build_params():
    params = dict(PARAMETERS)
    if S3_BUCKET_NAME:
        params["S3BucketName"] = S3_BUCKET_NAME
    else:
        params["S3BucketName"] = f"{STACK_NAME}-{get_account_id()}"
    return [
        {"ParameterKey": k, "ParameterValue": str(v)}
        for k, v in params.items()
    ]


def stack_exists(cfn):
    try:
        resp = cfn.describe_stacks(StackName=STACK_NAME)
        status = resp["Stacks"][0]["StackStatus"]
        return status not in ("DELETE_COMPLETE",)
    except ClientError as e:
        if "does not exist" in str(e):
            return False
        raise


def wait_for_stack(cfn, waiter_name):
    print(f"  Waiting for stack {waiter_name}...")
    waiter = cfn.get_waiter(waiter_name)
    try:
        waiter.wait(
            StackName=STACK_NAME,
            WaiterConfig={"Delay": 10, "MaxAttempts": 120},
        )
        print(f"  Stack {waiter_name} complete.")
        return True
    except Exception as e:
        print(f"  Stack operation failed: {e}")
        return False


def print_outputs(cfn):
    try:
        resp = cfn.describe_stacks(StackName=STACK_NAME)
        outputs = resp["Stacks"][0].get("Outputs", [])
        if not outputs:
            print("  No outputs found.")
            return
        print("\n  Stack Outputs:")
        print("  " + "-" * 70)
        for o in outputs:
            key = o["OutputKey"]
            val = o["OutputValue"]
            print(f"  {key:30s} {val}")
            if key == "ReportDashboardURL":
                print(f"\n  >>> Dashboard URL: {val}")
        print("  " + "-" * 70)
    except ClientError as e:
        print(f"  Error: {e}")


def print_status(cfn):
    try:
        resp = cfn.describe_stacks(StackName=STACK_NAME)
        stack = resp["Stacks"][0]
        print(f"  Stack:  {stack['StackName']}")
        print(f"  Status: {stack['StackStatus']}")
        if "StackStatusReason" in stack:
            print(f"  Reason: {stack['StackStatusReason']}")
    except ClientError as e:
        if "does not exist" in str(e):
            print(f"  Stack '{STACK_NAME}' does not exist.")
        else:
            print(f"  Error: {e}")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_deploy():
    cfn, s3 = get_clients()
    print(f"\nDeploying stack: {STACK_NAME}")

    staging_bucket = get_staging_bucket()
    ensure_staging_bucket(s3, staging_bucket)
    template_url = upload_template(s3, staging_bucket)
    params = build_params()

    exists = stack_exists(cfn)

    if exists:
        print("  Stack exists — updating...")
        try:
            cfn.update_stack(
                StackName=STACK_NAME,
                TemplateURL=template_url,
                Parameters=params,
                Capabilities=CAPABILITIES,
            )
        except ClientError as e:
            if "No updates are to be performed" in str(e):
                print("  No changes detected. Stack is up to date.")
                print_outputs(cfn)
                return
            raise
        success = wait_for_stack(cfn, "stack_update_complete")
    else:
        print("  Creating new stack...")
        cfn.create_stack(
            StackName=STACK_NAME,
            TemplateURL=template_url,
            Parameters=params,
            Capabilities=CAPABILITIES,
        )
        success = wait_for_stack(cfn, "stack_create_complete")

    if success:
        print("\n  Deployment successful!")
        print_outputs(cfn)
    else:
        print("\n  Deployment failed. Check the AWS CloudFormation console.")
        print_status(cfn)
        sys.exit(1)


def cmd_delete():
    cfn, _ = get_clients()
    if not stack_exists(cfn):
        print(f"  Stack '{STACK_NAME}' does not exist.")
        return

    print(f"\nDeleting stack: {STACK_NAME}")
    print("  WARNING: This will delete all resources in the stack.")
    confirm = input("  Type 'yes' to confirm: ").strip().lower()
    if confirm != "yes":
        print("  Aborted.")
        return

    # Empty S3 buckets first (CloudFormation can't delete non-empty buckets)
    try:
        resp = cfn.describe_stacks(StackName=STACK_NAME)
        outputs = {o["OutputKey"]: o["OutputValue"]
                   for o in resp["Stacks"][0].get("Outputs", [])}
        s3r = boto3.resource("s3")
        for key in ("ExportDataBucket", "AthenaResultsBucket"):
            bucket_name = outputs.get(key)
            if bucket_name:
                print(f"  Emptying bucket: {bucket_name}")
                bucket = s3r.Bucket(bucket_name)
                bucket.objects.all().delete()
    except Exception as e:
        print(f"  Warning emptying buckets: {e}")

    # Delete Athena workgroup (may have query history)
    try:
        athena = boto3.client("athena")
        wg = outputs.get("AthenaWorkgroup")
        if wg:
            print(f"  Deleting Athena workgroup: {wg}")
            athena.delete_work_group(
                WorkGroup=wg, RecursiveDeleteOption=True)
    except Exception as e:
        print(f"  Warning deleting workgroup: {e}")

    cfn.delete_stack(StackName=STACK_NAME)
    success = wait_for_stack(cfn, "stack_delete_complete")
    if success:
        print("  Stack deleted successfully.")
    else:
        print("  Delete may have failed. Check console.")


def cmd_outputs():
    cfn, _ = get_clients()
    print_outputs(cfn)


def cmd_status():
    cfn, _ = get_clients()
    print_status(cfn)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

COMMANDS = {
    "deploy": cmd_deploy,
    "delete": cmd_delete,
    "outputs": cmd_outputs,
    "status": cmd_status,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"Usage: python {sys.argv[0]} <{' | '.join(COMMANDS.keys())}>")
        print("\nCommands:")
        print("  deploy   Create or update the CloudFormation stack")
        print("  delete   Delete the stack (empties buckets first)")
        print("  outputs  Show stack outputs (dashboard URL, etc.)")
        print("  status   Show current stack status")
        sys.exit(1)

    COMMANDS[sys.argv[1]]()
