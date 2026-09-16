"""
MockDataGenerator — produces realistic UPS-style Illumio workload data.

Default count: 40 000 workloads with real-looking hostnames, proper
R-/E-/L-/A- label structure, multiple interfaces, and varied VEN state.
"""

from hashlib import sha256
from random import choice, randint, random, seed as _seed


_LOCATIONS = [
    "L-NJRAR", "L-GAALP", "L-UPS-TEMP", "L-ATLAN", "L-CHICG",
    "L-DALLX", "L-SEATL", "L-PHOEN", "L-MIAMI", "L-BOSTO",
    "L-DENVE", "L-PORTL", "L-MINNA", "L-DETRO", "L-KANSM",
]

_ENVIRONMENTS = [
    "E-PROD", "E-UPS-TEMP", "E-DEV", "E-QA", "E-STAGING", "E-DR",
]

_ROLES = [
    "R-APP_CONNECTOR", "R-UPS-TEMP", "R-WEB", "R-DB",
    "R-MIDDLEWARE", "R-BATCH", "R-MONITOR", "R-BACKUP",
]

_APPS = [
    "CSA-TOK-ZSCALER", "A-UPS-CORE", "A-LOGISTICS", "A-FINANCE",
    "A-HR-SYSTEMS", "A-NETWORK-OPS", "A-SECURITY", "A-ANALYTICS",
    "A-ECOMMERCE", "A-MOBILE-API",
]

_ENFORCEMENT = ["full", "visibility", "selective"]
_POLICY_SYNC = ["synced", "pending", "active"]
_PROTECTION = ["protected", "partial", "unprotected"]
_VEN_VERSIONS = ["23.5.1", "23.6.0", "24.1.0", "24.2.0"]
_OS_LIST = [
    ("windows-server", "Windows Server 2019 Standard"),
    ("windows-server", "Windows Server 2022 Datacenter"),
    ("rhel", "Red Hat Enterprise Linux 8.8"),
    ("rhel", "Red Hat Enterprise Linux 9.2"),
    ("ubuntu", "Ubuntu 20.04.6 LTS"),
    ("ubuntu", "Ubuntu 22.04.3 LTS"),
    ("centos", "CentOS Linux 7 (Core)"),
]

# UPS hostname prefix pools
_PREFIXES = [
    "lsysp", "gaalplpapp", "njrapp", "atlapps", "chiapp",
    "dallapp", "seatapp", "phxapp", "miaapp", "bosapp",
    "denapp", "pdxapp", "mnpapp", "detapp", "mcisapp",
]


def _make_ip(index, offset=0):
    third = ((index + offset) // 254) % 254
    fourth = ((index + offset) % 254) + 1
    segment = (index + offset) % 3
    if segment == 0:
        return f"10.{((index + offset) // 65536) % 256}.{third}.{fourth}"
    elif segment == 1:
        return f"172.{16 + ((index + offset) // 65536) % 16}.{third}.{fourth}"
    else:
        return f"192.168.{third}.{fourth}"


def _label_href(label_type, value):
    """Stable mock identity: one href always represents one label value."""
    digest = sha256(f"{label_type}:{value}".encode("utf-8")).hexdigest()[:16]
    return f"/orgs/1/labels/{label_type}-{digest}"


class MockDataGenerator:

    @staticmethod
    def generate(count=40_000, random_seed=42):
        _seed(random_seed)
        records = []

        for i in range(count):
            prefix = choice(_PREFIXES)
            hostname = f"{prefix}{i:08x}"
            os_id, os_detail = choice(_OS_LIST)

            # Build interfaces — 1 primary + occasional secondary
            interfaces = [
                {
                    "name": "eth0",
                    "address": _make_ip(i),
                    "network_type": "brn",
                }
            ]
            if random() < 0.3:
                interfaces.append({
                    "name": "eth1",
                    "address": _make_ip(i, offset=50_000),
                    "network_type": "brn",
                })

            # Labels
            labels = [
                {
                    "href": _label_href("role", role := choice(_ROLES)),
                    "type": "role",
                    "value": role,
                },
                {
                    "href": _label_href("environment", environment := choice(_ENVIRONMENTS)),
                    "type": "environment",
                    "value": environment,
                },
                {
                    "href": _label_href("location", location := choice(_LOCATIONS)),
                    "type": "location",
                    "value": location,
                },
                {
                    "href": _label_href("application", application := choice(_APPS)),
                    "type": "application",
                    "value": application,
                },
            ]

            # ~5% of workloads have no labels (unlabelled)
            if random() < 0.05:
                labels = []

            records.append({
                "href": f"/orgs/1/workloads/{i:08x}",
                "name": hostname.upper(),
                "hostname": hostname,
                "online": random() < 0.72,
                "connectivity_status": choice(["online", "offline"]),
                "enforcement_mode": choice(_ENFORCEMENT),
                "policy_sync_status": choice(_POLICY_SYNC),
                "protection_status": choice(_PROTECTION),
                "protection_coverage_score": randint(0, 100),
                "ven_version": choice(_VEN_VERSIONS),
                "os": os_id,
                "os_release": os_detail,
                "interfaces": interfaces,
                "labels": labels,
            })

        return records
