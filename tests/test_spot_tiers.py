"""Niveaux d'ingestion — qui interroge-t-on, et qui jamais.

Le catalogue est mondial, l'ingestion ne l'est pas. Ces tests vérifient la
seule règle qui compte : `catalog` n'est jamais interrogé, quoi qu'il arrive.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.enums import SpotTier
from app.models.spot import Spot
from app.services.spot_tiers import (
    HOME_MAX,
    get_or_create_preferences,
    recompute_tiers,
    record_position,
)
from tests.conftest import HOSSEGOR_LAT, HOSSEGOR_LON


async def tiers(db_session) -> dict[str, str]:
    spots = (await db_session.execute(select(Spot))).scalars().all()
    return {spot.slug: spot.tier for spot in spots}


async def test_spot_in_radius_becomes_potential(
    db_session, preferences, make_spot
) -> None:
    near = await make_spot(
        name="Proche", slug="proche", lat=HOSSEGOR_LAT + 0.05, lon=HOSSEGOR_LON
    )

    await recompute_tiers(db_session, preferences)

    await db_session.refresh(near)
    assert near.tier == SpotTier.POTENTIAL.value
    assert near.is_active is True


async def test_spot_outside_radius_stays_catalog(
    db_session, preferences, make_spot
) -> None:
    """Le reste du catalogue mondial : visible, jamais ingéré."""
    far = await make_spot(name="Nazaré", slug="nazare", lat=39.60, lon=-9.07)

    await recompute_tiers(db_session, preferences)

    await db_session.refresh(far)
    assert far.tier == SpotTier.CATALOG.value
    assert far.is_active is False


async def test_favorite_becomes_home(db_session, preferences, make_spot) -> None:
    """Les favoris sont le seul niveau ingéré en planifié."""
    far_favorite = await make_spot(name="Nazaré", slug="nazare", lat=39.60, lon=-9.07)
    preferences.favorite_spot_ids = [far_favorite.id]
    await db_session.commit()

    await recompute_tiers(db_session, preferences)

    await db_session.refresh(far_favorite)
    # Un favori est ingéré même hors rayon : c'est tout l'intérêt du favori.
    assert far_favorite.tier == SpotTier.HOME.value


async def test_home_wins_over_potential(db_session, preferences, make_spot) -> None:
    near = await make_spot(name="Proche", slug="proche", lat=HOSSEGOR_LAT + 0.01)
    preferences.favorite_spot_ids = [near.id]
    await db_session.commit()

    await recompute_tiers(db_session, preferences)

    await db_session.refresh(near)
    assert near.tier == SpotTier.HOME.value


async def test_hidden_spot_falls_back_to_catalog(
    db_session, preferences, make_spot
) -> None:
    """Masquer un spot est le seul moyen de faire taire un spot qu'on ne surfe pas."""
    near = await make_spot(name="Proche", slug="proche", lat=HOSSEGOR_LAT + 0.01)
    preferences.hidden_spot_ids = [near.id]
    await db_session.commit()

    await recompute_tiers(db_session, preferences)

    await db_session.refresh(near)
    assert near.tier == SpotTier.CATALOG.value


async def test_favorites_are_capped_at_twenty(
    db_session, preferences, make_spot
) -> None:
    """Au-delà, ce n'est plus une liste de spots maison, c'est une région."""
    spots = [
        await make_spot(name=f"Spot {i}", slug=f"spot-{i}", lat=39.0 + i / 100, lon=-9.0)
        for i in range(HOME_MAX + 5)
    ]
    preferences.favorite_spot_ids = [spot.id for spot in spots]
    await db_session.commit()

    counts = await recompute_tiers(db_session, preferences)

    assert counts["home"] == HOME_MAX
    home = (
        await db_session.execute(
            select(Spot).where(Spot.tier == SpotTier.HOME.value)
        )
    ).scalars().all()
    assert len(home) == HOME_MAX


async def test_demotion_when_a_favorite_is_removed(
    db_session, preferences, make_spot
) -> None:
    far = await make_spot(name="Nazaré", slug="nazare", lat=39.60, lon=-9.07)
    preferences.favorite_spot_ids = [far.id]
    await db_session.commit()
    await recompute_tiers(db_session, preferences)

    preferences.favorite_spot_ids = []
    await db_session.commit()
    await recompute_tiers(db_session, preferences)

    await db_session.refresh(far)
    assert far.tier == SpotTier.CATALOG.value
    assert far.is_active is False


async def test_position_opens_potential_spots_around_it(
    db_session, preferences, make_spot
) -> None:
    """Mode trip : on se déplace, les spots du coin s'activent sans rien régler."""
    away = await make_spot(name="Nazaré", slug="nazare", lat=39.60, lon=-9.07)
    await recompute_tiers(db_session, preferences)
    await db_session.refresh(away)
    assert away.tier == SpotTier.CATALOG.value

    moved = await record_position(db_session, preferences, 39.61, -9.08)

    assert moved is True
    await db_session.refresh(away)
    assert away.tier == SpotTier.POTENTIAL.value


async def test_small_gps_drift_does_not_recompute(
    db_session, preferences, make_spot
) -> None:
    """La géoloc d'un téléphone posé sur une table dérive de quelques mètres."""
    await record_position(db_session, preferences, HOSSEGOR_LAT, HOSSEGOR_LON)

    moved = await record_position(
        db_session, preferences, HOSSEGOR_LAT + 0.001, HOSSEGOR_LON
    )

    assert moved is False


async def test_preferences_are_created_on_first_access(db_session, user) -> None:
    preferences = await get_or_create_preferences(db_session, user.id)

    assert preferences.radius_km == pytest.approx(40.0)
    assert preferences.favorite_spot_ids == []
    assert preferences.hidden_spot_ids == []

    again = await get_or_create_preferences(db_session, user.id)
    assert again.id == preferences.id


async def test_without_home_or_position_nothing_is_activated(
    db_session, user, make_spot
) -> None:
    """Pas de domicile, pas de position : zéro appel, et c'est la bonne réponse."""
    preferences = await get_or_create_preferences(db_session, user.id)
    await make_spot(name="Proche", slug="proche")

    counts = await recompute_tiers(db_session, preferences)

    assert counts == {"home": 0, "potential": 0, "demoted": 1}
    assert set((await tiers(db_session)).values()) == {SpotTier.CATALOG.value}
