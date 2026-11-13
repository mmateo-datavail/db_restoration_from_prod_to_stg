#!/usr/bin/env python3
"""
AWS Resource Creation / Destruction Script
Usage:
  python3 aws_dr_resources.py creation  <region> <account_id> <env_tag> [txt_file_path]
  python3 aws_dr_resources.py destruction <region> <account_id> <env_tag> <txt_file_path>
"""

import sys
import json
import time
import datetime
import argparse
import threading
import secrets
import string
import boto3
from botocore.exceptions import ClientError
from typing import Any

# ─────────────────────────────────────────────
# ANSI color helpers
# ─────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def green(msg):  return f"{GREEN}{msg}{RESET}"
def red(msg):    return f"{RED}{msg}{RESET}"
def yellow(msg): return f"{YELLOW}{msg}{RESET}"
def cyan(msg):   return f"{CYAN}{msg}{RESET}"
def bold(msg):   return f"{BOLD}{msg}{RESET}"

def log(msg, color=None):
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(color(line) if color else line)

# ─────────────────────────────────────────────
# Argument parsing
# ─────────────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(
        description="Create or destroy AWS test resources tagged with a given Environment."
    )
    parser.add_argument(
        "process",
        choices=["creation", "destruction"],
        help="Action to perform: 'creation' or 'destruction'."
    )
    parser.add_argument("region",     help="AWS region (e.g. us-east-2)")
    parser.add_argument("account_id", help="AWS account ID")
    parser.add_argument("env_tag",    help="Value for the 'Environment' tag (e.g. Test-for-DR)")
    parser.add_argument(
        "txt_file_path",
        nargs="?",
        default=None,
        help="(destruction only) Path to .txt file with ARNs to destroy, one per line."
    )
    args = parser.parse_args()

    if args.process == "destruction" and not args.txt_file_path:
        parser.error("'destruction' requires a txt_file_path argument.")

    return args

# ─────────────────────────────────────────────
# Tag helpers
# ─────────────────────────────────────────────
def make_tags(env_tag):
    return [{"Key": "Environment", "Value": env_tag}]

def generate_master_password(length=20):
    """Generate a printable ASCII password accepted by RDS and Redshift."""
    special_chars = "!#$%&*+-.:;<=>?^_~"
    allowed_chars = string.ascii_letters + string.digits + special_chars
    password_chars = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
        secrets.choice(special_chars),
    ]
    password_chars.extend(
        secrets.choice(allowed_chars) for _ in range(length - len(password_chars))
    )
    secrets.SystemRandom().shuffle(password_chars)
    return "".join(password_chars)

# ─────────────────────────────────────────────
# Countdown with 10-second status updates
# ─────────────────────────────────────────────
def countdown_with_status(seconds, status_fn, interval=10):
    elapsed = 0
    while elapsed < seconds:
        remaining = seconds - elapsed
        log(f"Starting in {remaining}s ... (Ctrl+C to abort)", yellow)
        time.sleep(min(interval, remaining))
        elapsed += interval

# ─────────────────────────────────────────────
# Periodic status printer (background thread)
# ─────────────────────────────────────────────
class StatusPrinter:
    def __init__(self, get_status_fn, interval=10):
        self._fn = get_status_fn
        self._interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join()

    def _run(self):
        while not self._stop.is_set():
            time.sleep(self._interval)
            if not self._stop.is_set():
                self._fn()

# ─────────────────────────────────────────────
# Resource state tracker
# ─────────────────────────────────────────────
resource_status = {}   # name -> "PENDING" | "CREATING" | "DONE" | "FAILED"

def print_status():
    log("─── Resource creation status ───", cyan)
    for name, state in resource_status.items():
        if state == "DONE":
            print(f"  {green('✔')} {name}: {green(state)}")
        elif state == "FAILED":
            print(f"  {red('✘')} {name}: {red(state)}")
        elif state == "CREATING":
            print(f"  {yellow('…')} {name}: {yellow(state)}")
        else:
            print(f"  · {name}: {state}")

# ─────────────────────────────────────────────
# Output .txt writer
# ─────────────────────────────────────────────
def write_resources_file(resources, env_tag, region, filename=None):
    if filename is None:
        filename = (
            f"created_resources_{env_tag}_{region}.txt"
            # f"{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
            # f"{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        with open(filename, "w"):
            pass
        log(f"Resource list initialized: {filename}", green)
        return filename
    if not resources:
        return filename

    lines = []
    for r in resources:
        lines.append(f"Type   : {r.get('type', 'AWS resource')}")
        lines.append(f"ARN/ID : {r.get('arn', r.get('id', 'N/A'))}")
        if r.get("id") and r.get("arn"):
            lines.append(f"ID     : {r['id']}")
        if r.get("name"):
            lines.append(f"Name   : {r['name']}")
        lines.append(f"Region : {r.get('region', region)}")
        lines.append(f"Tag    : Environment={r.get('env', env_tag)}")
        lines.append("")   # blank line separator between resources
    with open(filename, "a") as f:
        f.write("\n".join(lines))
    return filename

# ─────────────────────────────────────────────
# ──────────────  CREATION  ───────────────────
# ─────────────────────────────────────────────

def get_default_vpc(ec2):
    vpcs = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
    if not vpcs["Vpcs"]:
        raise RuntimeError("No default VPC found in this region.")
    return vpcs["Vpcs"][0]["VpcId"]

def get_subnets(ec2, vpc_id):
    resp = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])
    return [s["SubnetId"] for s in resp["Subnets"]]

def get_amazon_linux_ami(ec2):
    resp = ec2.describe_images(
        Owners=["amazon"],
        Filters=[
            {"Name": "name",                "Values": ["al2023-ami-ecs-hvm-*-x86_64"]},
            {"Name": "state",               "Values": ["available"]},
            {"Name": "architecture",        "Values": ["x86_64"]},
            {"Name": "virtualization-type", "Values": ["hvm"]},
        ],
    )
    images = sorted(resp["Images"], key=lambda x: x["CreationDate"], reverse=True)
    if not images:
        raise RuntimeError("No Amazon Linux 2023 ECS-optimized AMI found.")
    return images[0]["ImageId"]

# ── ECS ───────────────────────────────────────
def create_ecs_cluster(ecs, name, env_tag, region, account_id):
    resource_status[name] = "CREATING"
    resp = ecs.create_cluster(
        clusterName=name,
        tags=[{"key": "Environment", "value": env_tag}],
    )
    arn = resp["cluster"]["clusterArn"]
    resource_status[name] = "DONE"
    log(f"ECS cluster created: {arn}", green)
    return {"name": name, "type": "ECS Cluster", "arn": arn, "region": region, "env": env_tag}

# ── Launch Template + ASG ─────────────────────
def create_launch_template(ec2, autoscaling, name, ami_id, env_tag, ecs_cluster_name):
    try:
        existing = ec2.describe_launch_templates(
            LaunchTemplateNames=[name]
        ).get("LaunchTemplates", [])
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code == "InvalidLaunchTemplateName.NotFoundException":
            existing = []
        else:
            raise
    if existing:
        existing_template = existing[0]
        template_id = existing_template["LaunchTemplateId"]
        if autoscaling:
            groups = autoscaling.describe_auto_scaling_groups().get("AutoScalingGroups", [])
            for group in groups:
                lt = group.get("LaunchTemplate", {})
                if lt.get("LaunchTemplateId") == template_id:
                    group_name = group["AutoScalingGroupName"]
                    log(f"  Deleting existing ASG before recreating launch template: {group_name}", yellow)
                    autoscaling.delete_auto_scaling_group(
                        AutoScalingGroupName=group_name,
                        ForceDelete=True,
                    )
                    deadline = time.monotonic() + 600
                    while True:
                        remaining = autoscaling.describe_auto_scaling_groups(
                            AutoScalingGroupNames=[group_name]
                        ).get("AutoScalingGroups", [])
                        if not any(g["AutoScalingGroupName"] == group_name for g in remaining):
                            break
                        if time.monotonic() >= deadline:
                            raise TimeoutError(
                                f"Timed out waiting for Auto Scaling group {group_name} deletion"
                            )
                        time.sleep(5)
        ec2.delete_launch_template(LaunchTemplateId=template_id)
        log(f"  Existing launch template deleted before recreation: {name}", yellow)

    resp = ec2.create_launch_template(
        LaunchTemplateName=name,
        LaunchTemplateData={
            "ImageId":      ami_id,
            "InstanceType": "t2.micro",
            "UserData": __import__("base64").b64encode(
                f"#!/bin/bash\necho ECS_CLUSTER={ecs_cluster_name} >> /etc/ecs/ecs.config\n".encode()
            ).decode(),
            "TagSpecifications": [
                {"ResourceType": "instance", "Tags": make_tags(env_tag)}
            ],
        },
        TagSpecifications=[
            {"ResourceType": "launch-template", "Tags": make_tags(env_tag)}
        ],
    )
    template = resp["LaunchTemplate"]
    return {
        "id": template["LaunchTemplateId"],
        "arn": template.get("LaunchTemplateArn"),
        "name": name,
        "type": "EC2 Launch Template",
        "region": ec2.meta.region_name,
        "env": env_tag,
    }

def create_asg(autoscaling, name, lt_id, subnets, env_tag, region):
    resource_status[name] = "CREATING"
    autoscaling.create_auto_scaling_group(
        AutoScalingGroupName=name,
        LaunchTemplate={"LaunchTemplateId": lt_id, "Version": "$Latest"},
        MinSize=1,
        MaxSize=1,
        DesiredCapacity=1,
        VPCZoneIdentifier=",".join(subnets[:2]),
        Tags=[
            {
                "Key":               "Environment",
                "Value":             env_tag,
                "ResourceId":        name,
                "ResourceType":      "auto-scaling-group",
                "PropagateAtLaunch": True,
            }
        ],
    )
    resp = autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[name])
    arn = resp["AutoScalingGroups"][0]["AutoScalingGroupARN"]
    resource_status[name] = "DONE"
    log(f"ASG created: {arn}", green)
    return {"name": name, "type": "Auto Scaling Group", "arn": arn, "id": arn, "region": region, "env": env_tag}

def create_ecs_task_definition(ecs, name, env_tag, region):
    """Register a small generic task compatible with the EC2-backed cluster."""
    response = ecs.register_task_definition(
        family=name,
        networkMode="bridge",
        requiresCompatibilities=["EC2"],
        cpu="128",
        memory="128",
        containerDefinitions=[
            {
                "name": "generic",
                "image": "public.ecr.aws/docker/library/busybox:latest",
                "essential": True,
                "command": ["sh", "-c", "while true; do sleep 3600; done"],
                "memory": 128,
            }
        ],
        tags=[{"key": "Environment", "value": env_tag}],
    )
    arn = response["taskDefinition"]["taskDefinitionArn"]
    log(f"ECS task definition registered: {arn}", green)
    return {"name": name, "type": "ECS Task Definition", "arn": arn, "region": region, "env": env_tag}


def attach_asg_to_ecs(ecs, cluster_arn, cluster_name, asg_arn, provider_name, env_tag):
    """Register an ASG-backed capacity provider and associate it with its ECS cluster."""
    existing = ecs.describe_capacity_providers(
        capacityProviders=[provider_name], include=["TAGS"]
    ).get("capacityProviders", [])
    if existing:
        provider = existing[0]
        provider_arn = provider["capacityProviderArn"]
        log(f"Using existing capacity provider: {provider_arn}", yellow)
    else:
        response = ecs.create_capacity_provider(
            name=provider_name,
            autoScalingGroupProvider={
                "autoScalingGroupArn": asg_arn,
                "managedScaling": {"status": "DISABLED"},
                "managedTerminationProtection": "DISABLED",
            },
            tags=[{"key": "Environment", "value": env_tag}],
        )
        provider_arn = response["capacityProvider"]["capacityProviderArn"]
    # Cluster creation can leave its attachment in progress briefly. ECS rejects
    # capacity-provider updates during that transition, so wait and retry.
    deadline = time.monotonic() + 300
    while True:
        try:
            ecs.put_cluster_capacity_providers(
                cluster=cluster_arn,
                capacityProviders=[provider_name],
                defaultCapacityProviderStrategy=[{"capacityProvider": provider_name, "weight": 1}],
            )
            break
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code != "UpdateInProgressException" or time.monotonic() >= deadline:
                raise
            log(f"ECS cluster {cluster_name} is updating; retrying capacity-provider attachment", yellow)
            time.sleep(5)
    log(f"Capacity provider {provider_name} attached to ECS cluster {cluster_name}", green)
    return {"name": provider_name, "type": "ECS Capacity Provider", "arn": provider_arn, "id": provider_arn, "region": ecs.meta.region_name, "env": env_tag}


def wait_for_ecs_container_instance(ecs, cluster, timeout=600):
    """Wait for the ASG instance to register before submitting an EC2 task."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        arns = ecs.list_container_instances(
            cluster=cluster, status="ACTIVE"
        ).get("containerInstanceArns", [])
        if arns:
            instances = ecs.describe_container_instances(
                cluster=cluster, containerInstances=arns
            ).get("containerInstances", [])
            if any(instance.get("status") == "ACTIVE" for instance in instances):
                return
        time.sleep(10)
    raise TimeoutError(
        f"No active ECS container instance registered in cluster {cluster} after {timeout} seconds"
    )

# ── EC2 ───────────────────────────────────────
def create_ec2_instance(ec2, name, ami_id, env_tag, region):
    resource_status[name] = "CREATING"
    resp = ec2.run_instances(
        ImageId=ami_id,
        InstanceType="t2.micro",
        MinCount=1,
        MaxCount=1,
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": make_tags(env_tag) + [{"Key": "Name", "Value": name}],
            }
        ],
    )
    instance    = resp["Instances"][0]
    instance_id = instance["InstanceId"]
    arn         = f"arn:aws:ec2:{region}::instance/{instance_id}"
    resource_status[name] = "DONE"
    log(f"EC2 instance created: {arn}/{instance_id}", green)
    return {"name": name, "type": "EC2 Instance", "arn": arn, "id": instance_id, "region": region, "env": env_tag}

# ── Redshift ──────────────────────────────────
def create_redshift_cluster(redshift, name, env_tag, region, account_id):
    # dc2.large is not available in every region. Redshift has no free-tier
    # instance; use the smallest generally available RA3 node type instead.
    node_type = "ra3.xlplus"
    resource_status[name] = "CREATING"
    master_password = generate_master_password()
    redshift.create_cluster(
        ClusterIdentifier=name,
        NodeType=node_type,
        MasterUsername="adminuser",
        MasterUserPassword=master_password,
        ClusterType="single-node",
        NumberOfNodes=1,
        PubliclyAccessible=False,
        Tags=make_tags(env_tag),
    )
    arn = f"arn:aws:redshift:{region}:{account_id}:cluster:{name}"
    resource_status[name] = "DONE"
    log(f"Redshift cluster created: {arn}", green)
    return {"name": name, "type": "Redshift Cluster", "arn": arn, "region": region, "env": env_tag}

# ── RDS ───────────────────────────────────────
def create_rds_instance(rds, name, env_tag, region, account_id, subnet_ids):
    resource_status[name] = "CREATING"
    sg_name = f"{name}-subnet-grp"
    try:
        rds.create_db_subnet_group(
            DBSubnetGroupName=sg_name,
            DBSubnetGroupDescription=f"Subnet group for {name}",
            SubnetIds=subnet_ids,
            Tags=make_tags(env_tag),
        )
    except ClientError as e:
        if "DBSubnetGroupAlreadyExists" not in str(e):
            raise
    master_password = generate_master_password()
    resp = rds.create_db_instance(
        DBInstanceIdentifier=name,
        DBInstanceClass="db.t3.micro",
        Engine="mysql",
        MasterUsername="adminuser",
        MasterUserPassword=master_password,
        AllocatedStorage=20,
        DBSubnetGroupName=sg_name,
        MultiAZ=False,
        PubliclyAccessible=False,
        Tags=make_tags(env_tag),
    )
    arn = resp["DBInstance"]["DBInstanceArn"]
    resource_status[name] = "DONE"
    log(f"RDS instance created: {arn}", green)
    return {"name": name, "type": "RDS DB Instance", "arn": arn, "region": region, "env": env_tag}

# ─────────────────────────────────────────────
# ──────────────  DESTRUCTION  ────────────────
# ─────────────────────────────────────────────

def read_arns_from_file(path):
    """
    Read ARNs from the .txt file produced by creation mode.
    Handles both raw ARN lines and 'ARN/ID : <value>' formatted lines.
    Uses 'contains' logic (line-by-line, checks if ARN string is present).
    """
    arns = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Format: "ARN/ID : arn:aws:..."
            if line.startswith("ARN/ID"):
                value = line.split(":", 1)[1].strip()
                if value and value != "N/A":
                    arns.append(value)
            elif line.startswith("ID"):
                value = line.split(":", 1)[1].strip()
                if value and value != "N/A":
                    arns.append(value)
            # Raw ARN / EC2 instance ID / launch template ID
            elif "arn:" in line or line.startswith(("i-", "lt-")):
                arns.append(line)
    return arns

def destroy_resource(arn, region, env_tag, session):
    """
    Dispatch destruction based on ARN content (contains-based matching).
    Verifies the Environment tag before deleting.
    """
    log(f"Attempting to destroy: {arn}", red)

    # ── ECS capacity provider ─────────────────
    if "arn:aws:ecs" in arn and ":capacity-provider/" in arn:
        ecs = session.client("ecs", region_name=region)
        providers = ecs.describe_capacity_providers(
            capacityProviders=[arn], include=["TAGS"]
        ).get("capacityProviders", [])
        if not providers:
            log(f"  Capacity provider not found: {arn}", yellow)
            return
        provider = providers[0]
        tags = {t["key"]: t["value"] for t in provider.get("tags", [])}
        if tags.get("Environment") != env_tag:
            log(f"  SKIPPED (tag mismatch — expected Environment={env_tag}): {arn}", yellow)
            return
        ecs.delete_capacity_provider(capacityProvider=arn)
        log(f"  ECS capacity provider deleted: {arn}", red)
        return

    if arn.startswith("lt-") or ":launch-template/" in arn:
        ec2 = session.client("ec2", region_name=region)
        autoscaling = session.client("autoscaling", region_name=region)
        # Launch templates have an ID, not a resource ARN suitable for deletion.
        # The resource file may contain either the ID or LaunchTemplateArn.
        template_id = arn.rsplit("/", 1)[-1] if ":launch-template/" in arn else arn
        templates = ec2.describe_launch_templates(
            LaunchTemplateIds=[template_id]
        ).get("LaunchTemplates", [])
        if not templates:
            log(f"  Launch template not found: {template_id}", yellow)
            return
        tags = {t["Key"]: t["Value"] for t in templates[0].get("Tags", [])}
        if tags.get("Environment") != env_tag:
            log(f"  SKIPPED (tag mismatch — expected Environment={env_tag}): {arn}", yellow)
            return

        asgs = autoscaling.describe_auto_scaling_groups().get("AutoScalingGroups", [])
        for group in asgs:
            lt = group.get("LaunchTemplate", {})
            if lt.get("LaunchTemplateId") == template_id:
                log(f"  Deleting ASG that still references launch template: {group['AutoScalingGroupName']}", yellow)
                autoscaling.delete_auto_scaling_group(
                    AutoScalingGroupName=group["AutoScalingGroupName"],
                    ForceDelete=True,
                )

        ec2.delete_launch_template(LaunchTemplateId=template_id)
        log(f"  Launch template deleted: {template_id}", red)
        return

    # ── ECS cluster ──────────────────────────
    if "arn:aws:ecs" in arn and ":cluster/" in arn:
        cluster_name = arn.split("/")[-1]
        ecs = session.client("ecs", region_name=region)
        tags_resp = ecs.list_tags_for_resource(resourceArn=arn)
        tags = {t["key"]: t["value"] for t in tags_resp.get("tags", [])}
        if tags.get("Environment") != env_tag:
            log(f"  SKIPPED (tag mismatch — expected Environment={env_tag}): {arn}", yellow)
            return
        ecs.delete_cluster(cluster=cluster_name)
        log(f"  ECS cluster deleted: {cluster_name}", red)

    # ── ASG ───────────────────────────────────
    elif "arn:aws:autoscaling" in arn and ":autoScalingGroup:" in arn:
        asg_name = arn.split("autoScalingGroupName/")[-1]
        autoscaling = session.client("autoscaling", region_name=region)
        resp = autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
        if not resp["AutoScalingGroups"]:
            log(f"  ASG not found: {asg_name}", yellow)
            return
        tags = {t["Key"]: t["Value"] for t in resp["AutoScalingGroups"][0].get("Tags", [])}
        if tags.get("Environment") != env_tag:
            log(f"  SKIPPED (tag mismatch — expected Environment={env_tag}): {arn}", yellow)
            return
        autoscaling.delete_auto_scaling_group(
            AutoScalingGroupName=asg_name,
            ForceDelete=True,
        )
        log(f"  ASG deleted: {asg_name}", red)

    # ── EC2 instance ──────────────────────────
    elif "arn:aws:ec2" in arn and ":instance/" in arn:
        instance_id = arn.split("/")[-1]
        ec2 = session.client("ec2", region_name=region)
        resp = ec2.describe_instances(InstanceIds=[instance_id])
        reservations = resp.get("Reservations", [])
        if not reservations:
            log(f"  EC2 instance not found: {instance_id}", yellow)
            return
        tags = {t["Key"]: t["Value"] for t in reservations[0]["Instances"][0].get("Tags", [])}
        if tags.get("Environment") != env_tag:
            log(f"  SKIPPED (tag mismatch — expected Environment={env_tag}): {arn}", yellow)
            return
        ec2.terminate_instances(InstanceIds=[instance_id])
        log(f"  EC2 instance terminated: {instance_id}", red)

    # ── Redshift cluster ──────────────────────
    elif "arn:aws:redshift" in arn and ":cluster:" in arn:
        cluster_id = arn.split(":")[-1]
        redshift = session.client("redshift", region_name=region)
        resp = redshift.describe_clusters(ClusterIdentifier=cluster_id)
        clusters = resp.get("Clusters", [])
        if not clusters:
            log(f"  Redshift cluster not found: {cluster_id}", yellow)
            return
        tags = {t["Key"]: t["Value"] for t in clusters[0].get("Tags", [])}
        if tags.get("Environment") != env_tag:
            log(f"  SKIPPED (tag mismatch — expected Environment={env_tag}): {arn}", yellow)
            return
        redshift.delete_cluster(
            ClusterIdentifier=cluster_id,
            SkipFinalClusterSnapshot=True,
        )
        log(f"  Redshift cluster deleted: {cluster_id}", red)

    # ── RDS instance ──────────────────────────
    elif "arn:aws:rds" in arn and ":db:" in arn:
        db_id = arn.split(":")[-1]
        rds = session.client("rds", region_name=region)
        resp = rds.describe_db_instances(DBInstanceIdentifier=db_id)
        dbs = resp.get("DBInstances", [])
        if not dbs:
            log(f"  RDS instance not found: {db_id}", yellow)
            return
        tags_resp = rds.list_tags_for_resource(ResourceName=arn)
        tags = {t["Key"]: t["Value"] for t in tags_resp.get("TagList", [])}
        if tags.get("Environment") != env_tag:
            log(f"  SKIPPED (tag mismatch — expected Environment={env_tag}): {arn}", yellow)
            return
        rds.delete_db_instance(
            DBInstanceIdentifier=db_id,
            SkipFinalSnapshot=True,
            DeleteAutomatedBackups=True,
        )
        log(f"  RDS instance deleted: {db_id}", red)

    else:
        log(f"  Unknown resource type, skipping: {arn}", yellow)

# ─────────────────────────────────────────────
# ──────────────  MAIN  ───────────────────────
# ─────────────────────────────────────────────

def main():
    args = parse_args()
    process:    str = args.process
    region:     str = args.region
    account_id: str = args.account_id
    env_tag:    str = args.env_tag
    txt_file:   Any = args.txt_file_path   # None when process == "creation"

    session = boto3.Session(region_name=region)

    # ── PLAN display ─────────────────────────
    print()
    print(bold("=" * 60))
    if process == "creation":
        print(bold(green("  PLAN — Resources to CREATE")))
        print(bold("=" * 60))
        resources_plan = [
            ("ECS Cluster",  "test-ecs-cluster-1", "ECS Fargate (cheapest, no EC2 nodes)"),
            ("ECS Cluster",  "test-ecs-cluster-2", "ECS Fargate (cheapest, no EC2 nodes)"),
            ("ASG",          "test-asg-1",          "ECS-optimized t2.micro, min/max/desired=1"),
            ("ASG",          "test-asg-2",          "ECS-optimized t2.micro, min/max/desired=1"),
            ("EC2 Launch Template", "test-lt-1",    "ECS-optimized launch template for ASG-1"),
            ("EC2 Launch Template", "test-lt-2",    "ECS-optimized launch template for ASG-2"),
            ("EC2 Instance", "test-ec2-1",          "t2.micro — free tier eligible"),
            ("EC2 Instance", "test-ec2-2",          "t2.micro — free tier eligible"),
            ("Redshift",     "test-redshift-1",     "ra3.xlplus single-node (no free tier; significant charges)"),
            ("RDS",          "test-rds-mysql-1",    "MySQL db.t3.micro (engine differs from Redshift)"),
        ]
        for rtype, rname, rdesc in resources_plan:
            print(green(f"  + [{rtype}] {rname}  —  {rdesc}"))
        print()
        print(green(f"  Tag    : Environment = {env_tag}"))
        print(green(f"  Region : {region}"))
    else:
        print(bold(cyan("  PLAN — Resources to DESTROY")))
        print(bold("=" * 60))
        arns = read_arns_from_file(txt_file)
        for arn in arns:
            print(red(f"  - {arn}"))
        print()
        print(bold(f"  Safety filter : only resources tagged Environment={env_tag} will be deleted."))
        print(bold(f"  Region        : {region}"))
    print(bold("=" * 60))
    print()

    # ── 10-second countdown ───────────────────
    log("Waiting 10 seconds before execution. Press Ctrl+C to abort.", yellow)
    countdown_with_status(10, print_status, interval=10)
    print()

    # ─────────────────────────────────────────
    # CREATION
    # ─────────────────────────────────────────
    if process == "creation":
        ec2_client         = session.client("ec2")
        ecs_client         = session.client("ecs")
        autoscaling_client = session.client("autoscaling")
        redshift_client    = session.client("redshift")
        rds_client         = session.client("rds")

        log("Discovering default VPC, subnets, and latest Amazon Linux 2023 AMI ...", cyan)
        vpc_id  = get_default_vpc(ec2_client)
        subnets = get_subnets(ec2_client, vpc_id)
        ami_id  = get_amazon_linux_ami(ec2_client)
        log(f"VPC: {vpc_id} | Subnets: {subnets[:3]} | AMI: {ami_id}", cyan)

        for key in [
            "test-ecs-cluster-1", "test-ecs-cluster-2",
            "test-asg-1", "test-asg-2",
            "test-ec2-1", "test-ec2-2",
            "test-redshift-1", "test-rds-mysql-1",
        ]:
            resource_status[key] = "PENDING"

        printer = StatusPrinter(print_status, interval=10)
        printer.start()

        created = []
        output_file = write_resources_file([], env_tag, region)
        try:
            log("Creating ECS clusters ...", cyan)
            for i in [1, 2]:
                r = create_ecs_cluster(
                    ecs_client, f"test-ecs-cluster-{i}", env_tag, region, account_id
                )
                created.append(r)
                write_resources_file([r], env_tag, region, output_file)
                task_record = create_ecs_task_definition(
                    ecs_client, f"test-ecs-task-{i}", env_tag, region
                )
                created.append(task_record)
                write_resources_file([task_record], env_tag, region, output_file)

            log("Creating Launch Templates and ASGs ...", cyan)
            for i in [1, 2]:
                lt_record = create_launch_template(
                    ec2_client,
                    autoscaling_client,
                    f"test-lt-{i}",
                    ami_id,
                    env_tag,
                    f"test-ecs-cluster-{i}",
                )
                created.append(lt_record)
                write_resources_file([lt_record], env_tag, region, output_file)
                r = create_asg(
                    autoscaling_client, f"test-asg-{i}", lt_record["id"], subnets, env_tag, region
                )
                created.append(r)
                write_resources_file([r], env_tag, region, output_file)
                cluster_arn = next(
                    item["arn"] for item in created
                    if item.get("name") == f"test-ecs-cluster-{i}"
                )
                provider_record = attach_asg_to_ecs(
                    ecs_client, cluster_arn, f"test-ecs-cluster-{i}", r["arn"],
                    f"test-capacity-provider-{i}", env_tag
                )
                created.append(provider_record)
                write_resources_file([provider_record], env_tag, region, output_file)
                log(f"Waiting for an EC2 container instance in test-ecs-cluster-{i} ...", cyan)
                wait_for_ecs_container_instance(ecs_client, cluster_arn)
                run_response = ecs_client.run_task(
                    cluster=cluster_arn,
                    taskDefinition=task_record["arn"],
                    capacityProviderStrategy=[
                        {"capacityProvider": f"test-capacity-provider-{i}", "weight": 1}
                    ],
                    count=1,
                )
                if run_response.get("failures"):
                    raise RuntimeError(f"ECS task launch failed: {run_response['failures']}")
                log(f"Generic task started on ECS cluster test-ecs-cluster-{i}", green)

            log("Creating EC2 instances ...", cyan)
            for i in [1, 2]:
                r = create_ec2_instance(
                    ec2_client, f"test-ec2-{i}", ami_id, env_tag, region
                )
                created.append(r)
                write_resources_file([r], env_tag, region, output_file)

            log("Creating Redshift cluster ...", cyan)
            r = create_redshift_cluster(
                redshift_client, "test-redshift-1", env_tag, region, account_id
            )
            created.append(r)
            write_resources_file([r], env_tag, region, output_file)

            log("Creating RDS MySQL instance ...", cyan)
            r = create_rds_instance(
                rds_client, "test-rds-mysql-1", env_tag, region, account_id, subnets
            )
            created.append(r)
            write_resources_file([r], env_tag, region, output_file)

        finally:
            printer.stop()

        print()
        print_status()
        print()
        log(f"Resource list written to: {output_file}", green)
        log("All creation tasks completed.", green)

    # ─────────────────────────────────────────
    # DESTRUCTION
    # ─────────────────────────────────────────
    else:
        arns = read_arns_from_file(txt_file)
        log(f"Read {len(arns)} ARN(s) from {txt_file}", cyan)

        log("Resources to be deleted:", cyan)
        for arn in arns:
            log(f"  {arn}", cyan)

        for arn in arns:
            try:
                destroy_resource(arn, region, env_tag, session)
            except ClientError as e:
                log(f"  ERROR destroying {arn}: {e}", red)

        log("\n\nAll destruction tasks completed.\n", green)


if __name__ == "__main__":
    main()
