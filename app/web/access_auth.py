"""Fail-closed Cloudflare Access verification for public web deployments."""

from __future__ import annotations

import json
import time
from threading import Lock
from urllib.parse import urlparse

import jwt
import requests

from app.config import settings


class AccessConfigurationError(RuntimeError):
    """Raised when a public deployment lacks its mandatory access settings."""


class AccessTokenError(RuntimeError):
    """Raised when a Cloudflare Access assertion cannot be trusted."""


_KEY_CACHE: dict[str, tuple[float, dict[str, object]]] = {}
_KEY_CACHE_LOCK = Lock()
_CACHE_SECONDS = 300


def validate_public_access_configuration() -> None:
    """Validate configuration before the public server accepts user traffic."""
    team_domain = settings.WEB_CLOUDFLARE_ACCESS_TEAM_DOMAIN
    audience = settings.WEB_CLOUDFLARE_ACCESS_AUD
    parsed = urlparse(team_domain)
    if not audience:
        raise AccessConfigurationError("WEB_CLOUDFLARE_ACCESS_AUD is required in public mode.")
    if parsed.scheme != "https" or not parsed.netloc:
        raise AccessConfigurationError(
            "WEB_CLOUDFLARE_ACCESS_TEAM_DOMAIN must be an HTTPS Cloudflare Access team URL."
        )


def _public_keys(team_domain: str) -> dict[str, object]:
    now = time.monotonic()
    with _KEY_CACHE_LOCK:
        cached = _KEY_CACHE.get(team_domain)
        if cached and now - cached[0] < _CACHE_SECONDS:
            return cached[1]
    try:
        response = requests.get(
            f"{team_domain}/cdn-cgi/access/certs", timeout=5
        )
        response.raise_for_status()
        documents = response.json().get("keys", [])
        keys = {
            document["kid"]: jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(document))
            for document in documents
            if document.get("kid")
        }
    except Exception as exc:  # Do not identify an auth weakness to callers.
        raise AccessTokenError("Unable to retrieve Cloudflare Access signing keys.") from exc
    if not keys:
        raise AccessTokenError("Cloudflare Access returned no signing keys.")
    with _KEY_CACHE_LOCK:
        _KEY_CACHE[team_domain] = (now, keys)
    return keys


def verify_cloudflare_access_token(token: str) -> dict:
    """Verify signature, issuer, expiry, and application audience claim."""
    validate_public_access_configuration()
    try:
        key_id = jwt.get_unverified_header(token).get("kid")
        key = _public_keys(settings.WEB_CLOUDFLARE_ACCESS_TEAM_DOMAIN).get(key_id)
        if key is None:
            raise AccessTokenError("Cloudflare Access token used an unknown signing key.")
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.WEB_CLOUDFLARE_ACCESS_AUD,
            issuer=settings.WEB_CLOUDFLARE_ACCESS_TEAM_DOMAIN,
        )
        # L-7: Enforce application-side maximum session / token age (8 hours).
        iat = claims.get("iat")
        if iat and (time.time() - iat) > (8 * 3600):
            raise AccessTokenError("Cloudflare Access assertion exceeded maximum allowed session age (8h).")
        return claims
    except AccessTokenError:
        raise
    except Exception as exc:
        raise AccessTokenError("Cloudflare Access token verification failed.") from exc
