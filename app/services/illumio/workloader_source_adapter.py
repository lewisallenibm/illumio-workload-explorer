"""CSV adapter for local Workloader exports.

The adapter is deliberately responsible only for file validation and source
shape conversion.  It never writes to the database; callers must pass its
records to ``IllumioIngestionService`` after the preview is accepted.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_HEADER_ALIASES = {
    "href": "href", "workload_href": "href",
    "hostname": "hostname", "host_name": "hostname", "machinename": "hostname",
    "machine_name": "hostname", "computername": "hostname", "computer_name": "hostname",
    "name": "name", "workload_name": "name",
    "interfaces": "interfaces", "interface": "interfaces",
    "public_ip": "public_ip", "publicip": "public_ip", "ip_address": "ip_address",
    "os": "os", "os_id": "os_id", "os_detail": "os_detail",
    "app": "application", "application": "application",
    "role": "role", "env": "environment", "environment": "environment",
    "loc": "location", "location": "location",
    "region": "region", "enforcement": "enforcement_mode",
    "enforcement_mode": "enforcement_mode", "online": "online",
    "agent_status": "agent_status", "agent_health": "agent_health",
    "agent_version": "ven_version", "ven_version": "ven_version",
    "security_policy_sync_state": "policy_sync_status",
    "security_policy_applied_at": "security_policy_applied_at",
    "security_policy_received_at": "security_policy_received_at",
    "security_policy_refresh_at": "security_policy_refresh_at",
    "last_heartbeat_on": "last_heartbeat_on",
    "hours_since_last_heartbeat": "hours_since_last_heartbeat",
    "ransomware_exposure": "ransomware_exposure",
    "protection_coverage_score": "protection_coverage_score",
    "agent_id": "agent_id", "ven_href": "ven_href",
    "active_pce_fqdn": "active_pce_fqdn", "visibility": "visibility_status",
    "managed": "managed", "created_at": "created_at",
}

_LABEL_COLUMNS = ("application", "role", "environment", "location")


def _header_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().casefold()).strip("_")


def _value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass(frozen=True)
class WorkloaderPreview:
    filename: str
    headers: tuple[str, ...]
    known_columns: tuple[str, ...]
    unknown_columns: tuple[str, ...]
    identifier: str | None
    readable_rows: int
    malformed_rows: int
    warnings: tuple[str, ...]
    errors: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.errors


class WorkloaderValidationError(ValueError):
    def __init__(self, preview: WorkloaderPreview):
        self.preview = preview
        super().__init__("; ".join(preview.errors) or "Workloader CSV validation failed")


class WorkloaderCsvSourceAdapter:
    """Read a flexible Workloader CSV without imposing a production schema."""

    source_type = "workloader_csv"

    @classmethod
    def preview(cls, file_path: str | Path) -> WorkloaderPreview:
        path = Path(file_path)
        if not path.is_file():
            return cls._empty_preview(path, "Selected file does not exist or is not a file.")

        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle, strict=True)
                if not reader.fieldnames:
                    return cls._empty_preview(path, "CSV has no parseable header row.")
                headers = tuple(header.strip() for header in reader.fieldnames if header)
                mapping, known, unknown = cls._header_mapping(headers)
                identifier = "Illumio href" if "href" in mapping else (
                    "hostname/name fallback" if "hostname" in mapping or "name" in mapping else (
                        "VEN href fallback" if "ven_href" in mapping else None
                    )
                )
                errors: list[str] = []
                warnings: list[str] = []
                if identifier is None:
                    errors.append("No usable workload identifier column was detected (href, hostname, or name).")
                elif identifier != "Illumio href":
                    warnings.append(
                        "Rows without an Illumio href use a deterministic hostname/name-derived identifier."
                    )

                readable_rows = malformed_rows = 0
                identities: set[str] = set()
                for row_number, row in enumerate(reader, start=2):
                    if not any(_value(value) for value in row.values()):
                        continue
                    readable_rows += 1
                    identity = cls._identity(row, mapping)
                    if identity is None:
                        malformed_rows += 1
                        continue
                    if identity in identities:
                        malformed_rows += 1
                        continue
                    identities.add(identity)

                if readable_rows == 0:
                    errors.append("CSV contains no readable workload rows.")
                if malformed_rows:
                    errors.append(
                        f"{malformed_rows} row(s) have a missing or duplicate workload identity."
                    )
                return WorkloaderPreview(
                    filename=path.name, headers=headers, known_columns=tuple(sorted(known)),
                    unknown_columns=tuple(unknown), identifier=identifier,
                    readable_rows=readable_rows, malformed_rows=malformed_rows,
                    warnings=tuple(warnings), errors=tuple(errors),
                )
        except (OSError, UnicodeError, csv.Error) as exc:
            return cls._empty_preview(path, f"Unable to parse CSV: {exc}")

    @classmethod
    def load_records(cls, file_path: str | Path) -> tuple[WorkloaderPreview, list[dict]]:
        """Return source-shaped records only after a fully valid preview."""
        path = Path(file_path)
        preview = cls.preview(path)
        if not preview.valid:
            raise WorkloaderValidationError(preview)

        mapping, _, _ = cls._header_mapping(preview.headers)
        records: list[dict] = []
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle, strict=True)
                for row in reader:
                    if not any(_value(value) for value in row.values()):
                        continue
                    records.append(cls._record_from_row(row, mapping))
        except (OSError, UnicodeError, csv.Error) as exc:
            raise WorkloaderValidationError(cls._empty_preview(path, f"Unable to parse CSV: {exc}")) from exc
        return preview, records

    @staticmethod
    def _header_mapping(headers: tuple[str, ...]):
        mapping: dict[str, str] = {}
        known: set[str] = set()
        unknown: list[str] = []
        for header in headers:
            canonical = _HEADER_ALIASES.get(_header_key(header))
            if canonical is None:
                unknown.append(header)
                continue
            known.add(canonical)
            mapping.setdefault(canonical, header)
        return mapping, known, unknown

    @staticmethod
    def _identity(row: dict[str, Any], mapping: dict[str, str]) -> str | None:
        href = _value(row.get(mapping.get("href", "")))
        if href:
            return f"href:{href}"
        hostname = _value(row.get(mapping.get("hostname", ""))) or _value(row.get(mapping.get("name", "")))
        ven_href = _value(row.get(mapping.get("ven_href", "")))
        if not hostname and not ven_href:
            return None
        normalized = (hostname or ven_href).casefold().rstrip(".")
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        prefix = "hostname" if hostname else "ven"
        return f"workloader://{prefix}/{digest}"

    @classmethod
    def _record_from_row(cls, row: dict[str, Any], mapping: dict[str, str]) -> dict:
        fields = {
            canonical: _value(row.get(header))
            for canonical, header in mapping.items()
        }
        href = fields.get("href") or cls._identity(row, mapping)
        labels = [
            {"type": key, "value": fields[key]}
            for key in _LABEL_COLUMNS if fields.get(key)
        ]
        interfaces = cls._interfaces(fields)
        raw = {header: value for header, value in row.items()}
        return {
            "href": href,
            "hostname": fields.get("hostname") or fields.get("name"),
            "name": fields.get("name") or fields.get("hostname"),
            "online": fields.get("online"),
            "enforcement_mode": fields.get("enforcement_mode"),
            "visibility_status": fields.get("visibility_status"),
            "policy_sync_status": fields.get("policy_sync_status"),
            "ransomware_exposure": fields.get("ransomware_exposure"),
            "protection_coverage_score": fields.get("protection_coverage_score"),
            "ven_version": fields.get("ven_version"),
            "os": fields.get("os") or fields.get("os_id"),
            "os_release": fields.get("os_detail"),
            "interfaces": interfaces,
            "labels": labels,
            "raw_json": raw,
        }

    @staticmethod
    def _interfaces(fields: dict[str, str | None]) -> list[dict]:
        interfaces: list[dict] = []
        source = fields.get("interfaces")
        if source:
            try:
                parsed = json.loads(source)
            except json.JSONDecodeError:
                parsed = [part.strip() for part in re.split(r"[;,]", source) if part.strip()]
            if isinstance(parsed, dict):
                parsed = [parsed]
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        interfaces.append(item)
                    elif _value(item):
                        interfaces.append({"name": "source", "address": _value(item)})
        for field, name in (("public_ip", "public"), ("ip_address", "source")):
            if fields.get(field):
                interfaces.append({"name": name, "address": fields[field]})
        return interfaces

    @staticmethod
    def _empty_preview(path: Path, error: str) -> WorkloaderPreview:
        return WorkloaderPreview(
            filename=path.name, headers=(), known_columns=(), unknown_columns=(),
            identifier=None, readable_rows=0, malformed_rows=0, warnings=(), errors=(error,),
        )
