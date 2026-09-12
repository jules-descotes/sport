from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Sport"
    app_version: str = "0.1.0"
    debug: bool = True

    # Base de données — SQLite en local et pour les tests, Postgres en production.
    database_url: str = "sqlite+aiosqlite:///./sport.db"

    # Auth — un seul utilisateur, créé au démarrage.
    secret_key: str = "sport-secret-dev-key-change-in-production"
    admin_email: str = "jules@atelier-okomi.fr"
    admin_password: str = "ChangeMe123!"
    # Session longue : on se connecte une fois depuis le téléphone, jamais plus.
    access_token_expire_days: int = 60
    session_cookie_name: str = "sport_session"
    # Vide en local (cookie lié à l'hôte). En production : ".atelier-okomi.fr",
    # pour que le cookie posé par api-sport soit renvoyé depuis sport.
    session_cookie_domain: str = ""

    # Un seul hôte, déclaré partout (cf. CLAUDE.md).
    site_url: str = "http://localhost:3000"

    # Stockage des photos de session (lot 2+).
    storage_backend: str = "local"
    media_dir: str = "media"
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "sport-media"
    r2_public_url: str = ""

    # Emails et supervision.
    resend_api_key: str = ""
    emails_from: str = "bonjour@atelier-okomi.fr"
    sentry_dsn: str = ""

    # Sources externes (lot 1).
    windy_webcams_api_key: str = ""
    tides_api_key: str = ""
    forecast_ingest_interval_hours: int = 3

    @field_validator("database_url", mode="after")
    @classmethod
    def _force_async_driver(cls, value: str) -> str:
        """Railway fournit un DATABASE_URL en `postgresql://` (driver synchrone).

        SQLAlchemy async a besoin d'asyncpg : on convertit à la lecture plutôt
        que de dépendre d'une variable d'environnement correctement écrite.
        """
        if value.startswith("postgresql+"):
            return value
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+asyncpg://", 1)
        return value

    @property
    def cors_origins(self) -> list[str]:
        origins = {
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            self.site_url.rstrip("/"),
        }
        return sorted(o for o in origins if o)

    @property
    def sync_database_url(self) -> str:
        """URL à driver synchrone, pour Alembic en mode hors ligne."""
        return self.database_url.replace("+asyncpg", "").replace("+aiosqlite", "")


settings = Settings()
