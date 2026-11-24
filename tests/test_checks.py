from copy import deepcopy
from datetime import UTC, datetime

import pytest

from app.scanner.checks import aws, azure, gcp
from app.scanner.registry import CHECKS

SNAPSHOT = datetime(2026, 10, 1, tzinfo=UTC)


@pytest.mark.parametrize(
    "evaluate,good,bad",
    [
        (
            aws.s3_public_access,
            {
                "public_access_block": dict(
                    block_public_acls=True,
                    ignore_public_acls=True,
                    block_public_policy=True,
                    restrict_public_buckets=True,
                )
            },
            {
                "public_access_block": dict(
                    block_public_acls=False,
                    ignore_public_acls=True,
                    block_public_policy=True,
                    restrict_public_buckets=True,
                )
            },
        ),
        (
            aws.ec2_internet_access,
            {"ingress": []},
            {"ingress": [dict(protocol="tcp", from_port=22, to_port=22, cidrs=["0.0.0.0/0"])]},
        ),
        (
            aws.iam_console_mfa,
            dict(console_access=True, mfa_enabled=True),
            dict(console_access=True, mfa_enabled=False),
        ),
        (
            aws.iam_key_age,
            {"access_keys": []},
            {
                "access_keys": [
                    dict(key_id="old", status="Active", created_at="2026-07-02T00:00:00Z")
                ]
            },
        ),
        (aws.rds_public_access, {"publicly_accessible": False}, {"publicly_accessible": True}),
        (
            azure.storage_public_access,
            {"allow_blob_public_access": False},
            {"allow_blob_public_access": True},
        ),
        (
            azure.nsg_internet_access,
            {"rules": []},
            {
                "rules": [
                    dict(
                        name="ssh",
                        direction="Inbound",
                        access="Allow",
                        protocol="Tcp",
                        source="Internet",
                        destination_ports="22",
                    )
                ]
            },
        ),
        (
            gcp.gcs_public_access,
            {"iam_bindings": []},
            {"iam_bindings": [dict(role="roles/storage.objectViewer", members=["allUsers"])]},
        ),
        (
            gcp.gcs_uniform_access,
            {"uniform_bucket_level_access": True},
            {"uniform_bucket_level_access": False},
        ),
        (
            gcp.firewall_internet_access,
            dict(disabled=True),
            dict(
                name="rdp",
                disabled=False,
                direction="INGRESS",
                source_ranges=["::/0"],
                allowed=[{"IPProtocol": "tcp", "ports": ["3389"]}],
            ),
        ),
    ],
)
def test_every_check_pass_fail_and_cannot_scan(evaluate, good, bad):
    assert evaluate(good, SNAPSHOT).status == "PASS"
    result = evaluate(bad, SNAPSHOT)
    assert result.status == "FAIL"
    assert result.details
    assert evaluate({}, SNAPSHOT).status == "CANNOT_SCAN"


def test_catalog_has_ten_unique_checks():
    assert len(CHECKS) == len({check.check_id for check in CHECKS}) == 10


@pytest.mark.parametrize(
    "rule,status",
    [
        (dict(protocol="tcp", from_port=3000, to_port=3500, cidrs=["0.0.0.0/0"]), "FAIL"),
        (dict(protocol="tcp", from_port=22, to_port=22, cidrs=["::/0"]), "FAIL"),
        (dict(protocol="-1", from_port=None, to_port=None, cidrs=["0.0.0.0/0"]), "FAIL"),
        (dict(protocol="6", from_port="22", to_port="22", cidrs=["0.0.0.0/0"]), "FAIL"),
        (dict(protocol="udp", from_port=22, to_port=22, cidrs=["0.0.0.0/0"]), "PASS"),
        (dict(protocol="tcp", from_port=22, to_port=22, cidrs=["203.0.113.0/24"]), "PASS"),
        (
            dict(protocol="tcp", from_port="twenty-two", to_port=22, cidrs=["0.0.0.0/0"]),
            "CANNOT_SCAN",
        ),
        (dict(protocol="tcp", from_port=True, to_port=22, cidrs=["0.0.0.0/0"]), "CANNOT_SCAN"),
        (dict(protocol="tcp", from_port=3500, to_port=22, cidrs=["0.0.0.0/0"]), "CANNOT_SCAN"),
        (dict(protocol="tcp", from_port=22, to_port=22, cidrs=["invalid"]), "CANNOT_SCAN"),
    ],
)
def test_aws_network_edges(rule, status):
    assert aws.ec2_internet_access({"ingress": [rule]}, SNAPSHOT).status == status


@pytest.mark.parametrize(
    "direction,access,ports,source,status",
    [
        ("Inbound", "Deny", "22", "*", "PASS"),
        ("Outbound", "Allow", "22", "*", "PASS"),
        ("Inbound", "Allow", "3380-3400", "0.0.0.0/0", "FAIL"),
        ("Inbound", "Allow", "*", "::/0", "FAIL"),
        ("Inbound", "Allow", "443,3389", "Internet", "FAIL"),
        ("Inbound", "Allow", "22", "VirtualNetwork", "PASS"),
        ("Inbound", "Allow", "invalid", "*", "CANNOT_SCAN"),
    ],
)
def test_azure_network_edges(direction, access, ports, source, status):
    rule = dict(
        name="test",
        direction=direction,
        access=access,
        destination_ports=ports,
        source=source,
        protocol="*",
    )
    assert azure.nsg_internet_access({"rules": [rule]}, SNAPSHOT).status == status


@pytest.mark.parametrize(
    "changes,status",
    [
        ({"disabled": True}, "PASS"),
        ({"direction": "EGRESS"}, "PASS"),
        ({"source_ranges": ["35.235.240.0/20"]}, "PASS"),
        ({"allowed": [{"IPProtocol": "tcp"}]}, "FAIL"),
        ({"allowed": [{"IPProtocol": "tcp", "ports": []}]}, "FAIL"),
        ({"allowed": [{"IPProtocol": "all"}]}, "FAIL"),
        ({"allowed": [{"IPProtocol": "tcp", "ports": ["3000-3500"]}]}, "FAIL"),
        ({"allowed": [{"IPProtocol": "tcp", "ports": ["8000-9000"]}]}, "PASS"),
        ({"allowed": [{"IPProtocol": "tcp", "ports": ["bad"]}]}, "CANNOT_SCAN"),
        ({"allowed": [{"IPProtocol": "tcp", "ports": None}]}, "CANNOT_SCAN"),
    ],
)
def test_gcp_network_edges(changes, status):
    resource = dict(
        name="test",
        direction="INGRESS",
        disabled=False,
        source_ranges=["::/0"],
        allowed=[dict(IPProtocol="tcp", ports=["22"])],
    )
    resource.update(changes)
    assert gcp.firewall_internet_access(resource, SNAPSHOT).status == status


@pytest.mark.parametrize(
    "created,state,status",
    [
        ("2026-07-03T00:00:00Z", "Active", "PASS"),
        ("2026-07-02T23:59:59Z", "Active", "FAIL"),
        ("2025-01-01T00:00:00Z", "Inactive", "PASS"),
        ("bad", "Active", "CANNOT_SCAN"),
        ("2026-07-03", "Active", "CANNOT_SCAN"),
        ("2026-10-02T00:00:00Z", "Active", "CANNOT_SCAN"),
    ],
)
def test_iam_age_boundary(created, state, status):
    user = {"access_keys": [dict(key_id="test", status=state, created_at=created)]}
    assert aws.iam_key_age(user, SNAPSHOT).status == status


def test_mfa_not_required_for_non_console_user():
    assert aws.iam_console_mfa({"console_access": False}, SNAPSHOT).status == "PASS"


def test_azure_outbound_fields_do_not_affect_inbound_exposure():
    resource = {"rules": [{"direction": "Outbound"}]}
    assert azure.nsg_internet_access(resource, SNAPSHOT).status == "PASS"


def test_gcs_all_authenticated_users_is_public():
    resource = {"iam_bindings": [dict(role="viewer", members=["allAuthenticatedUsers"])]}
    assert gcp.gcs_public_access(resource, SNAPSHOT).status == "FAIL"


@pytest.mark.parametrize(
    "evaluate,field",
    [
        (aws.rds_public_access, "publicly_accessible"),
        (azure.storage_public_access, "allow_blob_public_access"),
        (gcp.gcs_uniform_access, "uniform_bucket_level_access"),
    ],
)
def test_boolean_strings_are_not_booleans(evaluate, field):
    assert evaluate({field: "false"}, SNAPSHOT).status == "CANNOT_SCAN"


def test_proven_violation_wins_over_an_unrelated_malformed_rule():
    resource = {
        "ingress": [
            dict(protocol="tcp", from_port="bad", to_port=22, cidrs=["0.0.0.0/0"]),
            dict(protocol="tcp", from_port=22, to_port=22, cidrs=["0.0.0.0/0"]),
        ]
    }
    assert aws.ec2_internet_access(deepcopy(resource), SNAPSHOT).status == "FAIL"
