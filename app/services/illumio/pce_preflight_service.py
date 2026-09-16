"""Explicit, read-only PCE connectivity preflight."""

from app.config import settings


class PcePreflightService:
    @staticmethod
    def check():
        # Do not open a connection unless the operator has explicitly selected
        # the real-client mode in .env and restarted the app.
        if not settings.ILLUMIO_USE_REAL_CLIENT:
            return {
                "status": "DISABLED",
                "message": (
                    "Real PCE mode is disabled. Set ILLUMIO_USE_REAL_CLIENT=true "
                    "in .env and restart before testing connectivity."
                ),
            }
        from app.services.illumio.real_illumio_client import RealIllumioClient
        return RealIllumioClient().preflight()
