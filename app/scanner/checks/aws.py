from datetime import datetime

from app.scanner.checks.common import (
    Malformed,
    boolean,
    checked,
    combine,
    exposure,
    items,
    obj,
    port,
    protocol,
    string,
    timestamp,
)
from app.scanner.types import Outcome


@checked
def s3_public_access(resource: dict, snapshot: datetime) -> Outcome:
    # All four public-access-block switches must be true; missing data cannot pass.
    config = obj(resource.get("public_access_block"), "public_access_block")
    fields = [
        "block_public_acls",
        "ignore_public_acls",
        "block_public_policy",
        "restrict_public_buckets",
    ]
    return combine(
        fields,
        lambda key: f"{key} is disabled" if not boolean(config.get(key), key) else None,
        "All four public access block settings are enabled.",
    )


@checked
def ec2_internet_access(resource: dict, snapshot: datetime) -> Outcome:
    # Inspect ingress only; TCP/all-protocol rules fail when public ranges include SSH or RDP.
    def evaluate(raw):
        rule = obj(raw, "ingress rule")
        kind = protocol(rule.get("protocol"))
        if kind == "other":
            return None
        if kind == "all":
            ranges = [(0, 65535)]
        else:
            start, end = port(rule.get("from_port")), port(rule.get("to_port"))
            if start > end:
                raise Malformed("from_port exceeds to_port")
            ranges = [(start, end)]
        return exposure(items(rule.get("cidrs"), "cidrs"), ranges, "Ingress rule")

    return combine(
        items(resource.get("ingress"), "ingress"),
        evaluate,
        "No ingress rule exposes SSH or RDP to the internet.",
    )


@checked
def iam_console_mfa(resource: dict, snapshot: datetime) -> Outcome:
    # Users without console access pass; console users must have MFA enabled.
    if not boolean(resource.get("console_access"), "console_access"):
        return Outcome("PASS", "User has no console access; console MFA is not required.")
    if boolean(resource.get("mfa_enabled"), "mfa_enabled"):
        return Outcome("PASS", "Console access is protected by MFA.")
    return Outcome("FAIL", "Console access is enabled but MFA is disabled.")


@checked
def iam_key_age(resource: dict, snapshot: datetime) -> Outcome:
    # Only active keys count; age is measured against the snapshot, and exactly 90 days passes.
    def evaluate(raw):
        key = obj(raw, "access key")
        state = string(key.get("status"), "access key status").lower()
        if state == "inactive":
            return None
        if state != "active":
            raise Malformed("Access key status must be Active or Inactive")
        key_id = string(key.get("key_id"), "key_id")
        age = (snapshot - timestamp(key.get("created_at"), "created_at")).total_seconds() / 86400
        if age < 0:
            raise Malformed(f"Key {key_id} was created after the snapshot")
        return f"Active key {key_id} is {age:.1f} days old (limit: 90 days)" if age > 90 else None

    return combine(
        items(resource.get("access_keys"), "access_keys"),
        evaluate,
        "No active access key is older than 90 days.",
    )


@checked
def rds_public_access(resource: dict, snapshot: datetime) -> Outcome:
    # A publicly accessible database fails, even if its security group might restrict access.
    if boolean(resource.get("publicly_accessible"), "publicly_accessible"):
        return Outcome("FAIL", "RDS publicly_accessible is true; disable public accessibility.")
    return Outcome("PASS", "RDS is not publicly accessible.")
