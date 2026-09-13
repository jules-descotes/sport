"""Dépense estimée du jour — décidée le 13/09 (retours n° 4).

Surf et séances, en kilocalories **supplémentaires**. Trois choses sont
protégées ici, et ce sont celles qui rendent le chiffre croyable :

1. le socle de 3 MET est celui du compendium, tout le reste est une modulation
   assumée — durée et taille des vagues déclarée ;
2. une taille non renseignée ne vaut **pas** « moyenne » : elle ne vaut rien ;
3. le métabolisme de repos est retranché, sans quoi la dépense est surestimée
   de 20 à 30 % et la cible calorique avec elle.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.services.nutrition import RESTING_MET, activity_kcal, surf_met

NOW = datetime(2026, 9, 12, 9, 0, tzinfo=UTC)
TODAY = NOW.date()


async def _session(auth_client, spot, **overrides):
    payload = {
        "spot_id": spot.id,
        "started_at": NOW.isoformat(),
        "duration_min": 120,
        **overrides,
    }
    response = await auth_client.post("/api/v1/sessions", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ── Le MET du surf ─────────────────────────────────────────────────────────


def test_the_base_is_three_met() -> None:
    """« Surf, général » au compendium. La seule valeur publiée du calcul.

    Tout le reste est une modulation assumée, et elle s'efface : une session
    très longue tend vers ce socle, parce que la troisième heure est une heure
    d'attente.
    """
    from app.services.nutrition import SURF_MET_BASE

    assert SURF_MET_BASE == 3.0
    assert surf_met(10 * 60, "small") == pytest.approx(3.3, abs=0.05)
    assert surf_met(40 * 60, "small") == pytest.approx(3.0, abs=0.1)


def test_a_short_session_costs_more_per_minute() -> None:
    """La première heure est une heure de rame."""
    assert surf_met(60) > surf_met(180)


@pytest.mark.parametrize(
    "size,expected",
    [(None, 4.5), ("small", 4.5), ("medium", 5.5), ("large", 6.5)],
)
def test_the_declared_wave_size_moves_the_met(size, expected) -> None:
    """+1 pour des vagues moyennes, +2 pour des grandes (retours n° 4)."""
    assert surf_met(120, size) == pytest.approx(expected)


def test_an_undeclared_size_is_not_a_medium_one() -> None:
    """Le choix prudent, et il est délibéré.

    Deviner « moyennes » gonflerait la cible de toutes les sessions que
    personne n'a décrites — et une cible trop haute ne se voit pas, elle se
    mange.
    """
    assert surf_met(120, None) == surf_met(120, "small")


def test_the_resting_metabolism_is_subtracted() -> None:
    """Une heure à 5 MET coûte 4 × poids de plus, pas 5 × poids.

    Oublier ce « −1 » surestime la dépense de 20 à 30 %, et sur une année de
    surf ça fait plusieurs kilos de cible qui n'existent pas.
    """
    assert activity_kcal(5.0, 75.0, 60) == pytest.approx((5.0 - RESTING_MET) * 75.0)
    assert RESTING_MET == 1.0


def test_a_session_without_duration_costs_nothing() -> None:
    assert surf_met(0) == 0.0


# ── La route ───────────────────────────────────────────────────────────────


async def test_an_empty_day_costs_nothing(auth_client) -> None:
    response = await auth_client.get("/api/v1/expenditure")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_kcal"] == 0
    assert body["items"] == []


async def test_a_surf_session_shows_up_with_its_spot(
    auth_client, make_spot, fake_archive
) -> None:
    fake_archive()
    spot = await make_spot(name="La Gravière")
    await _session(auth_client, spot, wave_size="large")

    body = (
        await auth_client.get(
            "/api/v1/expenditure", params={"day": TODAY.isoformat()}
        )
    ).json()

    assert body["surf_min"] == 120
    assert body["surf_kcal"] > 0
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["kind"] == "surf"
    assert item["label"] == "La Gravière"
    # Le détail dit **pourquoi** le chiffre est ce qu'il est. « MET 6,5 » ne
    # renseigne personne ; « grandes vagues » si.
    assert item["detail"] == "grandes vagues"


async def test_bigger_waves_cost_more_on_the_same_session(
    auth_client, make_spot, fake_archive
) -> None:
    """Le test qui relie vraiment les deux fonctionnalités du jour."""
    fake_archive()
    spot = await make_spot()
    created = await _session(auth_client, spot)

    plain = (
        await auth_client.get(
            "/api/v1/expenditure", params={"day": TODAY.isoformat()}
        )
    ).json()["total_kcal"]

    await auth_client.patch(
        f"/api/v1/sessions/{created['id']}", json={"wave_size": "large"}
    )

    described = (
        await auth_client.get(
            "/api/v1/expenditure", params={"day": TODAY.isoformat()}
        )
    ).json()["total_kcal"]

    assert described > plain


async def test_the_numbers_are_whole(auth_client, make_spot, fake_archive) -> None:
    """Jamais au kcal près : c'est une estimation, et l'écran le dit.

    Rendre des décimales suggérerait une précision que ni le MET du compendium
    ni une durée arrondie au quart d'heure n'ont.
    """
    fake_archive()
    spot = await make_spot()
    await _session(auth_client, spot, wave_size="medium")

    body = (
        await auth_client.get(
            "/api/v1/expenditure", params={"day": TODAY.isoformat()}
        )
    ).json()

    assert isinstance(body["total_kcal"], int)
    assert isinstance(body["items"][0]["kcal"], int)


async def test_a_session_of_another_day_is_not_counted(
    auth_client, make_spot, fake_archive
) -> None:
    fake_archive()
    spot = await make_spot()
    await _session(
        auth_client, spot, started_at=(NOW - timedelta(days=2)).isoformat()
    )

    body = (
        await auth_client.get(
            "/api/v1/expenditure", params={"day": TODAY.isoformat()}
        )
    ).json()

    assert body["total_kcal"] == 0


async def test_a_trashed_session_stops_counting(
    auth_client, make_spot, fake_archive
) -> None:
    """La corbeille retire la session de la journée, comme partout ailleurs."""
    fake_archive()
    spot = await make_spot()
    created = await _session(auth_client, spot)

    await auth_client.delete(f"/api/v1/sessions/{created['id']}")

    body = (
        await auth_client.get(
            "/api/v1/expenditure", params={"day": TODAY.isoformat()}
        )
    ).json()

    assert body["total_kcal"] == 0


async def test_the_weight_used_is_reported(auth_client) -> None:
    """Une estimation faite sur un poids par défaut n'a pas la même valeur."""
    body = (await auth_client.get("/api/v1/expenditure")).json()

    assert body["weight_kg"] > 0
    assert body["weight_estimated"] is True


async def test_a_weigh_in_stops_the_estimate(auth_client) -> None:
    await auth_client.post(
        "/api/v1/nutrition/weight", json={"weight_kg": 71.4}
    )

    body = (await auth_client.get("/api/v1/expenditure")).json()

    assert body["weight_estimated"] is False
    assert body["weight_kg"] == pytest.approx(71.4, abs=0.1)


async def test_expenditure_needs_a_session(client) -> None:
    assert (await client.get("/api/v1/expenditure")).status_code == 401


# ── Le même calcul alimente la cible ───────────────────────────────────────


async def test_the_target_uses_the_same_estimate(
    auth_client, make_spot, fake_archive
) -> None:
    """Un second calcul « pour l'affichage » finirait par donner deux chiffres.

    La seule conclusion possible serait alors qu'on ne peut se fier à aucun
    des deux.
    """
    fake_archive()
    spot = await make_spot()
    await _session(auth_client, spot, wave_size="large")

    standalone = (
        await auth_client.get(
            "/api/v1/expenditure", params={"day": TODAY.isoformat()}
        )
    ).json()
    day = (
        await auth_client.get(
            "/api/v1/nutrition/day", params={"day": TODAY.isoformat()}
        )
    ).json()

    assert round(day["target"]["expenditure"]["surf_kcal"]) == standalone[
        "surf_kcal"
    ]
