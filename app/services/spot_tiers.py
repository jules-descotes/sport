"""Calcul des niveaux d'ingestion.

`spots.tier` répond à une seule question : qui interroge-t-on ? Il est
recalculé à chaque connexion, à chaque changement de favoris et à chaque
changement de position — jamais par le script d'import, qui n'a aucune idée de
ce que Jules a mis en favori.

Depuis le lot 1 ter, le niveau `home` part du **spot favori du profil**
(`profiles.home_spot_id`), auquel s'ajoutent les favoris secondaires. C'est le
seul niveau que le job planifié interroge. `potential` reste un simple
étiquetage — plus aucun chemin ne l'ingère en masse : un spot du rayon n'est
interrogé que lorsqu'on ouvre sa fiche sur l'écran Mer.

Le niveau vit sur `spots` et non sur une table par utilisateur : il pilote un
job planifié qui, lui, n'a pas d'utilisateur. Le jour où l'app s'ouvre aux
potes (cf. PROJET.md §11), `tier` devient l'union des niveaux de tous les
utilisateurs — la logique de cette fonction ne change pas, seule la boucle
d'entrée s'élargit.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SpotTier
from app.models.profile import Profile
from app.models.spot import Spot, SpotPreference
from app.services.geo import bounding_box, haversine_m

logger = logging.getLogger(__name__)

# Plafond des favoris. Vingt spots × 3 appels × 8 passes par jour = 480 appels,
# très loin des 10 000 du quota gratuit — mais la limite protège surtout de la
# tentation de tout mettre en favori et de ne plus rien décider.
HOME_MAX = 20

# Un déplacement ouvre des spots « potentiels » autour de la position courante,
# sans toucher au domicile ni au rayon d'affichage.
POSITION_RADIUS_KM = 50.0

# En deçà, une nouvelle position ne justifie pas de recalculer les niveaux :
# la géoloc d'un téléphone bouge de quelques dizaines de mètres au repos.
POSITION_MOVE_THRESHOLD_KM = 5.0


async def _spot_ids_within(
    db: AsyncSession, lat: float, lon: float, radius_km: float
) -> set[int]:
    min_lat, max_lat, min_lon, max_lon = bounding_box(lat, lon, radius_km)
    result = await db.execute(
        select(Spot.id, Spot.lat, Spot.lon).where(
            Spot.lat.between(min_lat, max_lat),
            Spot.lon.between(min_lon, max_lon),
        )
    )
    radius_m = radius_km * 1000.0
    return {
        spot_id
        for spot_id, spot_lat, spot_lon in result.all()
        if haversine_m(lat, lon, spot_lat, spot_lon) <= radius_m
    }


async def home_spot_id(db: AsyncSession, user_id: int) -> Optional[int]:
    """Spot favori du profil — la seule prévision affichée par défaut."""
    result = await db.execute(
        select(Profile.home_spot_id).where(Profile.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_or_create_preferences(
    db: AsyncSession, user_id: int
) -> SpotPreference:
    result = await db.execute(
        select(SpotPreference).where(SpotPreference.user_id == user_id)
    )
    preferences = result.scalar_one_or_none()
    if preferences is None:
        preferences = SpotPreference(user_id=user_id)
        db.add(preferences)
        await db.commit()
        await db.refresh(preferences)
    return preferences


async def recompute_tiers(
    db: AsyncSession, preferences: SpotPreference
) -> dict[str, int]:
    """Réaffecte `tier` et `is_active` sur tout le catalogue.

    Trois `UPDATE` en masse plutôt qu'une boucle : le catalogue OSM mondial
    compte des dizaines de milliers de lignes, et ceci tourne à chaque
    connexion.
    """
    favorites = [int(spot_id) for spot_id in (preferences.favorite_spot_ids or [])]
    hidden = {int(spot_id) for spot_id in (preferences.hidden_spot_ids or [])}

    # Le favori du profil ouvre la liste, et il y est même s'il n'a jamais été
    # coché comme favori secondaire : c'est lui qu'on regarde tous les matins,
    # c'est lui qui doit être ingéré même app fermée.
    favorite = await home_spot_id(db, preferences.user_id)
    if favorite is not None and favorite not in favorites:
        favorites.insert(0, favorite)

    home_ids = [spot_id for spot_id in favorites if spot_id not in hidden][:HOME_MAX]

    # Les spots de référence (le marégraphe de Brest) sont `home` de droit et
    # **hors plafond** : ce ne sont pas des favoris, ce sont des sources. Sans
    # cette ligne, la première connexion les renverrait au catalogue,
    # l'ingestion s'arrêterait, et le coefficient de marée disparaîtrait de
    # l'app sans que rien ne le dise.
    references = await db.execute(select(Spot.id).where(Spot.is_reference.is_(True)))
    home_ids += [spot_id for spot_id in references.scalars().all() if spot_id not in home_ids]

    potential_ids: set[int] = set()
    if preferences.home_lat is not None and preferences.home_lon is not None:
        potential_ids |= await _spot_ids_within(
            db, preferences.home_lat, preferences.home_lon, preferences.radius_km
        )
    if preferences.last_lat is not None and preferences.last_lon is not None:
        potential_ids |= await _spot_ids_within(
            db, preferences.last_lat, preferences.last_lon, POSITION_RADIUS_KM
        )

    # Un spot masqué reste masqué, même s'il est sous le nez : c'est le seul
    # moyen de faire taire un spot qu'on ne surfe jamais.
    potential_ids -= hidden
    potential_ids -= set(home_ids)

    active_ids = set(home_ids) | potential_ids

    # 1. Tout ce qui était actif et ne l'est plus retombe au catalogue.
    reset = await db.execute(
        update(Spot)
        .where(Spot.tier != SpotTier.CATALOG.value)
        .where(Spot.id.notin_(active_ids) if active_ids else Spot.id.isnot(None))
        .values(tier=SpotTier.CATALOG.value, is_active=False)
    )

    if potential_ids:
        await db.execute(
            update(Spot)
            .where(Spot.id.in_(potential_ids))
            .values(tier=SpotTier.POTENTIAL.value, is_active=True)
        )

    if home_ids:
        await db.execute(
            update(Spot)
            .where(Spot.id.in_(home_ids))
            .values(tier=SpotTier.HOME.value, is_active=True)
        )

    await db.commit()

    counts = {
        "home": len(home_ids),
        "potential": len(potential_ids),
        "demoted": reset.rowcount or 0,
    }
    logger.info(
        "Niveaux recalculés : %d maison, %d potentiels", counts["home"], counts["potential"]
    )
    return counts


async def record_position(
    db: AsyncSession,
    preferences: SpotPreference,
    lat: float,
    lon: float,
    now: Optional[datetime] = None,
) -> bool:
    """Enregistre la position courante. Renvoie `True` si les niveaux ont bougé.

    Le seuil de cinq kilomètres évite de recalculer le catalogue à chaque
    rafraîchissement de l'écran d'accueil : la géoloc d'un téléphone posé sur
    une table dérive de quelques dizaines de mètres.
    """
    moved = (
        preferences.last_lat is None
        or preferences.last_lon is None
        or haversine_m(preferences.last_lat, preferences.last_lon, lat, lon)
        > POSITION_MOVE_THRESHOLD_KM * 1000.0
    )

    preferences.last_lat = lat
    preferences.last_lon = lon
    preferences.last_position_at = now or datetime.now(UTC)
    await db.commit()

    if moved:
        await recompute_tiers(db, preferences)
    return moved
