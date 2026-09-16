from dotenv import load_dotenv
import os

load_dotenv()


class Settings:
    # Optional explicit URL is primarily for isolated tests. Production keeps
    # using the PostgreSQL component settings below.
    DATABASE_URL = os.getenv("DATABASE_URL", "")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "illumio_workloads")
    DB_USER = os.getenv("DB_USER", "")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")

    # Illumio PCE connection
    ILLUMIO_PCE_HOST = os.getenv("ILLUMIO_PCE_HOST", "")
    ILLUMIO_PCE_PORT = os.getenv("ILLUMIO_PCE_PORT", "8443")
    ILLUMIO_ORG_ID = os.getenv("ILLUMIO_ORG_ID", "1")
    ILLUMIO_API_KEY_ID = os.getenv("ILLUMIO_API_KEY_ID", "")
    ILLUMIO_API_KEY_SECRET = os.getenv("ILLUMIO_API_KEY_SECRET", "")

    # Set to "true" to use the real PCE instead of mock data
    ILLUMIO_USE_REAL_CLIENT = (
        os.getenv("ILLUMIO_USE_REAL_CLIENT", "false").lower() == "true"
    )
    # A second explicit gate is required before any approved label can be
    # written to PCE.  Real-client mode alone is intentionally read-only.
    ILLUMIO_ALLOW_PCE_WRITEBACK = (
        os.getenv("ILLUMIO_ALLOW_PCE_WRITEBACK", "false").lower() == "true"
    )

    # Web hosting is local-only by default.  PUBLIC mode is intentionally
    # fail-closed and requires Cloudflare Access JWT validation at the app.
    WEB_DEPLOYMENT_MODE = os.getenv("WEB_DEPLOYMENT_MODE", "local").lower()
    WEB_CLOUDFLARE_ACCESS_TEAM_DOMAIN = os.getenv(
        "WEB_CLOUDFLARE_ACCESS_TEAM_DOMAIN", ""
    ).rstrip("/")
    WEB_CLOUDFLARE_ACCESS_AUD = os.getenv("WEB_CLOUDFLARE_ACCESS_AUD", "")


settings = Settings()
