import requests
from requests.auth import HTTPBasicAuth

from app.config import settings
from app.services.illumio.illumio_client import IllumioClient


# Illumio PCE workloads endpoint returns pages of up to 500 by default.
# We fetch in chunks of 500 until we have all records.
_CHUNK_SIZE = 500


class RealIllumioClient(IllumioClient):
    """
    Connects to a real Illumio PCE via REST API v2.

    Credentials are read from environment variables (never hardcoded):
        ILLUMIO_PCE_HOST        e.g. my-pce.illumio.com
        ILLUMIO_PCE_PORT        e.g. 8443
        ILLUMIO_ORG_ID          e.g. 1
        ILLUMIO_API_KEY_ID      e.g. api_xxxxxxxxxxxxxxxx
        ILLUMIO_API_KEY_SECRET  e.g. xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

    Set ILLUMIO_USE_REAL_CLIENT=true in .env to activate this client.
    """

    def __init__(self):
        self._base = (
            f"https://{settings.ILLUMIO_PCE_HOST}"
            f":{settings.ILLUMIO_PCE_PORT}"
            f"/api/v2/orgs/{settings.ILLUMIO_ORG_ID}"
        )
        self._auth = HTTPBasicAuth(
            settings.ILLUMIO_API_KEY_ID,
            settings.ILLUMIO_API_KEY_SECRET,
        )
        # Set ILLUMIO_TLS_VERIFY=false in .env only for self-signed dev PCEs
        import os
        self._verify = (
            os.getenv("ILLUMIO_TLS_VERIFY", "true").lower() != "false"
        )
        if settings.WEB_DEPLOYMENT_MODE == "public" and not self._verify:
            raise ValueError(
                "ILLUMIO_TLS_VERIFY=false is prohibited in public deployment mode. "
                "Valid TLS certificates are required for all external connections."
            )

    @staticmethod
    def validate_configuration():
        """Fail clearly before any outbound PCE request is attempted."""
        missing = [
            name for name, value in {
                "ILLUMIO_PCE_HOST": settings.ILLUMIO_PCE_HOST,
                "ILLUMIO_API_KEY_ID": settings.ILLUMIO_API_KEY_ID,
                "ILLUMIO_API_KEY_SECRET": settings.ILLUMIO_API_KEY_SECRET,
            }.items() if not value
        ]
        if missing:
            raise ValueError(
                "Real Illumio client is not configured; missing " + ", ".join(missing)
            )
        host = settings.ILLUMIO_PCE_HOST.strip()
        if "://" in host or "/" in host:
            raise ValueError("ILLUMIO_PCE_HOST must be a hostname only (without https:// or a path)")
        if not str(settings.ILLUMIO_PCE_PORT).isdigit():
            raise ValueError("ILLUMIO_PCE_PORT must be a numeric port")
        if not str(settings.ILLUMIO_ORG_ID).isdigit():
            raise ValueError("ILLUMIO_ORG_ID must be numeric")

    def _get(self, path, params=None):
        self.validate_configuration()
        url = f"{self._base}{path}"
        resp = requests.get(
            url,
            auth=self._auth,
            params=params,
            verify=self._verify,
            timeout=30,
        )
        resp.raise_for_status()
        return resp

    def _put(self, path, body):
        self.validate_configuration()
        url = f"{self._base}{path}"
        resp = requests.put(
            url,
            auth=self._auth,
            json=body,
            verify=self._verify,
            timeout=30,
        )
        resp.raise_for_status()
        return resp

    def _post(self, path, body):
        self.validate_configuration()
        url = f"{self._base}{path}"
        resp = requests.post(
            url,
            auth=self._auth,
            json=body,
            verify=self._verify,
            timeout=30,
        )
        resp.raise_for_status()
        return resp

    def get_workloads(self):
        """
        Fetch all workloads from the PCE.
        Illumio paginates via offset/max_results.
        Returns a list of raw dicts in the same shape MockDataGenerator uses.
        """
        workloads = []
        offset = 0

        while True:
            resp = self._get(
                "/workloads",
                params={
                    "max_results": _CHUNK_SIZE,
                    "offset": offset,
                    "representation": "workload_labels",
                },
            )

            page = resp.json()
            if not isinstance(page, list):
                raise ValueError("PCE workloads response must be a JSON list")

            if not page:
                break

            for raw in page:
                workloads.append(
                    self._normalise_workload(raw)
                )

            # Illumio returns Illumio-Total-Count in the response header
            total_header = resp.headers.get(
                "X-Total-Count",
                resp.headers.get("Illumio-Total-Count", None),
            )

            if total_header is not None:
                try:
                    total = int(total_header)
                except (TypeError, ValueError) as exc:
                    raise ValueError("PCE returned an invalid workload total-count header") from exc
                if total < offset + len(page):
                    raise ValueError("PCE workload total-count header is smaller than the returned page")
                if offset + len(page) >= total:
                    break
            else:
                # No header — stop when a short page is returned
                if len(page) < _CHUNK_SIZE:
                    break

            # Advance by what was actually received.  This avoids skipping
            # records if a PCE returns a valid partial page before the end.
            offset += len(page)

        return workloads

    def get_labels(self):
        """Fetch all labels from the PCE."""
        resp = self._get("/labels")
        payload = resp.json()
        if not isinstance(payload, list):
            raise ValueError("PCE labels response must be a JSON list")
        labels = []
        for raw in payload:
            labels.append(
                {
                    "href": raw.get("href"),
                    "type": raw.get("key"),
                    "value": raw.get("value"),
                }
            )
        return labels

    def preflight(self):
        """Perform one read-only, one-row request to verify PCE access."""
        response = self._get(
            "/workloads",
            params={"max_results": 1, "offset": 0, "representation": "workload_labels"},
        )
        total = response.headers.get("X-Total-Count", response.headers.get("Illumio-Total-Count"))
        return {
            "status": "CONNECTED",
            "workload_count": int(total) if total and str(total).isdigit() else None,
        }

    def get_workload(self, href):
        """Fetch a single workload by its PCE href."""
        resp = self._get(self._path_from_href(href))
        return resp.json()

    def update_workload_labels(self, href, labels):
        """
        PUT updated labels onto a workload.
        labels: list of {"href": "/orgs/1/labels/123"} dicts.
        """
        self._put(self._path_from_href(href), {"labels": labels})

    def _path_from_href(self, href):
        """Make an org-relative endpoint path from either PCE href shape.

        The client base already contains ``/api/v2/orgs/<id>``.  PCE hrefs
        commonly contain ``/orgs/<id>/...``; appending those unchanged would
        duplicate the organization path and produce an invalid request URL.
        """
        if not href:
            raise ValueError("A workload href is required")

        api_prefix = f"/api/v2/orgs/{settings.ILLUMIO_ORG_ID}"
        org_prefix = f"/orgs/{settings.ILLUMIO_ORG_ID}"
        if href.startswith(api_prefix):
            path = href[len(api_prefix):]
        elif href.startswith(org_prefix):
            path = href[len(org_prefix):]
        else:
            path = href

        if not path.startswith("/"):
            path = f"/{path}"
        if not path.startswith("/workloads/"):
            raise ValueError(f"Unexpected workload href: {href}")
        return path

    def find_or_create_label(self, key, value):
        """
        Find an existing label href by key+value, or create it if missing.
        Returns the label href string.
        """
        # Try to find existing
        resp = self._get("/labels", params={"key": key, "value": value})
        existing = resp.json()
        if existing:
            return existing[0]["href"]

        # Create new label
        resp = self._post("/labels", {"key": key, "value": value})
        return resp.json()["href"]

    # ------------------------------------------------------------------
    # Normalise PCE JSON into the flat dict shape the sync service uses
    # ------------------------------------------------------------------

    def _normalise_workload(self, raw):
        interfaces = []
        for iface in raw.get("interfaces", []):
            # PCE may return multiple addresses per interface
            for addr in iface.get("addresses", [iface.get("address", "")]):
                if addr:
                    interfaces.append(
                        {
                            "name": iface.get("name", ""),
                            "address": addr,
                            "network_type": iface.get(
                                "network", ""
                            ),
                        }
                    )

        labels = []
        for lbl in raw.get("labels", []):
            labels.append(
                {
                    "href": lbl.get("href", ""),
                    "type": lbl.get("key", ""),
                    "value": lbl.get("value", ""),
                }
            )

        ven = raw.get("ven") or {}
        agent = raw.get("agent") or {}

        return {
            "href": raw.get("href", ""),
            "name": raw.get("name", ""),
            "hostname": raw.get("hostname", ""),
            "online": raw.get("online", False),
            "connectivity_status": (
                agent.get("status", {}).get("security_policy_sync_state")
                or raw.get("connectivity_status", "")
            ),
            "enforcement_mode": raw.get("enforcement_mode", ""),
            "visibility_status": raw.get("visibility_level", ""),
            "policy_sync_status": (
                agent.get("status", {}).get("security_policy_sync_state", "")
            ),
            "protection_status": raw.get("protection_coverage", {}).get(
                "ike_authentication_certificate", ""
            ),
            "protection_coverage_score": raw.get(
                "protection_coverage", {}
            ).get("coverage_summary", {}).get("coverage_score"),
            "ven_version": (
                ven.get("version")
                or agent.get("status", {}).get("agent_version", "")
            ),
            "os": raw.get("os_id", ""),
            "os_release": raw.get("os_detail", ""),
            "interfaces": interfaces,
            "labels": labels,
            "raw_json": raw,
        }
