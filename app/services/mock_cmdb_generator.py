"""
Mock CMDB generator — produces realistic UPS-style CMDB data at scale.

Generates up to 300 000 CI records that mirror the structure of a real
ServiceNow cmdb_rel_ci / Inventory Lookup export.

Deliberately bakes in mismatches so the reconciliation engine has real
work to do:
  - ~60% of records overlap with mock Illumio workloads (matched hostname)
  - ~15% have a wrong Role label
  - ~10% have a wrong Environment label
  - ~8%  have a wrong Location label
  - ~7%  have no label values at all (missing)
  - Remaining CMDB records have no matching Illumio workload (missing_in_illumio)
"""

from datetime import datetime, timedelta
from random import choice, randint, random, seed


# Realistic UPS location codes
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

_PARENT_APPS = [
    "Zscaler - ZPA Enterprise", "UPS Core Platform", "Logistics Suite",
    "Finance ERP", "HR Systems", "Network Operations", "Security Platform",
    "Analytics Platform", "eCommerce Platform", "Mobile API Gateway",
]

_REGIONS = [
    "Northeast", "Southeast", "Midwest", "Southwest", "Northwest",
    "Central", "International",
]

_DISTRICTS = [
    "District-1", "District-2", "District-3", "District-4",
    "District-5", "District-6", "District-7", "District-8",
]

_OS_LIST = ["Windows Server 2019", "Windows Server 2022", "RHEL 8", "RHEL 9",
            "Ubuntu 20.04", "Ubuntu 22.04", "CentOS 7"]

_DATACENTERS = ["DC-MAHWAH", "DC-ATLANTA", "DC-CHICAGO", "DC-DALLAS",
                "DC-SEATTLE", "DC-PHOENIX", "AWS-USE1", "AWS-USW2", "Azure-EUS"]

# Hostname prefix pools matching real UPS naming conventions
_PREFIXES = [
    "lsysp", "gaalplpapp", "njrapp", "atlapps", "chiapp",
    "dallapp", "seatapp", "phxapp", "miaapp", "bosapp",
    "denapp", "pdxapp", "mnpapp", "detapp", "mcisapp",
]


def _make_hostname(prefix, index):
    return f"{prefix}{index:08x}"


def _make_ip(index):
    # Spread across RFC-1918 ranges
    third = (index // 254) % 254
    fourth = (index % 254) + 1
    if index % 3 == 0:
        return f"10.{(index // 65536) % 256}.{third}.{fourth}"
    elif index % 3 == 1:
        return f"172.{16 + (index // 65536) % 16}.{third}.{fourth}"
    else:
        return f"192.168.{third}.{fourth}"


def _random_date(days_ago_max=365):
    return datetime.utcnow() - timedelta(days=randint(0, days_ago_max))


class MockCmdbGenerator:

    @staticmethod
    def generate(
        count=300_000,
        illumio_hostnames=None,
        overlap_ratio=0.60,
        mismatch_role_ratio=0.15,
        mismatch_env_ratio=0.10,
        mismatch_loc_ratio=0.08,
        missing_labels_ratio=0.07,
        random_seed=42,
    ):
        """
        Generate mock CMDB CI records.

        Args:
            count:                Total number of CMDB rows to generate.
            illumio_hostnames:    Optional list of Illumio hostnames to overlap with.
                                  If provided, overlap_ratio of records will use these hostnames.
            overlap_ratio:        Fraction of CMDB records that share a hostname with Illumio.
            mismatch_*_ratio:     Fraction of overlapping records with a deliberate label mismatch.
            random_seed:          For reproducibility.

        Returns:
            list of dicts matching the CmdbCi column structure.
        """
        seed(random_seed)
        records = []

        # How many records overlap with Illumio hostnames
        if illumio_hostnames:
            overlap_count = min(int(count * overlap_ratio), len(illumio_hostnames))
        else:
            overlap_count = 0

        # Remaining records are pure CMDB (no matching Illumio workload)
        pure_cmdb_count = count - overlap_count

        # -- Records that overlap with Illumio --
        ilumio_sample = (
            list(illumio_hostnames)[:overlap_count]
            if illumio_hostnames
            else []
        )

        for i, hostname in enumerate(ilumio_sample):
            role = choice(_ROLES)
            env = choice(_ENVIRONMENTS)
            loc = choice(_LOCATIONS)
            app = choice(_APPS)

            # Deliberately corrupt some labels to create mismatches
            r = random()
            if r < missing_labels_ratio:
                role = env = loc = app = None
            else:
                if random() < mismatch_role_ratio:
                    role = choice([r for r in _ROLES if r != role]) + "-WRONG"
                if random() < mismatch_env_ratio:
                    env = choice([e for e in _ENVIRONMENTS if e != env]) + "-WRONG"
                if random() < mismatch_loc_ratio:
                    loc = choice([l for l in _LOCATIONS if l != loc]) + "-WRONG"

            records.append(
                MockCmdbGenerator._make_record(
                    hostname=hostname,
                    cmdb_role=role,
                    cmdb_env=env,
                    cmdb_loc=loc,
                    cmdb_app=app,
                    index=i,
                )
            )

        # -- Pure CMDB records with no Illumio match --
        for i in range(pure_cmdb_count):
            prefix = choice(_PREFIXES)
            hostname = _make_hostname(prefix, 900_000 + i)
            records.append(
                MockCmdbGenerator._make_record(
                    hostname=hostname,
                    cmdb_role=choice(_ROLES),
                    cmdb_env=choice(_ENVIRONMENTS),
                    cmdb_loc=choice(_LOCATIONS),
                    cmdb_app=choice(_APPS),
                    index=overlap_count + i,
                )
            )

        return records

    @staticmethod
    def _make_record(hostname, cmdb_role, cmdb_env, cmdb_loc, cmdb_app, index):
        parent = choice(_PARENT_APPS)
        return {
            "hostname":               hostname,
            "cmdb_app":               cmdb_app,
            "cmdb_role":              cmdb_role,
            "cmdb_env":               cmdb_env,
            "cmdb_loc":               cmdb_loc,
            "ven_installed":          choice([True, True, True, False]),
            "region":                 choice(_REGIONS),
            "district":               choice(_DISTRICTS),
            "parent_application":     parent,
            "parent_sys_class_name":  "Business Application",
            "child_sys_class_name":   "Application Server",
            "sys_created_on":         _random_date(730),
            "u_last_seen":            _random_date(90),
            "os":                     choice(_OS_LIST),
            "data_center":            choice(_DATACENTERS),
            "ip_with_default_gw":     _make_ip(index),
        }
