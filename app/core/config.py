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
    # Jeton Bearer du raccourci iPhone. Un an : il vit dans les Raccourcis iOS
    # et on n'a pas envie de le refaire tous les deux mois. C'est long, et
    # c'est précisément pour ça qu'il est révocable depuis le profil.
    api_token_expire_days: int = 365
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

    # Open-Meteo : gratuit, sans clé, en usage non commercial. Les URL sont en
    # configuration et non en dur pour pouvoir corriger un changement d'API sans
    # redéployer du code, jamais pour changer de fournisseur en douce.
    openmeteo_marine_url: str = "https://marine-api.open-meteo.com/v1/marine"
    openmeteo_forecast_url: str = "https://api.open-meteo.com/v1/forecast"
    openmeteo_archive_url: str = (
        "https://historical-forecast-api.open-meteo.com/v1/forecast"
    )
    # Modèle de vagues demandé nommément. Ne JAMAIS le changer en cours de
    # route : un biais constant s'annule dans l'apprentissage, un biais qui
    # change casse tout l'historique (cf. PROJET.md §7.3).
    forecast_wave_model: str = "meteofrance_wave"
    # Écrite sur chaque ligne de `forecasts`. À incrémenter à la main le jour
    # où Météo-France recalibre MFWAM : c'est la seule trace qui permettra de
    # segmenter l'historique d'apprentissage avant / après.
    forecast_model_version: str = "mfwam-2025"
    # Cache des spots « potentiels » : au-delà, on réinterroge à l'ouverture.
    forecast_cache_hours: int = 3
    # Plafond dur d'appels par passe d'ingestion (cf. PROJET.md §6).
    forecast_call_cap: int = 600
    # Au-delà, l'écran est servi depuis la base et le reste se fait derrière.
    forecast_on_demand_timeout_s: float = 5.0

    # Open Food Facts — complément au code-barres (lot 5). Gratuit et sans
    # clé, comme Open-Meteo. Le `User-Agent` est **exigé** par leurs conditions
    # d'utilisation : une base bénévole a le droit de savoir qui l'interroge.
    openfoodfacts_url: str = "https://world.openfoodfacts.org"
    openfoodfacts_user_agent: str = "Sport/0.1 (perso, non commercial)"

    # Overpass — catalogue OSM, interrogé uniquement par le script d'import
    # mensuel, jamais depuis l'API.
    overpass_url: str = "https://overpass-api.de/api/interpreter"

    # CANDHIS (lot 1 bis) — bouées du Cerema. Contrairement à Open-Meteo, il
    # faut une clé, et elle n'a **aucun défaut** : sans elle la fonctionnalité
    # s'éteint proprement, elle ne tombe pas sur une valeur bidon qui ferait
    # quarante appels à 401 par jour. Elle vit en variable Railway et nulle
    # part ailleurs (cf. CLAUDE.md, décidé le 15/09).
    candhis_api_key: str = ""
    candhis_url: str = "https://candhis.cerema.fr/API/v1"
    # Quota accordé avec le jeton : 150 requêtes par jour. On s'arrête à 140.
    # La marge n'est pas de la pudeur : notre compteur et celui du Cerema ne
    # tomberont jamais exactement d'accord sur le fuseau d'une journée, et le
    # code 423 de leur documentation dit qu'une IP peut être bannie.
    candhis_daily_call_cap: int = 140
    # Le fuseau des horodatages CANDHIS **n'est pas documenté** (cf.
    # docs/CANDHIS.md §5). UTC est la convention des archives océanographiques
    # et celle du reste de la base ; cette variable existe pour corriger sans
    # redéployer le jour où la mesure dirait le contraire.
    candhis_tz: str = "UTC"
    # Une bouée au-delà de cette distance ne décrit plus le même plan d'eau.
    observation_station_max_km: float = 30.0
    # Le job horaire : ~24 requêtes par jour, loin sous le plafond.
    candhis_ingest_interval_hours: int = 1

    @property
    def candhis_enabled(self) -> bool:
        """Pas de clé, pas de bouée — et c'est dit au démarrage, pas à l'usage."""
        return bool(self.candhis_api_key.strip())

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
