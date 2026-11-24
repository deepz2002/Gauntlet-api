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
def storage_public_access(resource: dict, snapshot: datetime) -> Outcome:
    # Public blob access must be explicitly disabled.
    if boolean(resource.get("allow_blob_public_access"), "allow_blob_public_access"):
        return Outcome("FAIL", "allow_blob_public_access is true; disable public blob access.")
    return Outcome("PASS", "Public blob access is disabled.")


@checked
def nsg_internet_access(resource: dict, snapshot: datetime) -> Outcome:
    # Only inbound Allow rules can expose admin ports; Deny and Outbound rules are ignored.
    def evaluate(raw):
        rule = obj(raw, "NSG rule")
        direction = string(rule.get("direction"), "direction").lower()
        if direction == "outbound":
            return None
        access = string(rule.get("access"), "access").lower()
        if direction not in ("inbound", "outbound") or access not in ("allow", "deny"):
            raise Malformed("Invalid NSG direction or access")
        if access == "deny":
            return None
        if protocol(rule.get("protocol")) == "other":
            return None
        ranges = [
            port_range(p.strip())
            for p in string(rule.get("destination_ports"), "destination_ports").split(",")
        ]
        name = string(rule.get("name"), "rule name")
        return exposure([rule.get("source")], ranges, f"Inbound Allow rule {name}", azure=True)

    return combine(
        items(resource.get("rules"), "rules"),
        evaluate,
        "No inbound Allow rule exposes SSH or RDP to the internet.",
    )
