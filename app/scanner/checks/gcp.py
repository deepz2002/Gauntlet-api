from datetime import datetime

from app.scanner.checks.common import (
    Malformed,
    boolean,
    checked,
    combine,
    exposure,
    items,
    obj,
    port_range,
    protocol,
    string,
)
from app.scanner.types import Outcome


@checked
def gcs_public_access(resource: dict, snapshot: datetime) -> Outcome:
    # Either public IAM member makes the bucket public, including allAuthenticatedUsers.
    def evaluate(raw):
        binding = obj(raw, "IAM binding")
        role = string(binding.get("role"), "IAM role")
        members = items(binding.get("members"), "IAM members")

        def member(raw_member):
            name = string(raw_member, "IAM member")
            return (
                f"{role} grants access to {name}"
                if name in ("allUsers", "allAuthenticatedUsers")
                else None
            )

        outcome = combine(members, member, "No public IAM members.")
        if outcome.status == "CANNOT_SCAN":
            raise Malformed(outcome.details)
        return outcome.details if outcome.status == "FAIL" else None

    return combine(
        items(resource.get("iam_bindings"), "iam_bindings"),
        evaluate,
        "No IAM binding grants access to public members.",
    )


@checked
def gcs_uniform_access(resource: dict, snapshot: datetime) -> Outcome:
    # Uniform access must be enabled so IAM, rather than separate object ACLs, controls access.
    if boolean(resource.get("uniform_bucket_level_access"), "uniform_bucket_level_access"):
        return Outcome("PASS", "Uniform bucket-level access is enabled.")
    return Outcome(
        "FAIL", "uniform_bucket_level_access is false; enable uniform bucket-level access."
    )


@checked
def firewall_internet_access(resource: dict, snapshot: datetime) -> Outcome:
    # Disabled and egress rules pass; enabled ingress TCP/all rules must not expose admin ports.
    if boolean(resource.get("disabled"), "disabled"):
        return Outcome("PASS", "Firewall rule is disabled.")
    direction = string(resource.get("direction"), "direction").lower()
    if direction == "egress":
        return Outcome("PASS", "Firewall rule is egress-only.")
    if direction != "ingress":
        raise Malformed("direction must be INGRESS or EGRESS")

    def evaluate(raw):
        allowed = obj(raw, "allowed rule")
        kind = protocol(allowed.get("IPProtocol"))
        if kind == "other":
            return None
        # GCP omitting ports means every port for that protocol.
        if kind == "all" or "ports" not in allowed:
            ranges = [(0, 65535)]
        else:
            ports = items(allowed["ports"], "ports")
            ranges = [port_range(p) for p in ports] if ports else [(0, 65535)]
        return exposure(
            items(resource.get("source_ranges"), "source_ranges"),
            ranges,
            f"Firewall rule {resource.get('name', '(unnamed)')}",
        )

    return combine(
        items(resource.get("allowed"), "allowed"),
        evaluate,
        "Firewall rule does not expose SSH or RDP to the internet.",
    )
