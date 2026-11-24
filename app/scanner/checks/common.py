import logging
from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from ipaddress import ip_network

from app.scanner.types import Outcome

logger = logging.getLogger(__name__)


class Malformed(ValueError):
    """Resource data is insufficient or has the wrong type."""


def obj(value: object, field: str) -> dict:
    if not isinstance(value, dict):
        raise Malformed(f"{field} must be an object")
    return value


def items(value: object, field: str) -> list:
    if not isinstance(value, list):
        raise Malformed(f"{field} must be a list")
    return value


def string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Malformed(f"{field} must be a nonempty string")
    return value


def boolean(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise Malformed(f"{field} must be true or false")
    return value


def timestamp(value: object, field: str) -> datetime:
    raw = string(value, field)
    try:
        result = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Malformed(f"{field} must be an ISO 8601 timestamp") from exc
    if result.tzinfo is None:
        raise Malformed(f"{field} must include a timezone")
    return result.astimezone(UTC)


def combine(values: list, evaluate: Callable, success: str) -> Outcome:
    """A known violation takes priority; otherwise incomplete data cannot pass."""
    failures, errors = [], []
    for value in values:
        try:
            reason = evaluate(value)
            if reason:
                failures.append(reason)
        except Malformed as exc:
            logger.warning("Malformed check input: %s", exc)
            errors.append(str(exc))
    if failures:
        detail = "; ".join(failures)
        if errors:
            detail += "; Additional data could not be evaluated: " + "; ".join(errors)
        return Outcome("FAIL", detail)
    if errors:
        return Outcome("CANNOT_SCAN", "; ".join(errors))
    return Outcome("PASS", success)


def public_source(value: object, azure: bool = False) -> bool:
    source = string(value, "source range")
    if azure and source.lower() in ("internet", "*"):
        return True
    if azure and source.lower() in ("virtualnetwork", "azureloadbalancer"):
        return False
    try:
        return ip_network(source, strict=False).prefixlen == 0
    except ValueError as exc:
        raise Malformed(f"Invalid source range: {source}") from exc


def protocol(value: object) -> str:
    raw = string(value, "protocol").lower()
    if raw in ("tcp", "6"):
        return "tcp"
    if raw in ("all", "*", "-1"):
        return "all"
    if raw in ("udp", "icmp", "icmpv6", "esp", "ah", "sctp"):
        return "other"
    if raw.isdecimal() and 0 <= int(raw) <= 255:
        return "other"
    raise Malformed(f"Invalid protocol: {raw}")


def port(value: object) -> int:
    if isinstance(value, str) and value.isdecimal():
        value = int(value)
    if type(value) is not int or not 0 <= value <= 65535:
        raise Malformed(f"Invalid port: {value}")
    return value


def port_range(value: object) -> tuple[int, int]:
    raw = string(value, "port range")
    if raw == "*":
        return 0, 65535
    parts = raw.split("-")
    if len(parts) not in (1, 2):
        raise Malformed(f"Invalid port range: {raw}")
    start, end = port(parts[0]), port(parts[-1])
    if start > end:
        raise Malformed(f"Reversed port range: {raw}")
    return start, end


def exposure(sources: list, ranges: list[tuple[int, int]], rule: str, azure=False) -> str | None:
    problems, errors = [], []
    for source in sources:
        try:
            if public_source(source, azure):
                for target in (22, 3389):
                    if any(start <= target <= end for start, end in ranges):
                        problems.append(f"{rule} permits TCP port {target} from {source}")
        except Malformed as exc:
            logger.warning("Malformed source range: %s", exc)
            errors.append(str(exc))
    if problems:
        return "; ".join(problems)
    if errors:
        raise Malformed("; ".join(errors))
    return None


def checked(evaluate):
    @wraps(evaluate)
    def wrapped(resource, snapshot):
        try:
            return evaluate(resource, snapshot)
        except Malformed as exc:
            return Outcome("CANNOT_SCAN", str(exc))

    return wrapped
