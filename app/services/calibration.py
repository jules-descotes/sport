"""Calibration prévision ↔ mesure (§7.3) — appariement et lecture.

Ce que ce module fait, et ce qu'il ne fait **pas**.

Il fait : apparier chaque heure mesurée par la bouée avec ce que *chaque* run
de prévision disponible annonçait pour cette heure, et rendre le biais et
l'erreur absolue moyenne par tranche de délai.

Il ne fait pas : corriger quoi que ce soit. Le score de cold start ne bouge
pas d'un dixième (décision du 15/09). On mesure d'abord, longtemps ; on
corrigera avec des mois de données, pas avec trois jours. Un modèle recalé sur
deux semaines d'un automne calme serait faux tout l'hiver, et il serait faux
sans qu'on puisse le voir — c'est exactement le genre de correction qui
s'installe et qu'on ne retrouve plus.

**Le biais est signé, et son signe se lit dans un sens précis** :
`observé − prévu`. Positif = le modèle **sous-estime**. C'est la phrase qu'on
veut pouvoir écrire sans se tromper de sens un matin à six heures : « à 24 h,
le modèle sous-estime la hauteur de 8 % en moyenne ».
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.calibration import ForecastVsObserved
from app.models.forecast import Forecast, Observation
from app.models.spot import Spot

logger = logging.getLogger(__name__)

# Les tranches de délai, en heures. Bornes hautes exclues sauf la dernière.
#
# Elles ne sont pas régulières, et c'est le sujet : l'erreur d'un modèle de
# vagues ne croît pas linéairement avec le délai. 0–6 h, c'est « maintenant » ;
# 6–24 h, c'est « ce soir » ; 24–48 h, c'est « demain » ; au-delà, c'est le
# week-end. Découper en tranches égales mélangerait « ce soir » et « demain »,
# qui ne se décident pas de la même façon.
LEAD_BUCKETS: tuple[tuple[str, float, Optional[float]], ...] = (
    ("0-6h", 0.0, 6.0),
    ("6-24h", 6.0, 24.0),
    ("24-48h", 24.0, 48.0),
    ("48h+", 48.0, None),
)

# Fenêtre glissante de lecture.
DEFAULT_WINDOW_DAYS = 30

# En dessous, on n'affiche pas de chiffre. Cinq paires sur une tranche, ce
# n'est pas un biais, c'est une anecdote — et une anecdote affichée avec une
# décimale se lit comme une mesure.
MIN_PAIRS = 12

_CHUNK_SIZE = 500


def bucket_for(lead_hours: float) -> Optional[str]:
    for label, low, high in LEAD_BUCKETS:
        if lead_hours < low:
            continue
        if high is None or lead_hours < high:
            return label
    return None


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


# --- Appariement ----------------------------------------------------------


async def build_pairs(
    db: AsyncSession,
    spot: Spot,
    station_code: str,
    start: datetime,
    end: datetime,
    distance_m: Optional[float] = None,
) -> int:
    """Apparie les heures mesurées avec **tous** les runs qui les annonçaient.

    Les mesures sont demi-horaires, les prévisions horaires : chaque mesure est
    rapportée à **son heure pleine**, et quand deux mesures tombent dans la même
    heure on garde la plus proche du top. Interpoler donnerait une précision qui
    n'existe pas dans la prévision d'en face.
    """
    observations = (
        (
            await db.execute(
                select(Observation)
                .where(Observation.station_id == station_code)
                .where(Observation.ts >= start)
                .where(Observation.ts <= end)
                .order_by(Observation.ts)
            )
        )
        .scalars()
        .all()
    )
    if not observations:
        return 0

    # Heure pleine -> la mesure la plus proche du top de cette heure.
    by_hour: dict[datetime, tuple[float, Observation]] = {}
    for observation in observations:
        ts = _aware(observation.ts)
        hour = ts.replace(minute=0, second=0, microsecond=0)
        gap = abs((ts - hour).total_seconds())
        current = by_hour.get(hour)
        if current is None or gap < current[0]:
            by_hour[hour] = (gap, observation)

    if not by_hour:
        return 0

    hours = sorted(by_hour)
    # Un intervalle, pas un `IN` : une tranche de backfill de douze mois
    # contient ~17 000 heures mesurées, et la liste partirait en clause `IN`
    # de dix-sept mille éléments. L'appariement se fait ensuite en Python, sur
    # le dictionnaire `by_hour` — qui est de toute façon déjà en mémoire.
    forecasts = (
        (
            await db.execute(
                select(Forecast)
                .where(Forecast.spot_id == spot.id)
                .where(Forecast.ts >= hours[0])
                .where(Forecast.ts <= hours[-1])
            )
        )
        .scalars()
        .all()
    )
    if not forecasts:
        return 0

    payload: list[dict[str, Any]] = []
    for forecast in forecasts:
        ts = _aware(forecast.ts)
        run_ts = _aware(forecast.run_ts)
        entry = by_hour.get(ts)
        if entry is None:
            continue

        lead = (ts - run_ts).total_seconds() / 3600.0
        if lead < 0:
            # Un run postérieur à l'heure cible n'est pas une prévision mais un
            # constat déguisé. Le compter flatterait le modèle exactement là où
            # on cherche à le mesurer (cf. PROJET.md §7.1).
            continue

        observation = entry[1]
        # Une paire sans aucune des deux grandeurs n'apprend rien.
        if observation.hm0_m is None and observation.peak_period_s is None:
            continue

        payload.append(
            {
                "station_id": station_code,
                "spot_id": spot.id,
                "ts": ts,
                "run_ts": run_ts,
                "lead_hours": round(lead, 2),
                "forecast_hm0_m": forecast.wave_height_m,
                "observed_hm0_m": observation.hm0_m,
                # La période de pic des deux côtés : c'est celle que la bouée
                # publie le plus souvent, et celle qu'on lit à l'écran.
                "forecast_period_s": (
                    forecast.wave_peak_period_s or forecast.wave_period_s
                ),
                "observed_period_s": (
                    observation.peak_period_s or observation.mean_period_s
                ),
                "model": forecast.model,
                "model_version": forecast.model_version,
                "distance_m": distance_m,
            }
        )

    if not payload:
        return 0

    dialect = db.get_bind().dialect.name
    insert = pg_insert if dialect == "postgresql" else sqlite_insert
    for chunk_start in range(0, len(payload), _CHUNK_SIZE):
        chunk = payload[chunk_start : chunk_start + _CHUNK_SIZE]
        statement = insert(ForecastVsObserved).values(chunk).on_conflict_do_nothing(
            index_elements=["station_id", "ts", "run_ts"]
        )
        await db.execute(statement)

    await db.commit()
    return len(payload)


# --- Lecture --------------------------------------------------------------


@dataclass
class BucketStats:
    """Le biais et l'erreur d'une tranche de délai, pour une grandeur."""

    bucket: str
    pairs: int
    bias: Optional[float] = None
    mae: Optional[float] = None
    bias_pct: Optional[float] = None
    mean_observed: Optional[float] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "bucket": self.bucket,
            "pairs": self.pairs,
            "bias": self.bias,
            "mae": self.mae,
            "bias_pct": self.bias_pct,
            "mean_observed": self.mean_observed,
        }


def _stats(
    bucket: str, pairs: Sequence[tuple[float, float]]
) -> BucketStats:
    """`pairs` = [(prévu, observé), …]. Biais = observé − prévu."""
    if len(pairs) < MIN_PAIRS:
        # On rend le compte quand même : « pas encore assez » est une
        # information, et c'est elle qui s'affiche au début.
        return BucketStats(bucket=bucket, pairs=len(pairs))

    errors = [observed - forecast for forecast, observed in pairs]
    bias = sum(errors) / len(errors)
    mae = sum(abs(error) for error in errors) / len(errors)
    mean_observed = sum(observed for _, observed in pairs) / len(pairs)

    # Le pourcentage est rapporté à la moyenne **observée**, pas à la prévue :
    # c'est la mer qu'on prend comme référence, pas le modèle qu'on juge.
    bias_pct = (
        round(100.0 * bias / mean_observed, 1) if mean_observed > 0.01 else None
    )

    return BucketStats(
        bucket=bucket,
        pairs=len(pairs),
        bias=round(bias, 3),
        mae=round(mae, 3),
        bias_pct=bias_pct,
        mean_observed=round(mean_observed, 2),
    )


@dataclass
class Calibration:
    station_id: Optional[str]
    window_days: int
    pairs: int
    distance_m: Optional[float]
    hm0: list[BucketStats]
    period: list[BucketStats]

    def as_dict(self) -> dict[str, Any]:
        return {
            "station_id": self.station_id,
            "window_days": self.window_days,
            "pairs": self.pairs,
            "distance_m": self.distance_m,
            "hm0": [b.as_dict() for b in self.hm0],
            "period": [b.as_dict() for b in self.period],
        }


async def calibration(
    db: AsyncSession,
    station_code: Optional[str] = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
    now: Optional[datetime] = None,
) -> Calibration:
    """Biais et erreur absolue moyenne par tranche de délai, sur 30 jours.

    Glissants, et c'est voulu : un biais de modèle de vagues change avec la
    saison — une houle d'hiver longue et une mer de vent d'été ne se prévoient
    pas avec la même erreur. Une moyenne depuis le début de l'historique
    finirait par ne plus décrire aucune des deux.
    """
    now = now or datetime.now(UTC)
    since = now - timedelta(days=window_days)

    query = select(ForecastVsObserved).where(ForecastVsObserved.ts >= since)
    if station_code:
        query = query.where(ForecastVsObserved.station_id == station_code)
    rows = (await db.execute(query)).scalars().all()

    hm0_by_bucket: dict[str, list[tuple[float, float]]] = {
        label: [] for label, _, _ in LEAD_BUCKETS
    }
    period_by_bucket: dict[str, list[tuple[float, float]]] = {
        label: [] for label, _, _ in LEAD_BUCKETS
    }

    distance: Optional[float] = None
    for row in rows:
        bucket = bucket_for(row.lead_hours)
        if bucket is None:
            continue
        if distance is None and row.distance_m is not None:
            distance = row.distance_m
        if row.forecast_hm0_m is not None and row.observed_hm0_m is not None:
            hm0_by_bucket[bucket].append((row.forecast_hm0_m, row.observed_hm0_m))
        if row.forecast_period_s is not None and row.observed_period_s is not None:
            period_by_bucket[bucket].append(
                (row.forecast_period_s, row.observed_period_s)
            )

    return Calibration(
        station_id=station_code,
        window_days=window_days,
        pairs=len(rows),
        distance_m=distance,
        hm0=[_stats(label, hm0_by_bucket[label]) for label, _, _ in LEAD_BUCKETS],
        period=[
            _stats(label, period_by_bucket[label]) for label, _, _ in LEAD_BUCKETS
        ],
    )


def sentence(stats: BucketStats, quantity: str = "la hauteur") -> Optional[str]:
    """Une phrase en français, ou rien.

    « Rien » quand il n'y a pas assez de paires : afficher « le modèle
    sous-estime de 0,3 % » sur huit mesures ferait croire à un réglage fin là
    où il n'y a que du bruit.
    """
    if stats.bias is None or stats.bias_pct is None:
        return None
    if abs(stats.bias_pct) < 3:
        return f"à {stats.bucket}, le modèle tombe juste sur {quantity}"
    verb = "sous-estime" if stats.bias > 0 else "surestime"
    return (
        f"à {stats.bucket}, le modèle {verb} {quantity} "
        f"de {abs(stats.bias_pct):.0f} % en moyenne"
    )
