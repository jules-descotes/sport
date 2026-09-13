"""Le coefficient de marée — calculé à Brest, valable partout.

Décidé le 13/09. Jusqu'ici l'app affichait le marnage du jour et **pas** le
coefficient, parce que le coefficient se définit par rapport à un port de
référence dont nous n'avions pas la donnée (cf. CLAUDE.md, lot 1 ter). C'est
cette donnée qu'on va chercher : un spot technique, non affiché, posé sur le
marégraphe de **Brest**, ingéré comme un spot maison.

**La définition, et pourquoi Brest.** Le coefficient est national par
construction : le SHOM le calcule au port de référence de Brest, et il vaut
pour toute la côte. Ce n'est pas une approximation qu'on s'autorise, c'est la
définition.

    C = (H_PM − N0) / U × 100

- `H_PM` — hauteur de la pleine mer, à Brest ;
- `N0` — niveau moyen. Open-Meteo sert déjà un niveau **relatif au niveau moyen
  de la mer**, donc `N0` devrait valoir zéro ; on le mesure quand même sur une
  fenêtre glissante de trente jours du **même modèle**, ce qui retire au
  passage le biais propre au modèle. C'est la seule façon d'éviter qu'un
  décalage de dix centimètres du modèle ne se transforme en trois points de
  coefficient permanents ;
- `U` — l'unité de hauteur de Brest, 3,05 m. Constante SHOM, jamais recalculée.

**Ce qui est affiché avec « ≈ ».** Trois cas : une fenêtre de moins de sept
jours pour établir `N0` (les premières semaines après la mise en service), une
valeur qui sort de la plage 20–120 du SHOM, ou un écart mesuré de plus de cinq
points contre l'annuaire (cf. `docs/COEFFICIENT-MAREE.md`). Un chiffre
approximatif annoncé comme exact est pire qu'un chiffre absent : celui-ci, on
sait qu'on ne peut pas s'y fier.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.forecast import Forecast
from app.models.spot import Spot
from app.services.forecast_reads import latest_run_clause

logger = logging.getLogger(__name__)

# Le marégraphe de Brest. Ce ne sont pas les coordonnées de la ville : c'est le
# point de mer le plus proche du port de référence, pour que la sélection de
# maille d'Open-Meteo (`cell_selection=sea`) tombe sur de l'eau.
BREST_LAT = 48.383
BREST_LON = -4.495

# Slug réservé. Le tiret bas en tête le range en fin d'index et le rend
# reconnaissable d'un coup d'œil dans la base.
REFERENCE_SLUG = "_reference-brest"
REFERENCE_NAME = "Brest — marégraphe de référence"

# Unité de hauteur de Brest. Constante SHOM : elle ne se recalcule pas, elle ne
# se règle pas, et elle n'a rien à faire en variable d'environnement.
UNIT_HEIGHT_M = 3.05

# Écrit sur les lignes de `forecasts` du spot de référence. Ce ne sont pas des
# vagues : les étiqueter MFWAM ferait mentir la colonne `model`, dont tout
# l'intérêt est de dire quel modèle a produit quelle ligne (PROJET.md §7.3).
REFERENCE_MODEL = "openmeteo_sea_level"

# Fenêtre glissante sur laquelle se mesure le niveau moyen du modèle.
MEAN_WINDOW_DAYS = 30
# En deçà, la moyenne est trop courte pour valoir comme datum : on retombe sur
# le zéro théorique d'Open-Meteo, et le coefficient part avec son « ≈ ».
MIN_WINDOW_HOURS = 7 * 24

# Bornes de l'échelle SHOM. Au-delà, ce n'est plus une marée, c'est une erreur.
MIN_COEFFICIENT = 20
MAX_COEFFICIENT = 120

# ── Ce que vaut notre calcul, mesuré ───────────────────────────────────────
#
# Écart maximal relevé contre l'annuaire SHOM, en points de coefficient.
# Campagne du 13/09/2026, dix pleines mers : biais moyen −1,7, écart maximal 6,
# l'erreur étant négative en vive-eau et positive en morte-eau — le modèle
# comprime le balancement d'environ 12 % (cf. `docs/COEFFICIENT-MAREE.md`).
#
# Six points, c'est au-dessus de la tolérance de cinq fixée le 13/09 : tous les
# coefficients partent donc avec leur « ≈ ». Ce n'est pas une fatalité, c'est
# une mesure — refaire la campagne et baisser cette constante fait disparaître
# le signe. Elle est ici, en clair, pour qu'on sache **pourquoi** il est là.
MEASURED_MAX_GAP = 6
CALIBRATION_TOLERANCE = 5
CALIBRATED = MEASURED_MAX_GAP <= CALIBRATION_TOLERANCE


@dataclass(frozen=True)
class TideMark:
    """Une pleine mer, et le coefficient qu'elle porte."""

    ts: datetime
    height_m: float
    value: int
    approximate: bool
    reason: Optional[str] = None


def coefficient_from_height(
    high_tide_m: float, mean_level_m: float
) -> tuple[int, bool]:
    """`C = (H_PM − N0) / U × 100`, arrondi. Renvoie aussi « hors échelle ».

    L'arrondi est à l'entier le plus proche, comme le publie le SHOM. La borne
    n'est pas un rattrapage : elle signale qu'on est sorti du domaine où la
    formule veut dire quelque chose, et c'est le second membre qui le dit.
    """
    raw = (high_tide_m - mean_level_m) / UNIT_HEIGHT_M * 100.0
    value = int(round(raw))
    clamped = max(MIN_COEFFICIENT, min(MAX_COEFFICIENT, value))
    return clamped, clamped != value


def high_tides(levels: Sequence[tuple[datetime, float]]) -> list[tuple[datetime, float]]:
    """Les pleines mers d'une série horaire : les maxima locaux, **interpolés**.

    Open-Meteo donne un niveau heure par heure, pas une table de marées. La
    pleine mer est donc le sommet d'une bosse, et on la lit sur trois heures
    consécutives. Le premier et le dernier point sont écartés : on ne sait pas
    ce qu'il y a juste avant ni juste après, et un bord n'est pas un sommet.

    L'égalité est tranchée d'un seul côté (`>` à gauche, `>=` à droite) : un
    palier de deux heures à l'étale ne doit compter que pour une pleine mer.

    **L'interpolation n'est pas un raffinement, c'est une correction de biais.**
    Une marée a une période de 12 h 25 : l'échantillon horaire tombe presque
    toujours à côté du sommet, jusqu'à une demi-heure avant ou après. Sur une
    sinusoïde, une demi-heure de décalage coûte 3 % de hauteur — soit **trois
    points de coefficient**, systématiquement en moins. Prendre la valeur
    échantillonnée telle quelle donnerait donc un coefficient toujours trop
    bas, et l'écart avec l'annuaire SHOM serait un biais et non du bruit.

    La parabole qui passe par les trois points rend le sommet et son heure. Le
    décalage est borné à une demi-heure de part et d'autre : au-delà, ce n'est
    plus le même sommet.
    """
    peaks: list[tuple[datetime, float]] = []
    for index in range(1, len(levels) - 1):
        previous = levels[index - 1][1]
        current = levels[index][1]
        following = levels[index + 1][1]
        if not (current > previous and current >= following):
            continue

        ts = levels[index][0]
        curvature = previous - 2.0 * current + following
        if curvature < 0:
            offset = max(-0.5, min(0.5, 0.5 * (previous - following) / curvature))
            crest = current - 0.25 * (previous - following) * offset
            # Le pas de la série n'est pas toujours d'une heure pile (trou de
            # données) : on mesure celui du voisinage plutôt que de le poser.
            step = (levels[index + 1][0] - ts).total_seconds()
            peaks.append((ts + timedelta(seconds=offset * step), crest))
        else:
            peaks.append(levels[index])
    return peaks


def marks_from_levels(
    levels: Sequence[tuple[datetime, float]],
    mean_level_m: float,
    *,
    window_hours: int,
) -> list[TideMark]:
    """Les coefficients d'une série de niveaux, une entrée par pleine mer."""
    short_window = window_hours < MIN_WINDOW_HOURS
    marks: list[TideMark] = []
    for ts, height in high_tides(levels):
        value, out_of_range = coefficient_from_height(height, mean_level_m)
        reason = (
            "fenêtre de référence trop courte"
            if short_window
            else "hors de l'échelle 20-120"
            if out_of_range
            else None
        )
        marks.append(
            TideMark(
                ts=ts,
                height_m=round(height, 3),
                value=value,
                approximate=short_window or out_of_range,
                reason=reason,
            )
        )
    return marks


def with_calibration(mark: TideMark) -> TideMark:
    """Ajoute au besoin la réserve qui vient de la campagne de mesure.

    La distinction compte : `marks_from_levels` ne sait rien du SHOM, elle ne
    juge que son propre calcul (fenêtre trop courte, valeur hors échelle). Ce
    que vaut ce calcul **face à la réalité** est une mesure extérieure, datée,
    consignée dans `docs/COEFFICIENT-MAREE.md` — et c'est ici qu'elle s'applique,
    au bord, sans contaminer la fonction qui calcule.

    Une réserve déjà posée l'emporte : « fenêtre de référence trop courte » est
    plus précis, et plus actionnable, que « écart mesuré ».
    """
    if CALIBRATED or mark.approximate:
        return mark
    return replace(
        mark,
        approximate=True,
        reason=f"écart mesuré de {MEASURED_MAX_GAP} points contre l'annuaire SHOM",
    )


def nearest_mark(marks: Sequence[TideMark], ts: datetime) -> Optional[TideMark]:
    """Le coefficient qui qualifie une heure : celui de la pleine mer la plus proche.

    Une journée porte deux pleines mers, et leurs coefficients diffèrent d'un ou
    deux points. Rattacher une heure à la plus proche est ce qui correspond à
    l'usage : « ce matin c'était 95 » désigne la marée du matin.
    """
    if not marks:
        return None
    return min(marks, key=lambda mark: abs((mark.ts - ts).total_seconds()))


# ── Lecture de la base ─────────────────────────────────────────────────────


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


async def reference_spot(db: AsyncSession) -> Optional[Spot]:
    """Le spot technique de Brest, s'il existe déjà."""
    result = await db.execute(select(Spot).where(Spot.slug == REFERENCE_SLUG))
    return result.scalar_one_or_none()


async def ensure_reference_spot(db: AsyncSession) -> Spot:
    """Crée le spot de Brest s'il manque. Idempotent, appelé à chaque passe.

    `is_reference` le protège du recalcul des niveaux : il reste `home` quoi
    que Jules mette en favori, parce qu'il n'est pas un favori — c'est une
    source. Et il est exclu de toutes les listes : personne ne va surfer au
    marégraphe de Brest.
    """
    spot = await reference_spot(db)
    if spot is not None:
        return spot

    spot = Spot(
        slug=REFERENCE_SLUG,
        name=REFERENCE_NAME,
        lat=BREST_LAT,
        lon=BREST_LON,
        country_code="FR",
        source="system",
        tier="home",
        is_active=True,
        is_reference=True,
    )
    db.add(spot)
    await db.commit()
    await db.refresh(spot)
    logger.info("Spot de référence créé : %s", REFERENCE_SLUG)
    return spot


async def _levels(
    db: AsyncSession, spot_id: int, start: datetime, end: datetime
) -> list[tuple[datetime, float]]:
    """Les niveaux du dernier run, triés, sans trou nul."""
    result = await db.execute(
        select(Forecast.ts, Forecast.sea_level_m)
        .where(Forecast.spot_id == spot_id)
        .where(Forecast.ts >= start)
        .where(Forecast.ts <= end)
        .where(Forecast.sea_level_m.is_not(None))
        .where(latest_run_clause())
        .order_by(Forecast.ts)
    )
    return [(_utc(ts), float(level)) for ts, level in result.all()]


async def mean_level(
    db: AsyncSession, spot_id: int, now: Optional[datetime] = None
) -> tuple[float, int]:
    """Niveau moyen du modèle sur trente jours glissants. Renvoie aussi la taille de la fenêtre.

    C'est le `N0` de la formule. Le mesurer plutôt que de le poser à zéro retire
    le biais propre au modèle : Open-Meteo annonce un niveau relatif au niveau
    moyen, mais un décalage de dix centimètres vaudrait trois points de
    coefficient pour toujours.
    """
    now = now or datetime.now(UTC)
    rows = await _levels(db, spot_id, now - timedelta(days=MEAN_WINDOW_DAYS), now)
    if not rows:
        return 0.0, 0
    return sum(level for _, level in rows) / len(rows), len(rows)


async def coefficients(
    db: AsyncSession,
    start: date,
    days: int,
    *,
    now: Optional[datetime] = None,
) -> list[TideMark]:
    """Les coefficients des pleines mers sur une fenêtre de jours.

    Rend une liste vide tant que le spot de référence n'a rien en base — les
    premières heures après un déploiement, ou si Open-Meteo est indisponible.
    Une liste vide est une information exploitable par l'écran ; un zéro n'en
    est pas une.
    """
    spot = await reference_spot(db)
    if spot is None:
        return []

    now = now or datetime.now(UTC)
    datum, window_hours = await mean_level(db, spot.id, now)

    # Une heure de marge de part et d'autre : une pleine mer à 00 h 30 a besoin
    # de l'heure d'avant pour être reconnue comme un sommet.
    window_start = datetime.combine(start, datetime.min.time(), tzinfo=UTC) - timedelta(
        hours=1
    )
    window_end = window_start + timedelta(days=days, hours=2)
    levels = await _levels(db, spot.id, window_start, window_end)

    marks = marks_from_levels(levels, datum, window_hours=window_hours)
    # On a élargi la fenêtre pour détecter les sommets de bord ; on la resserre
    # pour ne rendre que les jours demandés.
    first = datetime.combine(start, datetime.min.time(), tzinfo=UTC)
    last = first + timedelta(days=days)
    return [
        with_calibration(mark) for mark in marks if first <= mark.ts < last
    ]
