"""Figeage des conditions d'une session — `conditions_snapshot`.

C'est la seule décision de modèle irrattrapable après coup (cf. PROJET.md §5).
Un point unique ne porte aucune tendance ; on fige donc une **fenêtre
T−2 h / T−1 h / T0**, en deux volets :

- `forecast` — ce qui était annoncé. Lu dans la table `forecasts`, donc garanti
  seulement sur les spots maison : la prévision telle qu'elle était la veille
  n'est pas reconstituable après coup, l'API Previous Runs d'Open-Meteo ne
  couvre pas les vagues.
- `observed` — ce qui s'est passé. Remonté de l'archive Open-Meteo à
  l'enregistrement, **pour n'importe quel spot du monde**, ingéré ou non, et
  pour une session saisie six mois plus tard. C'est là-dessus que le modèle de
  goût s'entraîne (cf. PROJET.md §7.3).

Règle de robustesse : un échec de backfill ne doit **jamais** empêcher
d'enregistrer une session. La session part avec un volet `observed` vide et une
raison ; elle sera complétée plus tard. Perdre une session pour un timeout
réseau serait le comble, vu que le risque du projet est la friction de saisie.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.forecast import Forecast
from app.models.spot import Spot
from app.services.forecast_reads import latest_forecasts_select
from app.services.openmeteo import HourlyBundle, OpenMeteoClient
from app.services.scoring import TideContext

logger = logging.getLogger(__name__)

# Les heures **avant** le début, relatives à lui. Deux points d'approche, c'est
# le minimum pour lire une pente : une houle de 1,5 m qui monte et une houle de
# 1,5 m qui s'écroule ne donnent pas la même session (features 12 et 13).
LEAD_HOURS = (-2, -1)

# La fenêtre de base — approche plus l'heure du départ. C'est ce que portaient
# toutes les sessions jusqu'au 13/09, et ce que porte encore une session dont
# on ne connaît pas la durée.
WINDOW_HOURS = (*LEAD_HOURS, 0)

# Au-delà, on n'étend plus : une session de plus de six heures est une erreur
# de saisie, et tirer une fenêtre de douze heures multiplierait le volume du
# snapshot pour de la donnée que personne n'a vécue.
MAX_SESSION_HOURS = 6


def window_offsets(duration_min: Optional[int] = None) -> tuple[int, ...]:
    """Les heures de la fenêtre, en décalage par rapport au début.

    Sans durée : T−2 h, T−1 h, T0 — la fenêtre historique.

    Avec une durée : la même approche, **plus une ligne par heure entamée** de
    la session. C'est ce qui rend les segments horaires exploitables (décidé le
    13/09) : chaque heure notée doit pouvoir s'apparier à *ses* conditions, et
    un segment de 10 h sur une session commencée à 8 h n'avait jusqu'ici rien à
    quoi se rattacher.

    « Entamée » et pas « pleine » : une session de 8 h 15 à 10 h 40 a vécu
    l'heure de 10 h, et elle mérite sa ligne.
    """
    if duration_min is None or duration_min <= 0:
        return WINDOW_HOURS
    # Nombre d'heures entamées après celle du départ.
    extra = min(MAX_SESSION_HOURS, (duration_min - 1) // 60)
    return (*WINDOW_HOURS, *range(1, extra + 1))

SNAPSHOT_FIELDS = (
    "wave_height_m",
    "wave_direction_deg",
    "wave_period_s",
    "wave_peak_period_s",
    "swell_height_m",
    "swell_direction_deg",
    "swell_period_s",
    "swell_peak_period_s",
    "secondary_swell_height_m",
    "secondary_swell_direction_deg",
    "secondary_swell_period_s",
    "wind_speed_kt",
    "wind_gust_kt",
    "wind_direction_deg",
    "sea_level_m",
    "water_temperature_c",
)


def window_timestamps(
    started_at: datetime, duration_min: Optional[int] = None
) -> list[datetime]:
    """Les heures pleines de la fenêtre, en UTC.

    Open-Meteo est horaire : on cale sur l'heure pleine plutôt que d'interpoler
    une précision qui n'existe pas dans la donnée.
    """
    reference = started_at.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    return [
        reference + timedelta(hours=offset)
        for offset in window_offsets(duration_min)
    ]


def _entry(
    offset_h: int, ts: datetime, values: dict[str, Optional[float]]
) -> dict[str, Any]:
    entry: dict[str, Any] = {"offset_h": offset_h, "ts": ts.isoformat()}
    entry.update({field: values.get(field) for field in SNAPSHOT_FIELDS})
    return entry


def _trend(entries: list[dict[str, Any]], field: str) -> Optional[float]:
    """Variation sur la fenêtre (features 12 et 13 du registre).

    La tendance est un des signaux les plus forts : une houle de 1,5 m qui
    monte et une houle de 1,5 m qui s'écroule ne donnent pas la même session.
    """
    if len(entries) < 2:
        return None
    first = entries[0].get(field)
    last = entries[-1].get(field)
    if first is None or last is None:
        return None
    return round(last - first, 3)


def _trends(entries: list[dict[str, Any]]) -> dict[str, Optional[float]]:
    return {
        "wave_height_m": _trend(entries, "wave_height_m"),
        "wave_period_s": _trend(entries, "wave_period_s"),
        "wind_speed_kt": _trend(entries, "wind_speed_kt"),
        "sea_level_m": _trend(entries, "sea_level_m"),
    }


async def _forecast_panel(
    db: AsyncSession,
    spot_id: int,
    timestamps: list[datetime],
    offsets: tuple[int, ...],
) -> list[dict[str, Any]]:
    """Volet `forecast` : ce qui était annoncé **avant** la session.

    Le dernier run émis au plus tard au début de la session, et pas le dernier
    run tout court : une passe d'ingestion postérieure à la session est un
    constat déguisé, pas une prévision. Les mélanger reviendrait à donner au
    modèle une information qu'il n'avait pas au moment de prédire — le décalage
    train/serve de PROJET.md §7.1, dans sa version la plus discrète.
    """
    reference = max(timestamps)
    result = await db.execute(
        latest_forecasts_select(
            [spot_id], at_or_before=reference
        ).where(Forecast.ts.in_(timestamps))
    )

    by_ts: dict[datetime, dict[str, Optional[float]]] = {}
    for forecast in result.scalars().all():
        ts = forecast.ts if forecast.ts.tzinfo else forecast.ts.replace(tzinfo=UTC)
        by_ts[ts] = {field: getattr(forecast, field) for field in SNAPSHOT_FIELDS}

    return [
        _entry(offset, ts, by_ts[ts])
        for offset, ts in zip(offsets, timestamps)
        if ts in by_ts
    ]


def observed_panel_from_bundle(
    bundle: HourlyBundle,
    timestamps: list[datetime],
    offsets: Optional[tuple[int, ...]] = None,
    measured: Optional[dict[datetime, dict[str, Optional[float]]]] = None,
) -> list[dict[str, Any]]:
    """Volet `observed` : l'archive, **recouverte** par la bouée quand il y en a.

    Recouverte et non remplacée, et la nuance porte tout le sens : une bouée
    mesure la houle, et *rien d'autre*. Ni le vent, ni le niveau de la mer. Un
    volet reconstruit à partir de la seule bouée perdrait le vent — c'est-à-dire
    la moitié de ce qui décide d'une session.

    Chaque ligne dit d'où viennent ses valeurs de houle. Sans ça, l'historique
    mélangerait des mesures de bouée et des sorties de modèle sous la même
    étiquette « observé », et personne ne pourrait plus les départager — y
    compris le modèle du lot 6.
    """
    measured = measured or {}
    panel: list[dict[str, Any]] = []

    for offset, ts in zip(offsets or WINDOW_HOURS, timestamps):
        values = bundle.rows.get(ts)
        overlay = measured.get(ts)
        if values is None and overlay is None:
            continue

        entry = _entry(offset, ts, values or {})
        if overlay:
            entry.update(overlay)
            entry["wave_source"] = "buoy"
        else:
            entry["wave_source"] = "model"
        panel.append(entry)

    return panel


async def fetch_observed(
    spot: Spot,
    timestamps: list[datetime],
    client: Optional[OpenMeteoClient] = None,
) -> Optional[HourlyBundle]:
    """Interroge l'archive Open-Meteo sur les journées de la fenêtre.

    On récupère les journées entières et pas seulement les trois heures : le
    niveau de la mer n'a de sens que rapporté aux extrêmes du jour, et l'appel
    coûte exactement le même prix. Renvoie `None` en cas d'échec — jamais une
    exception, une session ne se perd pas pour un timeout.
    """
    start = min(timestamps).date()
    end = max(timestamps).date()

    async def _run(open_meteo: OpenMeteoClient) -> HourlyBundle:
        return await open_meteo.fetch_archive(spot.lat, spot.lon, start, end)

    try:
        if client is not None:
            return await _run(client)
        async with OpenMeteoClient() as open_meteo:
            return await _run(open_meteo)
    except Exception as exc:
        logger.error(
            "Backfill impossible pour %s entre %s et %s : %s",
            spot.slug,
            start,
            end,
            exc,
        )
        return None


async def _measured_window(
    db: AsyncSession,
    spot: Spot,
    timestamps: list[datetime],
) -> tuple[Optional[Any], dict[datetime, dict[str, Optional[float]]]]:
    """La bouée du spot et ses mesures sur la fenêtre — ou rien du tout.

    Import local : `services/observations` importe `services/geo` et les
    modèles, et le faire en tête créerait un cycle avec les modules qui
    importent déjà `backfill`.
    """
    from app.services.observations import station_by_code, station_window_values

    station = await station_by_code(db, spot.observation_station_code)
    if station is None:
        return None, {}

    measured = await station_window_values(db, station.code, timestamps)
    return (station if measured else None), measured


async def build_conditions_snapshot(
    db: AsyncSession,
    spot: Spot,
    started_at: datetime,
    client: Optional[OpenMeteoClient] = None,
    duration_min: Optional[int] = None,
) -> dict[str, Any]:
    """Construit le `conditions_snapshot` complet d'une session.

    `duration_min` étend la fenêtre à toute la durée de la session (décidé le
    13/09) : sans lui, un segment horaire noté à la troisième heure n'aurait
    aucune condition à laquelle s'apparier, et ne vaudrait rien pour le modèle.
    """
    offsets = window_offsets(duration_min)
    timestamps = window_timestamps(started_at, duration_min)

    forecast_panel = await _forecast_panel(db, spot.id, timestamps, offsets)
    bundle = await fetch_observed(spot, timestamps, client)

    # La bouée prime sur l'archive quand elle est assez proche et qu'elle a
    # mesuré cette fenêtre : c'est une mesure contre une sortie de modèle. Elle
    # n'est pas toujours là — une session à l'étranger, une bouée en panne, une
    # session d'avant le lot 1 bis — et c'est pour ça que l'archive reste le
    # socle plutôt que le repli.
    station, measured = await _measured_window(db, spot, timestamps)
    observed = observed_panel_from_bundle(
        bundle or HourlyBundle(), timestamps, offsets, measured
    )

    # La position dans la marée se lit sur les extrêmes du **jour**, pas sur
    # les heures de la fenêtre : trois points ne disent pas où sont la pleine
    # et la basse mer. D'où les journées entières demandées à l'archive.
    #
    # La référence est **l'heure du départ** (décalage 0), et non la dernière
    # heure de la fenêtre. Depuis que celle-ci s'étend à toute la durée, la
    # dernière heure est la sortie de l'eau : y rapporter la marée de la
    # session ferait basculer le « moment de la marée » de toutes les sessions
    # longues, et la feature 7 du registre changerait de sens sans prévenir.
    reference = timestamps[offsets.index(0)]
    tide = TideContext.from_levels(
        {ts: values.get("sea_level_m") for ts, values in bundle.rows.items()}
        if bundle
        else {}
    )

    snapshot: dict[str, Any] = {
        "window_hours": list(offsets),
        "reference_ts": reference.isoformat(),
        "source": "open-meteo",
        "model": settings.forecast_wave_model,
        "model_version": settings.forecast_model_version,
        "filled_at": datetime.now(UTC).isoformat(),
        "forecast": forecast_panel,
        "observed": observed,
        "trends": {
            "forecast": _trends(forecast_panel),
            "observed": _trends(observed),
        },
        "tide": {
            "range_m": tide.range_m(reference),
            "position": tide.position(reference),
            "trend_m_per_h": tide.trend_m_per_h(reference),
        },
        "spot": {
            "onshore_dir_deg": spot.onshore_dir_deg,
            "coast_bearing_deg": spot.coast_bearing_deg,
        },
    }

    if station is not None:
        # La source **et** la distance, parce que les deux s'affichent
        # (« bouée d'Anglet, 4 km ») et que les deux comptent : une mesure à
        # 25 km ne vaut pas une mesure à 4 km, et il faudra pouvoir le dire
        # sans rouvrir le catalogue des stations.
        snapshot["observed_station"] = {
            "code": station.code,
            "name": station.name,
            "distance_m": spot.observation_station_distance_m,
            "source": "candhis",
            "hours": sum(
                1 for entry in observed if entry.get("wave_source") == "buoy"
            ),
        }

    if not observed:
        # Une session sans volet `observed` reste exploitable, mais elle doit
        # se signaler : c'est elle qu'un rattrapage ultérieur devra reprendre.
        snapshot["observed_error"] = "archive indisponible à l'enregistrement"

    return snapshot
