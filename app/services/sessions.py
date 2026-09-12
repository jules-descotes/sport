"""Le chemin des quinze secondes, et ce qui le tient.

Ce module existe pour une raison chiffrée : **~240 sessions par an**. À
90 secondes de formulaire pièce, c'est six heures de saisie annuelles et un
abandon au bout de trois mois ; à 15 secondes, l'historique existe. Le chemin
rapide n'est donc pas un confort, c'est ce qui décide si le modèle aura des
données (cf. PROJET.md §7.2).

Trois décisions y sont écrites, et elles se tiennent :

1. **Le spot est deviné, pas demandé.** Le plus proche du catalogue dans un
   rayon de 2 km ; hors zone, le favori du profil. Se tromper de spot se
   rattrape d'un tap sur l'écran de notation ; demander le spot à la sortie de
   l'eau coûte un tap à chaque session, 240 fois par an.
2. **Le début est estimé, pas saisi.** Fin − 90 min, et `start_estimated` le
   dit. Une estimation ne doit jamais pouvoir se lire comme une mesure.
3. **L'appel est idempotent sur dix minutes.** Un raccourci iOS se déclenche
   deux fois pour un doigt mouillé ; une session en double pollue autant
   l'historique qu'une session manquante.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SessionStatus
from app.models.profile import Profile
from app.models.spot import Spot
from app.models.surf_session import SurfSession
from app.services.backfill import build_conditions_snapshot
from app.services.geo import bounding_box, haversine_m

logger = logging.getLogger(__name__)

# Rayon de reconnaissance du spot. Deux kilomètres : à cette distance sur la
# côte landaise on a déjà changé de plage, et au-delà la géoloc d'un téléphone
# dans une combinaison mouillée n'est plus une information fiable.
QUICK_RADIUS_KM = 2.0

# Durée par défaut d'une session. Une heure trente est la session type ; elle
# se corrige aux molettes de quinze minutes sur l'écran de notation.
QUICK_DEFAULT_DURATION_MIN = 90

# Fenêtre d'idempotence. Dix minutes : c'est plus long qu'un double tap et
# beaucoup plus court que l'intervalle entre deux vraies sessions.
IDEMPOTENCY_WINDOW_MIN = 10


async def nearest_spot(
    db: AsyncSession, lat: float, lon: float, radius_km: float = QUICK_RADIUS_KM
) -> Optional[tuple[Spot, float]]:
    """Le spot du catalogue le plus proche d'un point, et sa distance en km.

    Boîte englobante en SQL, distance exacte en Python — comme
    `/spots/nearby` : sans le premier tri, c'est un balayage du catalogue
    mondial à chaque sortie de l'eau.
    """
    min_lat, max_lat, min_lon, max_lon = bounding_box(lat, lon, radius_km)
    result = await db.execute(
        select(Spot)
        .where(Spot.lat.between(min_lat, max_lat))
        .where(Spot.lon.between(min_lon, max_lon))
    )

    radius_m = radius_km * 1000.0
    best: Optional[tuple[Spot, float]] = None
    for spot in result.scalars().all():
        distance_m = haversine_m(lat, lon, spot.lat, spot.lon)
        if distance_m > radius_m:
            continue
        if best is None or distance_m < best[1]:
            best = (spot, distance_m)

    if best is None:
        return None
    return best[0], round(best[1] / 1000.0, 3)


async def home_spot(db: AsyncSession, user_id: int) -> Optional[Spot]:
    """Le spot favori du profil — le repli quand la géoloc ne dit rien."""
    result = await db.execute(
        select(Spot)
        .join(Profile, Profile.home_spot_id == Spot.id)
        .where(Profile.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def resolve_quick_spot(
    db: AsyncSession,
    user_id: int,
    lat: Optional[float],
    lon: Optional[float],
) -> tuple[Optional[Spot], str, Optional[float]]:
    """Quel spot pour cette sortie de l'eau : le plus proche, sinon le favori.

    Renvoie `(spot, source, distance_km)`. `source` vaut `nearest` ou `home`,
    et il remonte jusqu'à l'écran : un spot deviné doit se signaler comme tel,
    sinon on ne pense jamais à le corriger.
    """
    if lat is not None and lon is not None:
        found = await nearest_spot(db, lat, lon)
        if found is not None:
            spot, distance_km = found
            return spot, "nearest", distance_km

    # Hors catalogue — un spot de voyage, ou une plage qu'OSM ignore. Le favori
    # est un repli honnête : il sera faux, et l'écran de notation le dira.
    return await home_spot(db, user_id), "home", None


async def find_duplicate(
    db: AsyncSession,
    user_id: int,
    started_at: datetime,
    client_uuid: Optional[str] = None,
    window_min: int = IDEMPOTENCY_WINDOW_MIN,
) -> Optional[SurfSession]:
    """La session déjà enregistrée que ce nouvel appel voudrait recréer.

    Deux garde-fous, dans cet ordre :

    - `client_uuid`, quand le client en fournit un — c'est l'idempotence
      exacte, celle de la file hors ligne qui rejoue ses envois ;
    - à défaut, un début à moins de dix minutes — c'est l'idempotence
      approchée, celle du raccourci iOS déclenché deux fois, qui n'a aucun
      moyen de se souvenir de son appel précédent.
    """
    if client_uuid:
        result = await db.execute(
            select(SurfSession)
            .where(SurfSession.user_id == user_id)
            .where(SurfSession.client_uuid == client_uuid)
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing

    window = timedelta(minutes=window_min)
    result = await db.execute(
        select(SurfSession)
        .where(SurfSession.user_id == user_id)
        .where(SurfSession.started_at >= started_at - window)
        .where(SurfSession.started_at <= started_at + window)
        .order_by(SurfSession.started_at.desc())
        .limit(1)
    )
    return result.scalars().first()


def quick_start_time(ended_at: datetime, duration_min: int) -> datetime:
    """Début estimé d'une session dont on ne connaît que la fin."""
    return ended_at.astimezone(UTC) - timedelta(minutes=duration_min)


async def create_quick_session(
    db: AsyncSession,
    user_id: int,
    spot: Spot,
    started_at: datetime,
    duration_min: int,
    discipline: str,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    client_uuid: Optional[str] = None,
) -> SurfSession:
    """Crée la session « à noter » et fige ses conditions.

    Le figeage est le seul geste irrattrapable du lot (cf. CLAUDE.md, règle 7)
    et il a lieu **ici**, à la sortie de l'eau, pas à la notation : le volet
    `forecast` ne doit retenir que les runs émis avant le début de la session,
    et attendre le soir pour le construire n'y changerait rien — mais un
    échec silencieux, si.

    Un échec de backfill n'empêche jamais l'enregistrement : perdre une session
    pour un timeout serait le comble, vu que le risque du projet est la
    friction de saisie.
    """
    session = SurfSession(
        user_id=user_id,
        spot_id=spot.id,
        started_at=started_at,
        duration_min=duration_min,
        discipline=discipline,
        status=SessionStatus.TO_RATE.value,
        lat=lat,
        lon=lon,
        client_uuid=client_uuid,
        start_estimated=True,
    )
    session.conditions_snapshot = await build_conditions_snapshot(
        db, spot, started_at
    )

    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


def needs_refill(session: SurfSession) -> bool:
    """Le volet `observed` est-il vide alors qu'il ne devrait pas l'être ?

    Cas courant et prévu : la session est enregistrée sur le parking, l'archive
    Open-Meteo ne répond pas, le snapshot part avec `observed_error`. On
    complète à la notation, qui se fait au sec — c'est le rattrapage naturel,
    et il ne coûte rien puisqu'on est déjà en train d'écrire la ligne.
    """
    snapshot = session.conditions_snapshot
    if not snapshot:
        return True
    return not snapshot.get("observed")


# ── Historique des snapshots ───────────────────────────────────────────────
#
# Le `conditions_snapshot` est la seule donnée irrattrapable du projet
# (cf. CLAUDE.md, règle 7). Depuis que les sessions se modifient depuis le
# navigateur (13/09), une correction de bonne foi — « en fait c'était Les
# Estagnots, pas La Gravière » — refait le figeage. L'ancien est empilé, jamais
# perdu : on ne sait pas encore lequel des deux dira la vérité au modèle, et on
# le saura moins encore dans six mois.

# Au-delà, on ne garde que les plus récents : une session corrigée vingt fois
# est une session qu'on cherche encore, pas une donnée à archiver.
SNAPSHOT_HISTORY_MAX = 10

# Durée de rétention de la corbeille, en jours.
TRASH_RETENTION_DAYS = 30


def archive_snapshot(
    session: SurfSession,
    reason: str,
    *,
    spot_id: int,
    started_at: datetime,
) -> None:
    """Empile le `conditions_snapshot` courant avant qu'il soit remplacé.

    `spot_id` et `started_at` sont ceux **pour lesquels le snapshot avait été
    figé**, pas ceux de la session après correction — l'appelant a déjà écrit
    les nouvelles valeurs sur l'objet quand il arrive ici, et archiver
    celles-ci étiquetterait l'ancienne fenêtre avec le nouveau spot. C'est
    exactement l'erreur que l'historique existe pour empêcher.

    `reason` dit **pourquoi** il a été refait — « spot modifié », « début
    modifié » — parce qu'un empilement sans motif est illisible au moment où on
    en a besoin, c'est-à-dire longtemps après.
    """
    current = session.conditions_snapshot
    if not current:
        return

    history = list(session.snapshot_history or [])
    history.append(
        {
            "replaced_at": datetime.now(UTC).isoformat(),
            "reason": reason,
            "spot_id": spot_id,
            "started_at": (
                started_at if started_at.tzinfo else started_at.replace(tzinfo=UTC)
            ).isoformat(),
            "snapshot": current,
        }
    )
    # Réassignation et pas `.append()` : SQLAlchemy ne voit pas la mutation
    # d'une liste JSON en place, et la colonne partirait inchangée en base.
    session.snapshot_history = history[-SNAPSHOT_HISTORY_MAX:]


def purge_deadline(now: Optional[datetime] = None) -> datetime:
    """Au-delà de cette date, une session en corbeille est purgeable."""
    return (now or datetime.now(UTC)) - timedelta(days=TRASH_RETENTION_DAYS)


async def purge_trashed_sessions(
    db: AsyncSession, now: Optional[datetime] = None
) -> int:
    """Supprime définitivement les sessions en corbeille depuis plus de 30 jours.

    Appelée par le job planifié, jamais par une requête de lecture : une
    lecture qui écrit est une surprise, et celle-ci détruirait des lignes.
    """
    deadline = purge_deadline(now)
    result = await db.execute(
        select(SurfSession)
        .where(SurfSession.deleted_at.is_not(None))
        .where(SurfSession.deleted_at < deadline)
    )
    doomed = list(result.scalars().all())
    for session in doomed:
        await db.delete(session)
    if doomed:
        await db.commit()
        logger.info("Corbeille : %d session(s) purgée(s)", len(doomed))
    return len(doomed)
