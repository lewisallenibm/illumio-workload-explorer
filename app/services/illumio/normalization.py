"""Canonical normalization for all Illumio workload ingestion sources.

Sources are deliberately kept outside the database model.  Mock data, PCE
responses, and future Workloader exports may use different field names, but
they must all become :class:`CanonicalWorkload` objects before persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping


CANONICAL_LABEL_KEYS = {
    "application",
    "role",
    "environment",
    "location",
}

LABEL_KEY_ALIASES = {
    "app": "application",
    "application": "application",
    "role": "role",
    "env": "environment",
    "environment": "environment",
    "loc": "location",
    "location": "location",
}


@dataclass(frozen=True)
class CanonicalLabel:
    key: str
    value: str
    href: str | None = None


@dataclass(frozen=True)
class CanonicalInterface:
    name: str
    address: str
    network_name_or_type: str | None
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class CanonicalWorkload:
    href: str
    name: str | None
    hostname: str | None
    online: bool | None
    connectivity_status: str | None
    enforcement_mode: str | None
    visibility_status: str | None
    policy_sync_status: str | None
    ransomware_exposure: str | None
    protection_status: str | None
    protection_coverage_score: float | None
    ven_version: str | None
    os: str | None
    os_release: str | None
    interfaces: tuple[CanonicalInterface, ...]
    labels: tuple[CanonicalLabel, ...]
    raw: Mapping[str, Any]


def canonical_label_key(value: Any) -> str | None:
    """Return the canonical internal label key, or ``None`` for unknown keys."""
    if value is None:
        return None
    return LABEL_KEY_ALIASES.get(str(value).strip().lower())


def _text(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _boolean(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "yes", "1", "y", "online"}:
        return True
    if normalized in {"false", "no", "0", "n", "offline"}:
        return False
    return None


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first(record: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None


def _normalise_interfaces(raw_interfaces: Any) -> tuple[CanonicalInterface, ...]:
    if not isinstance(raw_interfaces, list):
        return ()

    interfaces: list[CanonicalInterface] = []
    seen: set[tuple[str, str]] = set()
    for raw in raw_interfaces:
        if not isinstance(raw, Mapping):
            continue
        name = _text(_first(raw, "name", "interface_name")) or "unknown"
        network = _text(_first(raw, "network_type", "network", "type"))
        addresses = raw.get("addresses")
        if not isinstance(addresses, list):
            addresses = [_first(raw, "address", "ip_address")]
        for address in addresses:
            address = _text(address)
            if not address or (name, address) in seen:
                continue
            seen.add((name, address))
            interfaces.append(CanonicalInterface(name, address, network, dict(raw)))
    return tuple(interfaces)


def _normalise_labels(raw_labels: Any) -> tuple[CanonicalLabel, ...]:
    if not isinstance(raw_labels, list):
        return ()

    labels: list[CanonicalLabel] = []
    seen: set[tuple[str, str]] = set()
    for raw in raw_labels:
        if not isinstance(raw, Mapping):
            continue
        key = canonical_label_key(_first(raw, "key", "type", "label_type"))
        value = _text(raw.get("value"))
        if not key or not value or (key, value) in seen:
            continue
        seen.add((key, value))
        labels.append(CanonicalLabel(key, value, _text(raw.get("href"))))
    return tuple(labels)


def normalize_workload(record: Mapping[str, Any]) -> CanonicalWorkload:
    """Normalize a mock/API-shaped workload record into the canonical DTO.

    A stable Illumio href is required for a safe, idempotent synchronization.
    File adapters can supply another source-stable identifier as ``href`` in a
    future phase; this function intentionally refuses ambiguous records.
    """
    href = _text(record.get("href"))
    if not href:
        raise ValueError("Workload record has no usable href/source identifier")

    raw = record.get("raw_json")
    if not isinstance(raw, Mapping):
        raw = record

    return CanonicalWorkload(
        href=href,
        name=_text(record.get("name")),
        hostname=_text(record.get("hostname")),
        online=_boolean(record.get("online")),
        connectivity_status=_text(_first(record, "connectivity_status")),
        enforcement_mode=_text(_first(record, "enforcement_mode", "enforcement")),
        visibility_status=_text(_first(record, "visibility_status", "visibility")),
        policy_sync_status=_text(_first(record, "policy_sync_status", "security_policy_sync_state")),
        ransomware_exposure=_text(record.get("ransomware_exposure")),
        protection_status=_text(record.get("protection_status")),
        protection_coverage_score=_number(record.get("protection_coverage_score")),
        ven_version=_text(_first(record, "ven_version", "agent_version")),
        os=_text(_first(record, "os", "os_id")),
        os_release=_text(_first(record, "os_release", "os_detail")),
        interfaces=_normalise_interfaces(record.get("interfaces")),
        labels=_normalise_labels(record.get("labels")),
        raw=dict(raw),
    )
