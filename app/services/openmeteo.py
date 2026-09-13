"""Client Open-Meteo — houle MFWAM, vent, niveau de la mer.

Un seul endroit parle à l'extérieur. Trois règles y sont tenues, et elles
viennent toutes du cadrage :

1. **Modèle explicite.** `models=meteofrance_wave` (MFWAM) est demandé
   nommément, jamais le « best match » : on ne change ni de source ni de modèle
   en cours de route, sous peine de casser tout l'historique d'apprentissage
   (cf. PROJET.md §7.3). La version du modèle est portée par la configuration
   et écrite sur chaque ligne.
2. **Plafond dur.** 600 appels par passe au maximum, quoi qu'il arrive. Le
   quota gratuit d'Open-Meteo est très au-dessus, mais un bug de boucle sur un
   catalogue mondial ne doit pas pouvoir le consommer.
3. **Backoff sur 429.** Exponentiel, en respectant `Retry-After` s'il est là.

Pourquoi deux appels marins par spot : `models=meteofrance_wave` restreint la
réponse aux variables du modèle de vagues, et ni le niveau de la mer ni la
température de l'eau n'en font partie. Les demander dans le même appel
reviendrait à les perdre en silence. Le budget le permet largement (20 spots ×
3 appels par passe, contre un plafond de 600).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Variables de vagues, servies par MFWAM.
WAVE_VARIABLES = (
    "wave_height",
    "wave_direction",
    "wave_period",
    "wave_peak_period",
    "swell_wave_height",
    "swell_wave_direction",
    "swell_wave_period",
    "swell_wave_peak_period",
    "secondary_swell_wave_height",
    "secondary_swell_wave_direction",
    "secondary_swell_wave_period",
)

# Variables marines hors modèle de vagues : marée et température de l'eau.
SEA_VARIABLES = ("sea_level_height_msl", "sea_surface_temperature")

WIND_VARIABLES = ("wind_speed_10m", "wind_gusts_10m", "wind_direction_10m")

# Correspondance nom Open-Meteo -> colonne de `forecasts`.
COLUMN_BY_VARIABLE: dict[str, str] = {
    "wave_height": "wave_height_m",
    "wave_direction": "wave_direction_deg",
    "wave_period": "wave_period_s",
    "wave_peak_period": "wave_peak_period_s",
    "swell_wave_height": "swell_height_m",
    "swell_wave_direction": "swell_direction_deg",
    "swell_wave_period": "swell_period_s",
    "swell_wave_peak_period": "swell_peak_period_s",
    "secondary_swell_wave_height": "secondary_swell_height_m",
    "secondary_swell_wave_direction": "secondary_swell_direction_deg",
    "secondary_swell_wave_period": "secondary_swell_period_s",
    "sea_level_height_msl": "sea_level_m",
    "sea_surface_temperature": "water_temperature_c",
    "wind_speed_10m": "wind_speed_kt",
    "wind_gusts_10m": "wind_gust_kt",
    "wind_direction_10m": "wind_direction_deg",
}

MAX_RETRIES = 4
BACKOFF_BASE_S = 1.5


class CallBudgetExhausted(RuntimeError):
    """Le plafond dur d'appels de la passe est atteint. La passe s'arrête."""


@dataclass
class CallBudget:
    """Plafond d'appels d'une passe d'ingestion.

    Codé en dur à 600 (cf. PROJET.md §6) : c'est un garde-fou contre une boucle
    qui partirait sur le catalogue mondial, pas un paramètre de réglage.
    """

    limit: int = 600
    used: int = 0

    def take(self) -> None:
        if self.used >= self.limit:
            raise CallBudgetExhausted(
                f"plafond de {self.limit} appels atteint pour cette passe"
            )
        self.used += 1

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)


@dataclass
class HourlyBundle:
    """Lignes horaires normalisées, prêtes pour l'upsert.

    `rows` est indexé par l'horodatage UTC ; chaque valeur est un dictionnaire
    de colonnes de `forecasts`. Les variables absentes de la réponse (modèle
    qui ne les sert pas, trou de données) restent simplement absentes.
    """

    rows: dict[datetime, dict[str, Optional[float]]] = field(default_factory=dict)

    def merge(self, other: "HourlyBundle") -> None:
        for ts, values in other.rows.items():
            self.rows.setdefault(ts, {}).update(values)

    def sorted_rows(self) -> list[tuple[datetime, dict[str, Optional[float]]]]:
        return sorted(self.rows.items())


def parse_hourly(payload: dict[str, Any]) -> HourlyBundle:
    """Traduit une réponse Open-Meteo en lignes de `forecasts`.

    Open-Meteo renvoie des colonnes parallèles : `time`, puis une liste par
    variable. On transpose, on convertit les horodatages — toujours demandés en
    UTC — et on ignore les variables qu'on ne stocke pas.
    """
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []

    bundle = HourlyBundle()
    for index, raw_ts in enumerate(times):
        try:
            ts = datetime.fromisoformat(raw_ts)
        except (TypeError, ValueError):
            continue
        ts = ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts.astimezone(UTC)

        values: dict[str, Optional[float]] = {}
        for variable, column in COLUMN_BY_VARIABLE.items():
            series = hourly.get(variable)
            if series is None or index >= len(series):
                continue
            value = series[index]
            values[column] = None if value is None else float(value)

        if values:
            bundle.rows[ts] = values

    return bundle


class OpenMeteoClient:
    """Enveloppe httpx : plafond d'appels, backoff, et rien d'autre.

    Aucune clé : Open-Meteo est gratuit et sans authentification en usage non
    commercial. Si le projet devient commercial un jour, c'est ici que ça se
    verra (cf. CLAUDE.md, points de vigilance).
    """

    def __init__(
        self,
        client: Optional[httpx.AsyncClient] = None,
        budget: Optional[CallBudget] = None,
    ) -> None:
        self._client = client
        self._owns_client = client is None
        self.budget = budget or CallBudget()

    async def __aenter__(self) -> "OpenMeteoClient":
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(20.0))
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._client is None:  # pragma: no cover - usage hors contexte
            raise RuntimeError("OpenMeteoClient doit être utilisé comme contexte async")

        self.budget.take()

        delay = BACKOFF_BASE_S
        for attempt in range(1, MAX_RETRIES + 1):
            response = await self._client.get(url, params=params)

            if response.status_code == 429 and attempt < MAX_RETRIES:
                # Open-Meteo compte à la minute, à l'heure et au jour : une
                # attente courte suffit presque toujours à repasser sous le
                # seuil de la minute.
                retry_after = response.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else delay
                logger.warning(
                    "Open-Meteo 429 sur %s — nouvelle tentative dans %.1f s (%d/%d)",
                    url,
                    wait,
                    attempt,
                    MAX_RETRIES,
                )
                await asyncio.sleep(wait)
                delay *= 2
                continue

            response.raise_for_status()
            return response.json()

        raise RuntimeError("inatteignable")  # pragma: no cover

    # -- Prévision ---------------------------------------------------------

    async def fetch_forecast(
        self, lat: float, lon: float, forecast_days: int = 5
    ) -> HourlyBundle:
        """Prévision horaire sur `forecast_days` jours : houle, mer, vent."""
        bundle = HourlyBundle()

        waves = await self._get(
            settings.openmeteo_marine_url,
            {
                "latitude": lat,
                "longitude": lon,
                "hourly": ",".join(WAVE_VARIABLES),
                "models": settings.forecast_wave_model,
                "forecast_days": forecast_days,
                "timezone": "UTC",
                "cell_selection": "sea",
            },
        )
        bundle.merge(parse_hourly(waves))

        sea = await self._get(
            settings.openmeteo_marine_url,
            {
                "latitude": lat,
                "longitude": lon,
                "hourly": ",".join(SEA_VARIABLES),
                "forecast_days": forecast_days,
                "timezone": "UTC",
                "cell_selection": "sea",
            },
        )
        bundle.merge(parse_hourly(sea))

        wind = await self._get(
            settings.openmeteo_forecast_url,
            {
                "latitude": lat,
                "longitude": lon,
                "hourly": ",".join(WIND_VARIABLES),
                "forecast_days": forecast_days,
                "timezone": "UTC",
                "wind_speed_unit": "kn",
            },
        )
        bundle.merge(parse_hourly(wind))

        return bundle

    async def fetch_sea_level(
        self,
        lat: float,
        lon: float,
        past_days: int = 30,
        forecast_days: int = 6,
    ) -> HourlyBundle:
        """Niveau marin seul, passé compris — la source du coefficient de marée.

        **Un seul appel** au lieu des trois de `fetch_forecast` : le marégraphe
        de Brest n'a que faire des vagues et du vent, et ce serait deux appels
        par passe pour des colonnes que personne ne lira jamais.

        `past_days` est ce qui rend le calcul possible dès le premier jour : le
        niveau moyen du modèle se mesure sur trente jours glissants, et sans ce
        paramètre il faudrait attendre un mois de passes pour en accumuler
        autant. Open-Meteo va jusqu'à 92 jours en arrière sur le même appel.
        """
        payload = await self._get(
            settings.openmeteo_marine_url,
            {
                "latitude": lat,
                "longitude": lon,
                "hourly": "sea_level_height_msl",
                "past_days": past_days,
                "forecast_days": forecast_days,
                "timezone": "UTC",
                "cell_selection": "sea",
            },
        )
        return parse_hourly(payload)

    # -- Archive -----------------------------------------------------------

    async def fetch_archive(
        self, lat: float, lon: float, start: date, end: date
    ) -> HourlyBundle:
        """Conditions constatées sur une fenêtre passée.

        Sert le volet `observed` du `conditions_snapshot`, pour n'importe quel
        spot du monde, ingéré ou non. Le passé se récupère ; la prévision telle
        qu'elle était la veille, non (cf. PROJET.md §6).
        """
        window = {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "timezone": "UTC",
        }
        bundle = HourlyBundle()

        waves = await self._get(
            settings.openmeteo_marine_url,
            {
                "latitude": lat,
                "longitude": lon,
                "hourly": ",".join(WAVE_VARIABLES),
                "models": settings.forecast_wave_model,
                "cell_selection": "sea",
                **window,
            },
        )
        bundle.merge(parse_hourly(waves))

        sea = await self._get(
            settings.openmeteo_marine_url,
            {
                "latitude": lat,
                "longitude": lon,
                "hourly": ",".join(SEA_VARIABLES),
                "cell_selection": "sea",
                **window,
            },
        )
        bundle.merge(parse_hourly(sea))

        wind = await self._get(
            settings.openmeteo_archive_url,
            {
                "latitude": lat,
                "longitude": lon,
                "hourly": ",".join(WIND_VARIABLES),
                "wind_speed_unit": "kn",
                **window,
            },
        )
        bundle.merge(parse_hourly(wind))

        return bundle
