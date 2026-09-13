"""Classement des favoris — décidé le 13/09 (retours n° 4), règle B.2.

Jour montrait la prévision du favori principal et trois annonces. Utile, et
incomplet : une annonce dit qu'un spot correspond, elle ne dit pas lequel des
quatre est le meilleur ce matin — ce qui est la question qu'on se pose en
ouvrant l'app.

Ce que ces tests protègent :

1. la note de journée est un **produit** (part des heures × qualité), pas une
   somme ;
2. un favori **sans critères** est classé sur le seul score, et signalé ;
3. un favori **sans prévision** est rendu, rangé en bas, et **pas noté**.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest


async def _favorite(auth_client, spot) -> None:
    response = await auth_client.post(
        f"/api/v1/spots/{spot.slug}/favorite", json={"favorite": True}
    )
    assert response.status_code == 200, response.text


async def _rules(auth_client, spot, **overrides) -> None:
    payload = {
        "wave_height_min_m": 0.5,
        "wave_height_max_m": 4.0,
        "wave_period_min_s": 6.0,
        "swell_sectors": [],
        "wind_sectors": [],
        "wind_max_kt": 30.0,
        "tide_phases": [],
        "hour_min": None,
        "hour_max": None,
        **overrides,
    }
    response = await auth_client.put(
        f"/api/v1/spots/{spot.slug}/rules", json=payload
    )
    assert response.status_code == 200, response.text
    return response.json()


# ── Le classement ──────────────────────────────────────────────────────────


async def test_no_favorites_gives_nothing(auth_client) -> None:
    response = await auth_client.get("/api/v1/spots/favorites/ranking")

    assert response.status_code == 200, response.text
    assert response.json() == []


async def test_a_favorite_without_forecast_is_listed_but_not_scored(
    auth_client, make_spot
) -> None:
    """Un spot jamais ingéré n'est pas un mauvais spot.

    Lui inventer une note serait pire que de n'en donner aucune — on le range
    en bas, et on dit qu'il n'a pas de prévision.
    """
    spot = await make_spot(name="Jamais vu")
    await _favorite(auth_client, spot)

    body = (await auth_client.get("/api/v1/spots/favorites/ranking")).json()

    assert len(body) == 1
    assert body[0]["spot"]["name"] == "Jamais vu"
    assert body[0]["has_forecast"] is False
    assert body[0]["best_day_score"] == 0.0


async def test_a_favorite_without_rules_is_flagged(
    auth_client, make_spot, make_forecast
) -> None:
    """Sans règles, « correspond » ne veut rien dire.

    Tous ses créneaux correspondraient et il finirait toujours premier. On le
    classe donc sur le seul score, et l'écran le signale.
    """
    spot = await make_spot()
    await make_forecast(spot)
    await _favorite(auth_client, spot)

    body = (await auth_client.get("/api/v1/spots/favorites/ranking")).json()

    assert body[0]["has_rules"] is False
    assert body[0]["days"]
    # La part vaut 1 : on ne peut pas la calculer, et la mettre à zéro ferait
    # disparaître du classement un spot qu'on vient de mettre en favori.
    assert body[0]["days"][0]["match_ratio"] == 1.0


async def test_rules_make_the_ratio_meaningful(
    auth_client, make_spot, make_forecast
) -> None:
    spot = await make_spot()
    await make_forecast(spot)
    await _favorite(auth_client, spot)
    # Des critères que rien ne remplit : la part doit tomber à zéro, pas la
    # prévision.
    await _rules(auth_client, spot, wave_height_min_m=9.0, wave_height_max_m=12.0)

    body = (await auth_client.get("/api/v1/spots/favorites/ranking")).json()

    assert body[0]["has_rules"] is True
    assert body[0]["days"][0]["matching_hours"] == 0
    assert body[0]["days"][0]["day_score"] == 0.0
    # La journée existe quand même : on sait qu'il y avait des heures de jour.
    assert body[0]["has_forecast"] is True


async def test_a_matching_spot_outranks_one_that_never_matches(
    auth_client, make_spot, make_forecast
) -> None:
    """Le test qui décide si le classement sert à quelque chose."""
    good = await make_spot(name="Celui qui marche", slug="celui-qui-marche")
    bad = await make_spot(name="Celui qui ne marche pas", slug="celui-qui-non")
    await make_forecast(good)
    await make_forecast(bad)
    await _favorite(auth_client, good)
    await _favorite(auth_client, bad)

    await _rules(auth_client, good, wave_height_min_m=0.1)
    await _rules(auth_client, bad, wave_height_min_m=9.0, wave_height_max_m=12.0)

    body = (await auth_client.get("/api/v1/spots/favorites/ranking")).json()

    assert [row["spot"]["name"] for row in body] == [
        "Celui qui marche",
        "Celui qui ne marche pas",
    ]
    assert body[0]["best_day_score"] > body[1]["best_day_score"]


async def test_the_day_score_is_a_product_not_a_sum(
    auth_client, make_spot, make_forecast
) -> None:
    """Part × qualité.

    Un spot excellent une heure par jour et un spot correct toute la journée
    ne se départagent pas par addition : le premier demande d'être là à 8 h,
    le second se décide au réveil.
    """
    spot = await make_spot()
    await make_forecast(spot)
    await _favorite(auth_client, spot)
    await _rules(auth_client, spot, wave_height_min_m=0.1)

    day = (
        await auth_client.get("/api/v1/spots/favorites/ranking")
    ).json()[0]["days"][0]

    assert day["day_score"] == pytest.approx(
        round(day["match_ratio"] * day["average_score"], 2), abs=0.02
    )


async def test_the_best_window_is_continuous(
    auth_client, make_spot, make_forecast
) -> None:
    """Deux heures séparées par une qui ne correspond pas ne font pas trois.

    C'est la différence entre y aller et le regretter.
    """
    spot = await make_spot()
    await make_forecast(spot)
    await _favorite(auth_client, spot)
    await _rules(auth_client, spot, wave_height_min_m=0.1)

    day = (
        await auth_client.get("/api/v1/spots/favorites/ranking")
    ).json()[0]["days"][0]

    if day["window_start"] is not None:
        start = datetime.fromisoformat(day["window_start"])
        end = datetime.fromisoformat(day["window_end"])
        assert end > start
        assert (end - start) <= timedelta(hours=day["matching_hours"])


async def test_the_horizon_is_bounded(auth_client, make_spot, make_forecast) -> None:
    """Aujourd'hui et demain. Au-delà, une prévision de houle est une intention."""
    spot = await make_spot()
    await make_forecast(spot)
    await _favorite(auth_client, spot)

    default = (await auth_client.get("/api/v1/spots/favorites/ranking")).json()
    assert len(default[0]["days"]) == 2

    refused = await auth_client.get(
        "/api/v1/spots/favorites/ranking", params={"days": 9}
    )
    assert refused.status_code == 422


async def test_ranking_needs_a_session(client) -> None:
    assert (
        await client.get("/api/v1/spots/favorites/ranking")
    ).status_code == 401


async def test_the_route_is_not_read_as_a_spot_reference(
    auth_client, make_spot
) -> None:
    """Route fixe **avant** `/spots/{spot_ref}` (cf. CLAUDE.md).

    Sans cet ordre, FastAPI lirait « favorites » comme un identifiant et
    renverrait 422 — la panne classique de ce fichier.
    """
    await make_spot()
    response = await auth_client.get("/api/v1/spots/favorites/ranking")

    assert response.status_code == 200


# ── L'aperçu de la fiche de critères ───────────────────────────────────────


async def test_saving_rules_answers_with_a_preview(
    auth_client, make_spot, make_forecast
) -> None:
    """« Sur les 3 prochains jours, ça matcherait N heures ».

    Sans lui, on règle des seuils à l'aveugle et on découvre trois jours plus
    tard qu'on a écrit des critères que la côte ne remplit jamais.
    """
    spot = await make_spot()
    await make_forecast(spot)

    saved = await _rules(auth_client, spot, wave_height_min_m=0.1)

    assert saved["preview"] is not None
    assert saved["preview"]["daylight_hours"] > 0
    assert saved["preview"]["matching_hours"] > 0


async def test_impossible_rules_preview_zero(
    auth_client, make_spot, make_forecast
) -> None:
    spot = await make_spot()
    await make_forecast(spot)

    saved = await _rules(
        auth_client, spot, wave_height_min_m=9.0, wave_height_max_m=12.0
    )

    assert saved["preview"]["matching_hours"] == 0
    # Les heures de jour, elles, existent : on distingue « aucune heure ne
    # correspond » de « aucune prévision ».
    assert saved["preview"]["daylight_hours"] > 0


async def test_a_spot_without_forecast_previews_nothing(
    auth_client, make_spot
) -> None:
    spot = await make_spot()

    saved = await _rules(auth_client, spot)

    assert saved["preview"]["daylight_hours"] == 0
    assert saved["preview"]["matching_hours"] == 0
