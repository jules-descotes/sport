"""Demi-points et segments horaires — décidés le 13/09 après deux jours d'usage.

Deux retours qui tiennent ensemble : « 3 ou 4 » ne suffisait pas à départager
deux sessions d'une même semaine, et une session de deux heures et demie n'est
pas une note — la houle monte, le vent se lève, la marée tourne.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models.surf_session import SurfSession
from app.schemas.session import from_half, to_half
from app.services.backfill import MAX_SESSION_HOURS, window_offsets

NOW = datetime(2026, 9, 12, 9, 0, tzinfo=UTC)


async def _create(auth_client, spot, **overrides):
    payload = {
        "spot_id": spot.id,
        "started_at": (NOW - timedelta(hours=3)).isoformat(),
        "duration_min": 120,
        **overrides,
    }
    response = await auth_client.post("/api/v1/sessions", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ── La conversion, au bord ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "rating,stored", [(1.0, 2), (2.5, 5), (3.5, 7), (4.0, 8), (5.0, 10)]
)
def test_a_rating_is_stored_doubled(rating: float, stored: int) -> None:
    """La base porte `note × 2`. 7 se relit 3,5, et jamais 7/5."""
    assert to_half(rating) == stored
    assert from_half(stored) == rating


def test_an_absent_rating_stays_absent() -> None:
    """Une session non notée n'a pas de note, et surtout pas un zéro."""
    assert to_half(None) is None
    assert from_half(None) is None


# ── La saisie ──────────────────────────────────────────────────────────────


async def test_a_half_point_survives_the_round_trip(
    auth_client, make_spot, fake_archive
) -> None:
    fake_archive()
    spot = await make_spot()

    created = await _create(
        auth_client, spot, rating_conditions=3.5, rating_personal=4.5
    )

    assert created["rating_conditions"] == 3.5
    assert created["rating_personal"] == 4.5
    assert created["status"] == "rated"

    read = await auth_client.get(f"/api/v1/sessions/{created['id']}")
    assert read.json()["rating_conditions"] == 3.5


async def test_a_whole_number_still_works(
    auth_client, make_spot, fake_archive
) -> None:
    """La non-régression qui compte : l'échelle s'élargit, elle ne change pas."""
    fake_archive()
    spot = await make_spot()

    created = await _create(
        auth_client, spot, rating_conditions=4, rating_personal=2
    )

    assert created["rating_conditions"] == 4.0
    assert created["rating_personal"] == 2.0


async def test_a_quarter_point_is_refused(
    auth_client, make_spot, fake_archive
) -> None:
    """3,7 n'est pas une note : personne ne l'a saisie.

    Arrondir en silence accepterait une valeur que l'échelle à dix crans ne
    permet pas, et l'échelle cesserait d'être exacte au premier client
    approximatif.
    """
    fake_archive()
    spot = await make_spot()

    response = await auth_client.post(
        "/api/v1/sessions",
        json={
            "spot_id": spot.id,
            "started_at": NOW.isoformat(),
            "rating_conditions": 3.7,
        },
    )

    assert response.status_code == 422


async def test_the_history_filter_reads_half_points(
    auth_client, make_spot, fake_archive
) -> None:
    """Un filtre « au moins 4 » ne doit pas laisser passer un 3,5."""
    fake_archive()
    spot = await make_spot()
    await _create(
        auth_client,
        spot,
        started_at=(NOW - timedelta(days=1)).isoformat(),
        rating_conditions=3.5,
        rating_personal=3,
    )
    await _create(
        auth_client,
        spot,
        started_at=(NOW - timedelta(days=2)).isoformat(),
        rating_conditions=4.5,
        rating_personal=3,
    )

    body = (
        await auth_client.get("/api/v1/sessions", params={"min_rating": 4})
    ).json()

    assert [item["rating_conditions"] for item in body] == [4.5]


async def test_one_half_rating_alone_does_not_close_the_session(
    auth_client, make_spot, fake_archive
) -> None:
    """Les **deux** notes, jamais une seule (CLAUDE.md, règle 6)."""
    fake_archive()
    spot = await make_spot()

    created = await _create(auth_client, spot, rating_conditions=3.5)

    assert created["status"] == "to_rate"


# ── La fenêtre du snapshot suit la durée ───────────────────────────────────


def test_a_session_without_duration_keeps_the_historic_window() -> None:
    """Sans durée, on ne sait rien : T−2 h, T−1 h, T0, comme avant."""
    assert window_offsets(None) == (-2, -1, 0)
    assert window_offsets(0) == (-2, -1, 0)


@pytest.mark.parametrize(
    "duration,expected",
    [
        (45, (-2, -1, 0)),
        (60, (-2, -1, 0)),
        # 61 minutes ont entamé l'heure suivante, et elle mérite sa ligne.
        (61, (-2, -1, 0, 1)),
        (150, (-2, -1, 0, 1, 2)),
    ],
)
def test_the_window_covers_every_hour_started(duration, expected) -> None:
    """« Entamée » et pas « pleine » : une session de 8 h 15 à 10 h 40 a vécu
    l'heure de 10 h."""
    assert window_offsets(duration) == expected


def test_an_absurd_duration_does_not_blow_up_the_window() -> None:
    """Une session de douze heures est une erreur de saisie, pas une session."""
    offsets = window_offsets(12 * 60)
    assert max(offsets) == MAX_SESSION_HOURS


async def test_a_long_session_gets_a_line_per_hour(
    auth_client, make_spot, fake_archive, archive_bundle
) -> None:
    """Sans cette extension, un segment de la troisième heure ne vaudrait rien.

    C'est tout l'intérêt : chaque heure notée s'apparie à **ses** conditions.
    """
    fake_archive(bundle=archive_bundle(NOW))
    spot = await make_spot()

    created = await _create(
        auth_client,
        spot,
        started_at=NOW.isoformat(),
        duration_min=180,
        rating_conditions=4,
        rating_personal=4,
    )

    snapshot = created["conditions_snapshot"]
    assert snapshot["window_hours"] == [-2, -1, 0, 1, 2]
    assert [entry["offset_h"] for entry in snapshot["observed"]] == [-2, -1, 0, 1, 2]


async def test_the_tide_still_refers_to_the_start_of_the_session(
    auth_client, make_spot, fake_archive, archive_bundle, db_session
) -> None:
    """La marée du snapshot est celle du **départ**, pas de la sortie de l'eau.

    Depuis que la fenêtre s'étend, sa dernière heure est la fin de la session.
    Y rapporter la marée ferait basculer le « moment de la marée » de toutes
    les sessions longues, et la feature 7 du registre changerait de sens sans
    que rien ne le dise.
    """
    fake_archive(bundle=archive_bundle(NOW))
    spot = await make_spot()

    short = await _create(
        auth_client, spot, started_at=NOW.isoformat(), duration_min=30
    )
    long = await _create(
        auth_client,
        spot,
        started_at=NOW.isoformat(),
        duration_min=240,
        client_uuid="long",
    )

    assert (
        short["conditions_snapshot"]["tide"]["position"]
        == long["conditions_snapshot"]["tide"]["position"]
    )


# ── Les segments horaires ──────────────────────────────────────────────────


async def test_segments_are_saved_and_read_back(
    auth_client, make_spot, fake_archive
) -> None:
    fake_archive()
    spot = await make_spot()
    created = await _create(
        auth_client,
        spot,
        started_at=NOW.isoformat(),
        duration_min=180,
        rating_conditions=3,
        rating_personal=3,
    )

    updated = await auth_client.patch(
        f"/api/v1/sessions/{created['id']}",
        json={
            "segments": [
                {
                    "started_at": NOW.isoformat(),
                    "rating_conditions": 4.5,
                    "rating_personal": 4,
                },
                {
                    "started_at": (NOW + timedelta(hours=1)).isoformat(),
                    "rating_conditions": 2.5,
                    "rating_personal": 3,
                },
            ]
        },
    )

    segments = updated.json()["segments"]
    assert [item["rating_conditions"] for item in segments] == [4.5, 2.5]
    # La note globale reste la référence d'affichage : les segments ne la
    # touchent pas.
    assert updated.json()["rating_conditions"] == 3.0


async def test_a_segment_is_pinned_to_the_full_hour(
    auth_client, make_spot, fake_archive
) -> None:
    """C'est la clé d'appariement avec la ligne horaire du snapshot.

    Un segment à 9 h 17 n'aurait rien à quoi se rattacher : Open-Meteo est
    horaire, et la fenêtre du snapshot aussi.
    """
    fake_archive()
    spot = await make_spot()
    created = await _create(auth_client, spot, started_at=NOW.isoformat())

    updated = await auth_client.patch(
        f"/api/v1/sessions/{created['id']}",
        json={
            "segments": [
                {
                    "started_at": (NOW + timedelta(minutes=17)).isoformat(),
                    "rating_conditions": 4,
                }
            ]
        },
    )

    stamp = updated.json()["segments"][0]["started_at"]
    assert datetime.fromisoformat(stamp) == NOW


async def test_every_segment_matches_a_line_of_the_snapshot(
    auth_client, make_spot, fake_archive, archive_bundle
) -> None:
    """Le test qui compte : sans appariement, un segment ne vaut rien."""
    fake_archive(bundle=archive_bundle(NOW))
    spot = await make_spot()
    created = await _create(
        auth_client, spot, started_at=NOW.isoformat(), duration_min=180
    )

    updated = await auth_client.patch(
        f"/api/v1/sessions/{created['id']}",
        json={
            "segments": [
                {
                    "started_at": (NOW + timedelta(hours=hour)).isoformat(),
                    "rating_conditions": 4,
                    "rating_personal": 3,
                }
                for hour in range(3)
            ]
        },
    )

    body = updated.json()
    # Comparaison sur les **instants** et non sur les chaînes : « Z » et
    # « +00:00 » désignent la même heure, et un test qui comparerait le texte
    # échouerait sur une différence de typographie.
    observed = {
        datetime.fromisoformat(entry["ts"])
        for entry in body["conditions_snapshot"]["observed"]
    }
    assert body["segments"]
    for segment in body["segments"]:
        assert datetime.fromisoformat(segment["started_at"]) in observed


async def test_an_empty_list_erases_the_segments(
    auth_client, make_spot, fake_archive
) -> None:
    """Un doigt mouillé en note une de temps en temps : il faut pouvoir défaire."""
    fake_archive()
    spot = await make_spot()
    created = await _create(auth_client, spot, started_at=NOW.isoformat())

    await auth_client.patch(
        f"/api/v1/sessions/{created['id']}",
        json={
            "segments": [
                {"started_at": NOW.isoformat(), "rating_conditions": 4}
            ]
        },
    )
    cleared = await auth_client.patch(
        f"/api/v1/sessions/{created['id']}", json={"segments": []}
    )

    assert cleared.json()["segments"] == []


async def test_not_sending_segments_leaves_them_alone(
    auth_client, make_spot, fake_archive
) -> None:
    """`None` et liste vide ne veulent pas dire la même chose.

    Noter la session depuis l'écran de notation ne doit pas effacer une frise
    saisie la veille.
    """
    fake_archive()
    spot = await make_spot()
    created = await _create(auth_client, spot, started_at=NOW.isoformat())

    await auth_client.patch(
        f"/api/v1/sessions/{created['id']}",
        json={
            "segments": [
                {"started_at": NOW.isoformat(), "rating_conditions": 4}
            ]
        },
    )
    untouched = await auth_client.patch(
        f"/api/v1/sessions/{created['id']}",
        json={"rating_conditions": 5, "rating_personal": 5},
    )

    assert len(untouched.json()["segments"]) == 1


async def test_an_empty_segment_is_ignored(
    auth_client, make_spot, fake_archive
) -> None:
    """Une ligne ouverte puis laissée vide n'est pas un renseignement."""
    fake_archive()
    spot = await make_spot()
    created = await _create(auth_client, spot, started_at=NOW.isoformat())

    updated = await auth_client.patch(
        f"/api/v1/sessions/{created['id']}",
        json={
            "segments": [
                {"started_at": NOW.isoformat()},
                {
                    "started_at": (NOW + timedelta(hours=1)).isoformat(),
                    "rating_conditions": 3,
                },
            ]
        },
    )

    assert len(updated.json()["segments"]) == 1


async def test_deleting_a_session_takes_its_segments(
    auth_client, make_spot, fake_archive, db_session
) -> None:
    """Un segment sans session n'a aucun sens."""
    from sqlalchemy import func, select

    from app.models.session_segment import SessionSegment

    fake_archive()
    spot = await make_spot()
    created = await _create(auth_client, spot, started_at=NOW.isoformat())
    await auth_client.patch(
        f"/api/v1/sessions/{created['id']}",
        json={
            "segments": [
                {"started_at": NOW.isoformat(), "rating_conditions": 4}
            ]
        },
    )

    session = await db_session.get(SurfSession, created["id"])
    await db_session.delete(session)
    await db_session.commit()

    remaining = await db_session.execute(
        select(func.count()).select_from(SessionSegment)
    )
    assert remaining.scalar_one() == 0


# ── Re-noter une heure déjà notée (bug de production du 13/09) ──────────────
#
# `PATCH /sessions/1` avec des segments répondait 500 en production, et le
# navigateur affichait une erreur CORS — la réponse d'erreur sortait du
# `ServerErrorMiddleware` sans passer par `CORSMiddleware`.
#
# La cause est dans le flush : remplacer la collection entière fait écrire les
# nouvelles lignes **avant** que SQLAlchemy ne supprime les orphelines, et
# `uq_session_segments_session_hour` refuse la deuxième ligne de 8 h.


async def test_resending_the_same_hour_replaces_its_ratings(
    auth_client, make_spot, fake_archive
) -> None:
    """Le geste qui cassait : corriger une heure déjà notée."""
    fake_archive()
    spot = await make_spot()
    created = await _create(
        auth_client, spot, started_at=NOW.isoformat(), duration_min=180
    )

    first = await auth_client.patch(
        f"/api/v1/sessions/{created['id']}",
        json={
            "segments": [
                {
                    "started_at": NOW.isoformat(),
                    "rating_conditions": 4,
                    "rating_personal": 3,
                },
                {
                    "started_at": (NOW + timedelta(hours=1)).isoformat(),
                    "rating_conditions": 3,
                    "rating_personal": 3,
                },
            ]
        },
    )
    assert first.status_code == 200, first.text

    second = await auth_client.patch(
        f"/api/v1/sessions/{created['id']}",
        json={
            "segments": [
                {
                    "started_at": NOW.isoformat(),
                    "rating_conditions": 5,
                    "rating_personal": 4.5,
                },
                {
                    "started_at": (NOW + timedelta(hours=1)).isoformat(),
                    "rating_conditions": 3,
                    "rating_personal": 3,
                },
            ]
        },
    )

    assert second.status_code == 200, second.text
    segments = second.json()["segments"]
    assert [item["rating_conditions"] for item in segments] == [5.0, 3.0]
    assert [item["rating_personal"] for item in segments] == [4.5, 3.0]


async def test_a_segment_can_be_dropped_while_another_is_kept(
    auth_client, make_spot, fake_archive, db_session
) -> None:
    """Effacer une heure notée par erreur, sans toucher aux autres."""
    from sqlalchemy import func, select

    from app.models.session_segment import SessionSegment

    fake_archive()
    spot = await make_spot()
    created = await _create(
        auth_client, spot, started_at=NOW.isoformat(), duration_min=180
    )

    await auth_client.patch(
        f"/api/v1/sessions/{created['id']}",
        json={
            "segments": [
                {"started_at": NOW.isoformat(), "rating_conditions": 4},
                {
                    "started_at": (NOW + timedelta(hours=1)).isoformat(),
                    "rating_conditions": 2,
                },
                {
                    "started_at": (NOW + timedelta(hours=2)).isoformat(),
                    "rating_conditions": 3,
                },
            ]
        },
    )

    trimmed = await auth_client.patch(
        f"/api/v1/sessions/{created['id']}",
        json={
            "segments": [
                {
                    "started_at": (NOW + timedelta(hours=2)).isoformat(),
                    "rating_conditions": 3.5,
                }
            ]
        },
    )

    assert trimmed.status_code == 200, trimmed.text
    segments = trimmed.json()["segments"]
    assert len(segments) == 1
    assert segments[0]["rating_conditions"] == 3.5

    # Les orphelines sont parties, pas seulement détachées.
    remaining = await db_session.execute(
        select(func.count()).select_from(SessionSegment)
    )
    assert remaining.scalar_one() == 1


async def test_an_hour_shifted_by_one_keeps_the_untouched_hours(
    auth_client, make_spot, fake_archive
) -> None:
    """Le cas mixte : une heure conservée, une supprimée, une ajoutée."""
    fake_archive()
    spot = await make_spot()
    created = await _create(
        auth_client, spot, started_at=NOW.isoformat(), duration_min=180
    )

    await auth_client.patch(
        f"/api/v1/sessions/{created['id']}",
        json={
            "segments": [
                {"started_at": NOW.isoformat(), "rating_conditions": 4},
                {
                    "started_at": (NOW + timedelta(hours=1)).isoformat(),
                    "rating_conditions": 2,
                },
            ]
        },
    )

    shifted = await auth_client.patch(
        f"/api/v1/sessions/{created['id']}",
        json={
            "segments": [
                {"started_at": NOW.isoformat(), "rating_conditions": 4},
                {
                    "started_at": (NOW + timedelta(hours=2)).isoformat(),
                    "rating_conditions": 5,
                },
            ]
        },
    )

    assert shifted.status_code == 200, shifted.text
    segments = shifted.json()["segments"]
    assert [item["rating_conditions"] for item in segments] == [4.0, 5.0]


async def test_rating_a_session_that_already_has_segments(
    auth_client, make_spot, fake_archive
) -> None:
    """Le PATCH de production : les deux notes **et** les segments d'un coup."""
    fake_archive()
    spot = await make_spot()
    created = await _create(
        auth_client, spot, started_at=NOW.isoformat(), duration_min=180
    )
    await auth_client.patch(
        f"/api/v1/sessions/{created['id']}",
        json={
            "segments": [
                {"started_at": NOW.isoformat(), "rating_conditions": 3},
            ]
        },
    )

    rated = await auth_client.patch(
        f"/api/v1/sessions/{created['id']}",
        json={
            "rating_conditions": 4,
            "rating_personal": 3.5,
            "segments": [
                {
                    "started_at": NOW.isoformat(),
                    "rating_conditions": 3,
                    "rating_personal": 3,
                },
                {
                    "started_at": (NOW + timedelta(hours=1)).isoformat(),
                    "rating_conditions": 4.5,
                    "rating_personal": 4,
                },
            ],
        },
    )

    assert rated.status_code == 200, rated.text
    body = rated.json()
    assert body["status"] == "rated"
    assert body["rating_conditions"] == 4.0
    assert len(body["segments"]) == 2
