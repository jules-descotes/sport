"""Type de vagues — décidé le 13/09 (retours n° 3).

Trois axes optionnels : taille, longueur, forme. Ce qu'ils sont, et qui décide
de leur valeur pour une heure donnée.

Ce sont des **descripteurs des conditions observées**, pas des étiquettes de
confort : aucune API ne les mesure, seul quelqu'un dans l'eau peut les dire, et
c'est ce qui les rend exploitables au lot 3 comme cibles auxiliaires.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

NOW = datetime(2026, 9, 12, 9, 0, tzinfo=UTC)


async def _create(auth_client, spot, **overrides):
    payload = {
        "spot_id": spot.id,
        "started_at": NOW.isoformat(),
        "duration_min": 180,
        **overrides,
    }
    response = await auth_client.post("/api/v1/sessions", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ── La saisie ──────────────────────────────────────────────────────────────


async def test_the_three_axes_survive_the_round_trip(
    auth_client, make_spot, fake_archive
) -> None:
    fake_archive()
    spot = await make_spot()

    created = await _create(
        auth_client,
        spot,
        wave_size="medium",
        wave_length="long",
        wave_shape="hollow",
    )

    assert created["wave_size"] == "medium"
    assert created["wave_length"] == "long"
    assert created["wave_shape"] == "hollow"

    read = (await auth_client.get(f"/api/v1/sessions/{created['id']}")).json()
    assert read["wave_shape"] == "hollow"


async def test_a_session_without_them_says_nothing(
    auth_client, make_spot, fake_archive
) -> None:
    """Une absence de réponse n'est **pas** « moyenne ».

    Semer un défaut fabriquerait une observation que personne n'a faite — et
    c'est précisément ce que le modèle prendrait pour un fait.
    """
    fake_archive()
    spot = await make_spot()

    created = await _create(auth_client, spot)

    assert created["wave_size"] is None
    assert created["wave_length"] is None
    assert created["wave_shape"] is None


async def test_they_can_be_added_at_rating_time(
    auth_client, make_spot, fake_archive
) -> None:
    """Repliés sous « décrire les vagues » : on les pose quand on a le temps."""
    fake_archive()
    spot = await make_spot()
    created = await _create(auth_client, spot)

    updated = await auth_client.patch(
        f"/api/v1/sessions/{created['id']}",
        json={
            "rating_conditions": 4,
            "rating_personal": 3.5,
            "wave_size": "large",
            "wave_shape": "mushy",
        },
    )

    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["wave_size"] == "large"
    assert body["wave_shape"] == "mushy"
    # Non renseigné reste non renseigné.
    assert body["wave_length"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("wave_size", "enorme"),
        ("wave_length", "moyenne"),
        ("wave_shape", "tubulaire"),
    ],
)
async def test_an_unknown_value_is_refused(
    auth_client, make_spot, fake_archive, field, value
) -> None:
    """Trois valeurs par axe. Une quatrième se pose dans le code, pas au vol."""
    fake_archive()
    spot = await make_spot()

    response = await auth_client.post(
        "/api/v1/sessions",
        json={"spot_id": spot.id, "started_at": NOW.isoformat(), field: value},
    )

    assert response.status_code == 422


async def test_the_value_is_stored_not_the_enum_member(
    auth_client, make_spot, fake_archive, db_session
) -> None:
    """« small » en base, jamais « WaveSize.SMALL »."""
    from sqlalchemy import select

    from app.models.surf_session import SurfSession

    fake_archive()
    spot = await make_spot()
    created = await _create(auth_client, spot, wave_size="small")

    stored = (
        await db_session.execute(
            select(SurfSession.wave_size).where(SurfSession.id == created["id"])
        )
    ).scalar_one()
    assert stored == "small"


# ── Le segment prime pour son heure ────────────────────────────────────────


async def test_a_segment_carries_its_own_wave_type(
    auth_client, make_spot, fake_archive
) -> None:
    """La houle monte, la marée tourne : molle à 9 h, creuse à 11 h."""
    fake_archive()
    spot = await make_spot()
    created = await _create(
        auth_client, spot, wave_size="medium", wave_shape="mushy"
    )

    updated = await auth_client.patch(
        f"/api/v1/sessions/{created['id']}",
        json={
            "segments": [
                {
                    "started_at": NOW.isoformat(),
                    "rating_conditions": 3,
                    "wave_shape": "mushy",
                },
                {
                    "started_at": (NOW + timedelta(hours=2)).isoformat(),
                    "rating_conditions": 4.5,
                    "wave_shape": "hollow",
                    "wave_size": "large",
                },
            ]
        },
    )

    assert updated.status_code == 200, updated.text
    segments = updated.json()["segments"]
    assert [item["wave_shape"] for item in segments] == ["mushy", "hollow"]
    assert [item["wave_size"] for item in segments] == [None, "large"]
    # La session garde la sienne : elle décrit la séance dans son ensemble.
    assert updated.json()["wave_shape"] == "mushy"


async def test_an_hour_described_without_a_rating_is_kept(
    auth_client, make_spot, fake_archive
) -> None:
    """« Ça a molli à 10 h » se dit sans mettre de note.

    C'est le seul endroit où la règle « un segment vide est ignoré » cède : une
    heure décrite **est** un renseignement.
    """
    fake_archive()
    spot = await make_spot()
    created = await _create(auth_client, spot)

    updated = await auth_client.patch(
        f"/api/v1/sessions/{created['id']}",
        json={
            "segments": [
                {
                    "started_at": (NOW + timedelta(hours=1)).isoformat(),
                    "wave_shape": "mushy",
                }
            ]
        },
    )

    segments = updated.json()["segments"]
    assert len(segments) == 1
    assert segments[0]["wave_shape"] == "mushy"
    assert segments[0]["rating_conditions"] is None


async def test_an_hour_neither_rated_nor_described_is_ignored(
    auth_client, make_spot, fake_archive
) -> None:
    fake_archive()
    spot = await make_spot()
    created = await _create(auth_client, spot)

    updated = await auth_client.patch(
        f"/api/v1/sessions/{created['id']}",
        json={"segments": [{"started_at": NOW.isoformat()}]},
    )

    assert updated.json()["segments"] == []


async def test_re_describing_an_hour_replaces_it(
    auth_client, make_spot, fake_archive
) -> None:
    """Même chemin que les notes : mise à jour sur place, pas de doublon."""
    fake_archive()
    spot = await make_spot()
    created = await _create(auth_client, spot)

    for shape in ("mushy", "hollow"):
        response = await auth_client.patch(
            f"/api/v1/sessions/{created['id']}",
            json={
                "segments": [
                    {
                        "started_at": NOW.isoformat(),
                        "rating_conditions": 3,
                        "wave_shape": shape,
                    }
                ]
            },
        )
        assert response.status_code == 200, response.text

    segments = response.json()["segments"]
    assert len(segments) == 1
    assert segments[0]["wave_shape"] == "hollow"


# ── Le crible de l'historique ──────────────────────────────────────────────


async def test_the_history_filters_on_the_session_axis(
    auth_client, make_spot, fake_archive
) -> None:
    fake_archive()
    spot = await make_spot()
    await _create(
        auth_client,
        spot,
        started_at=(NOW - timedelta(days=1)).isoformat(),
        wave_shape="hollow",
    )
    await _create(
        auth_client,
        spot,
        started_at=(NOW - timedelta(days=2)).isoformat(),
        wave_shape="mushy",
    )

    body = (
        await auth_client.get(
            "/api/v1/sessions", params={"wave_shape": "hollow"}
        )
    ).json()

    assert len(body) == 1
    assert body[0]["wave_shape"] == "hollow"


async def test_the_filter_also_catches_a_described_hour(
    auth_client, make_spot, fake_archive
) -> None:
    """Molle dans l'ensemble, creuse à 11 h : elle ressort sur « creuse ».

    Même sémantique que l'affichage — un segment renseigné prime pour son
    heure. Un crible qui ne regarderait que la session raterait exactement les
    sessions que les segments servent à décrire.
    """
    fake_archive()
    spot = await make_spot()
    other_day = NOW - timedelta(days=1)
    described = await _create(
        auth_client,
        spot,
        started_at=other_day.isoformat(),
        wave_shape="mushy",
    )
    await auth_client.patch(
        f"/api/v1/sessions/{described['id']}",
        json={
            "segments": [
                {
                    "started_at": (other_day + timedelta(hours=2)).isoformat(),
                    "rating_conditions": 4.5,
                    "wave_shape": "hollow",
                }
            ]
        },
    )
    await _create(
        auth_client,
        spot,
        started_at=(NOW - timedelta(days=3)).isoformat(),
        wave_shape="mushy",
    )

    body = (
        await auth_client.get(
            "/api/v1/sessions", params={"wave_shape": "hollow"}
        )
    ).json()

    assert [item["id"] for item in body] == [described["id"]]


async def test_the_filters_stack_with_the_others(
    auth_client, make_spot, fake_archive
) -> None:
    fake_archive()
    spot = await make_spot()
    await _create(
        auth_client,
        spot,
        started_at=(NOW - timedelta(days=1)).isoformat(),
        wave_shape="hollow",
        rating_conditions=4.5,
        rating_personal=4,
    )
    await _create(
        auth_client,
        spot,
        started_at=(NOW - timedelta(days=2)).isoformat(),
        wave_shape="hollow",
        rating_conditions=2,
        rating_personal=2,
    )

    body = (
        await auth_client.get(
            "/api/v1/sessions",
            params={"wave_shape": "hollow", "min_rating": 4},
        )
    ).json()

    assert len(body) == 1
    assert body[0]["rating_conditions"] == 4.5


async def test_no_filter_still_returns_everything(
    auth_client, make_spot, fake_archive
) -> None:
    """Le cas courant : pas de crible, la liste complète."""
    fake_archive()
    spot = await make_spot()
    await _create(
        auth_client, spot, started_at=(NOW - timedelta(days=1)).isoformat()
    )
    await _create(
        auth_client,
        spot,
        started_at=(NOW - timedelta(days=2)).isoformat(),
        wave_shape="hollow",
    )

    body = (await auth_client.get("/api/v1/sessions")).json()

    assert len(body) == 2


# ── Les segments posés dès la création ─────────────────────────────────────


async def test_segments_can_be_posted_with_the_session(
    auth_client, make_spot, fake_archive
) -> None:
    """L'écran « Ajouter une session » les propose : ils ne doivent pas
    disparaître en route.

    `SurfSessionCreate` ne portait pas le champ, donc Pydantic le jetait en
    silence — le front l'envoyait depuis le 13/09, le serveur n'en gardait
    rien, et personne ne pouvait le voir sans comparer les deux.
    """
    fake_archive()
    spot = await make_spot()

    created = await _create(
        auth_client,
        spot,
        rating_conditions=4,
        rating_personal=3,
        segments=[
            {
                "started_at": NOW.isoformat(),
                "rating_conditions": 4.5,
                "wave_shape": "hollow",
            },
            {
                "started_at": (NOW + timedelta(hours=1)).isoformat(),
                "rating_conditions": 3,
            },
        ],
    )

    assert len(created["segments"]) == 2
    assert created["segments"][0]["wave_shape"] == "hollow"


async def test_a_session_without_segments_still_has_none(
    auth_client, make_spot, fake_archive
) -> None:
    fake_archive()
    spot = await make_spot()

    created = await _create(auth_client, spot)

    assert created["segments"] == []
