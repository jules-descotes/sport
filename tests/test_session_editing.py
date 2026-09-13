"""Création et modification d'une session **depuis le navigateur** (13/09).

Le raccourci iPhone reste le chemin normal, mais il ne couvre pas tout : un
téléphone resté dans la voiture, une session d'il y a trois semaines, un trip
dont on saisit les six sessions au retour. Ce qui se teste ici :

- une session **passée** créée à la main déclenche le même backfill, et son
  volet `forecast` reste **borné aux runs émis avant le début** ;
- une **modification** qui change le spot ou l'heure refait le figeage et
  **conserve** l'ancien — c'est la seule donnée irrattrapable du projet ;
- la **corbeille** : trente jours, restauration à l'identique, purge.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models.surf_session import SurfSession
from app.services.sessions import (
    SNAPSHOT_HISTORY_MAX,
    TRASH_RETENTION_DAYS,
    purge_trashed_sessions,
)


async def _create(auth_client, spot, started_at, **extra) -> dict:
    payload = {
        "spot_id": spot.id,
        "started_at": started_at.isoformat(),
        "duration_min": 90,
        "rating_conditions": 4,
        "rating_personal": 3,
        **extra,
    }
    response = await auth_client.post("/api/v1/sessions", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ── Création manuelle d'une session passée ────────────────────────────────


async def test_manual_past_session_is_backfilled(
    auth_client, make_spot, fake_archive, archive_bundle
):
    """Une session d'il y a trois semaines remonte l'archive comme les autres."""
    three_weeks_ago = (datetime.now(UTC) - timedelta(days=21)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    calls = fake_archive(archive_bundle(three_weeks_ago))
    spot = await make_spot()

    body = await _create(auth_client, spot, three_weeks_ago)

    assert len(calls) == 1
    snapshot = body["conditions_snapshot"]
    # Deux heures d'approche, l'heure du départ, et l'heure entamée après :
    # la fenêtre couvre la durée de la session depuis le 13/09.
    assert [entry["offset_h"] for entry in snapshot["observed"]] == [-2, -1, 0, 1]
    assert snapshot["trends"]["observed"]["wave_height_m"] is not None


async def test_manual_session_keeps_both_ratings(
    auth_client, make_spot, fake_archive
):
    """Saisie au sec, à tête reposée : les deux notes sont posées d'emblée."""
    fake_archive()
    spot = await make_spot()
    started = datetime.now(UTC) - timedelta(days=2)

    body = await _create(auth_client, spot, started)

    assert body["status"] == "rated"
    assert body["rating_conditions"] == 4
    assert body["rating_personal"] == 3


async def test_forecast_panel_only_keeps_runs_issued_before_the_start(
    auth_client, make_spot, make_forecast, fake_archive
):
    """Le point qui compte, et il vaut aussi pour une saisie manuelle.

    Une passe d'ingestion postérieure à la session est un **constat déguisé** :
    la retenir reviendrait à donner au modèle une information qu'il n'avait pas
    au moment de prédire (`PROJET.md` §7.1).
    """
    fake_archive()
    spot = await make_spot()
    started = datetime.now(UTC).replace(
        minute=0, second=0, microsecond=0
    ) - timedelta(days=3)

    # Ce qu'on savait avant d'y aller : 1,0 m.
    await make_forecast(
        spot,
        start=started - timedelta(hours=3),
        hours=6,
        run_ts=started - timedelta(hours=12),
        wave_height_m=1.0,
    )
    # Ce qu'une passe postérieure a écrit : 2,5 m. Elle ne doit pas entrer.
    await make_forecast(
        spot,
        start=started - timedelta(hours=3),
        hours=6,
        run_ts=started + timedelta(hours=6),
        wave_height_m=2.5,
    )

    body = await _create(auth_client, spot, started)

    panel = body["conditions_snapshot"]["forecast"]
    assert panel, "le volet forecast devrait être rempli"
    assert all(entry["wave_height_m"] == 1.0 for entry in panel)


# ── Modification ───────────────────────────────────────────────────────────


async def test_changing_the_spot_redoes_the_snapshot_and_keeps_the_old(
    auth_client, make_spot, fake_archive, db_session
):
    fake_archive()
    gravière = await make_spot(name="La Gravière", slug="la-graviere")
    estagnots = await make_spot(
        name="Les Estagnots", slug="les-estagnots", lat=43.68, lon=-1.44
    )
    started = datetime.now(UTC) - timedelta(days=1)

    created = await _create(auth_client, gravière, started)
    first_snapshot = created["conditions_snapshot"]

    response = await auth_client.patch(
        f"/api/v1/sessions/{created['id']}", json={"spot_id": estagnots.id}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["spot_id"] == estagnots.id
    # L'ancien est empilé, pas écrasé.
    assert len(body["snapshot_history"]) == 1
    archived = body["snapshot_history"][0]
    assert archived["reason"] == "spot modifié"
    assert archived["spot_id"] == gravière.id
    assert archived["snapshot"]["reference_ts"] == first_snapshot["reference_ts"]


async def test_changing_the_hour_redoes_the_snapshot_and_keeps_the_old(
    auth_client, make_spot, fake_archive
):
    fake_archive()
    spot = await make_spot()
    started = datetime.now(UTC).replace(
        hour=9, minute=0, second=0, microsecond=0
    ) - timedelta(days=1)

    created = await _create(auth_client, spot, started)

    moved = started.replace(hour=15)
    response = await auth_client.patch(
        f"/api/v1/sessions/{created['id']}",
        json={"started_at": moved.isoformat()},
    )

    body = response.json()
    assert body["snapshot_history"][0]["reason"] == "début modifié"
    assert body["conditions_snapshot"]["reference_ts"].startswith(
        moved.strftime("%Y-%m-%dT%H")
    )


async def test_quarter_hour_nudges_do_not_touch_the_snapshot(
    auth_client, make_spot, fake_archive
):
    """La fenêtre est calée à l'heure pleine : quinze minutes ne changent rien.

    Refaire le figeage à chaque cran de molette ferait un appel d'archive par
    tap, et remplirait l'historique de versions identiques.
    """
    fake_archive()
    spot = await make_spot()
    started = datetime.now(UTC).replace(
        hour=9, minute=0, second=0, microsecond=0
    ) - timedelta(days=1)

    created = await _create(auth_client, spot, started)

    response = await auth_client.patch(
        f"/api/v1/sessions/{created['id']}",
        json={"started_at": started.replace(minute=15).isoformat()},
    )

    assert response.json()["snapshot_history"] == []


async def test_rating_alone_never_archives_a_snapshot(
    auth_client, make_spot, fake_archive
):
    """Noter n'est pas corriger : l'historique ne doit pas se remplir de bruit."""
    fake_archive()
    spot = await make_spot()
    started = datetime.now(UTC) - timedelta(hours=3)

    created = await _create(auth_client, spot, started)

    response = await auth_client.patch(
        f"/api/v1/sessions/{created['id']}",
        json={"rating_conditions": 5, "rating_personal": 5, "wave_count": 12},
    )

    assert response.json()["snapshot_history"] == []


async def test_snapshot_history_is_capped(auth_client, make_spot, fake_archive):
    """Une session corrigée vingt fois est une session qu'on cherche encore."""
    fake_archive()
    spot = await make_spot()
    started = datetime.now(UTC).replace(
        hour=8, minute=0, second=0, microsecond=0
    ) - timedelta(days=2)

    created = await _create(auth_client, spot, started)

    for hour in range(9, 9 + SNAPSHOT_HISTORY_MAX + 3):
        await auth_client.patch(
            f"/api/v1/sessions/{created['id']}",
            json={"started_at": started.replace(hour=hour % 24).isoformat()},
        )

    body = (await auth_client.get(f"/api/v1/sessions/{created['id']}")).json()
    assert len(body["snapshot_history"]) == SNAPSHOT_HISTORY_MAX


# ── Corbeille ──────────────────────────────────────────────────────────────


async def test_delete_moves_to_the_trash(auth_client, make_spot, fake_archive):
    fake_archive()
    spot = await make_spot()
    created = await _create(auth_client, spot, datetime.now(UTC) - timedelta(days=1))

    assert (
        await auth_client.delete(f"/api/v1/sessions/{created['id']}")
    ).status_code == 204

    # Elle n'existe plus du point de vue de l'app…
    assert (
        await auth_client.get(f"/api/v1/sessions/{created['id']}")
    ).status_code == 404
    assert (await auth_client.get("/api/v1/sessions")).json() == []
    # …mais elle est récupérable.
    trash = (await auth_client.get("/api/v1/sessions/trash")).json()
    assert [item["id"] for item in trash] == [created["id"]]


async def test_trashed_sessions_leave_the_day_screen(
    auth_client, make_spot, fake_archive
):
    fake_archive()
    spot = await make_spot()
    created = await _create(
        auth_client,
        spot,
        datetime.now(UTC) - timedelta(hours=2),
        rating_conditions=None,
        rating_personal=None,
    )
    assert created["status"] == "to_rate"

    await auth_client.delete(f"/api/v1/sessions/{created['id']}")

    journal = (await auth_client.get("/api/v1/sessions/today")).json()
    assert journal["to_rate"] == []
    assert journal["today"] == []


async def test_restore_brings_it_back_unchanged(
    auth_client, make_spot, fake_archive
):
    """Une session restaurée doit être **exactement** celle qui a été supprimée.

    Sinon la corbeille ne répare pas l'erreur, elle en fabrique une autre.
    """
    fake_archive()
    spot = await make_spot()
    created = await _create(auth_client, spot, datetime.now(UTC) - timedelta(days=1))
    await auth_client.delete(f"/api/v1/sessions/{created['id']}")

    response = await auth_client.post(
        f"/api/v1/sessions/{created['id']}/restore"
    )

    assert response.status_code == 200
    restored = response.json()
    assert restored["deleted_at"] is None
    assert restored["rating_conditions"] == created["rating_conditions"]
    assert restored["started_at"] == created["started_at"]
    assert restored["conditions_snapshot"] == created["conditions_snapshot"]
    assert (await auth_client.get("/api/v1/sessions")).json() != []


async def test_a_trashed_session_cannot_be_edited(
    auth_client, make_spot, fake_archive
):
    fake_archive()
    spot = await make_spot()
    created = await _create(auth_client, spot, datetime.now(UTC) - timedelta(days=1))
    await auth_client.delete(f"/api/v1/sessions/{created['id']}")

    response = await auth_client.patch(
        f"/api/v1/sessions/{created['id']}", json={"rating_conditions": 5}
    )

    assert response.status_code == 404


async def test_trash_route_is_declared_before_the_parameterised_one(auth_client):
    """Sans cet ordre, FastAPI lirait « trash » comme un identifiant (422)."""
    response = await auth_client.get("/api/v1/sessions/trash")
    assert response.status_code == 200


async def test_purge_destroys_only_what_is_past_thirty_days(
    auth_client, make_spot, fake_archive, db_session
):
    fake_archive()
    spot = await make_spot()
    recent = await _create(auth_client, spot, datetime.now(UTC) - timedelta(days=1))
    old = await _create(auth_client, spot, datetime.now(UTC) - timedelta(days=60))

    await auth_client.delete(f"/api/v1/sessions/{recent['id']}")
    await auth_client.delete(f"/api/v1/sessions/{old['id']}")

    # On vieillit artificiellement la seconde suppression.
    session = await db_session.get(SurfSession, old["id"])
    session.deleted_at = datetime.now(UTC) - timedelta(
        days=TRASH_RETENTION_DAYS + 1
    )
    await db_session.commit()

    purged = await purge_trashed_sessions(db_session)

    assert purged == 1
    assert await db_session.get(SurfSession, old["id"]) is None
    assert await db_session.get(SurfSession, recent["id"]) is not None


async def test_expired_trash_is_not_offered_for_restore(
    auth_client, make_spot, fake_archive, db_session
):
    """Entre deux passes du job, une session peut avoir dépassé ses trente
    jours sans être encore détruite : la proposer serait une promesse qu'on ne
    tiendra pas au prochain cycle."""
    fake_archive()
    spot = await make_spot()
    created = await _create(auth_client, spot, datetime.now(UTC) - timedelta(days=60))
    await auth_client.delete(f"/api/v1/sessions/{created['id']}")

    session = await db_session.get(SurfSession, created["id"])
    session.deleted_at = datetime.now(UTC) - timedelta(
        days=TRASH_RETENTION_DAYS + 2
    )
    await db_session.commit()

    assert (await auth_client.get("/api/v1/sessions/trash")).json() == []


# ── Filtres de l'historique ────────────────────────────────────────────────


async def test_history_filters_by_spot(auth_client, make_spot, fake_archive):
    fake_archive()
    first = await make_spot(name="La Gravière", slug="la-graviere")
    second = await make_spot(
        name="Lafitenia", slug="lafitenia", lat=43.41, lon=-1.63
    )
    await _create(auth_client, first, datetime.now(UTC) - timedelta(days=1))
    await _create(auth_client, second, datetime.now(UTC) - timedelta(days=2))

    body = (
        await auth_client.get("/api/v1/sessions", params={"spot_id": second.id})
    ).json()

    assert [item["spot_id"] for item in body] == [second.id]


async def test_history_filters_by_minimum_condition_rating(
    auth_client, make_spot, fake_archive
):
    """Le crible porte sur la note **de conditions** : c'est celle qu'on cherche
    en refaisant l'historique d'un spot."""
    fake_archive()
    spot = await make_spot()
    await _create(
        auth_client,
        spot,
        datetime.now(UTC) - timedelta(days=1),
        rating_conditions=2,
        rating_personal=5,
    )
    await _create(
        auth_client,
        spot,
        datetime.now(UTC) - timedelta(days=3),
        rating_conditions=5,
        rating_personal=2,
    )

    body = (
        await auth_client.get("/api/v1/sessions", params={"min_rating": 4})
    ).json()

    assert [item["rating_conditions"] for item in body] == [5]


async def test_history_filters_by_month(auth_client, make_spot, fake_archive):
    fake_archive()
    spot = await make_spot()
    recent = datetime.now(UTC) - timedelta(days=2)
    older = datetime.now(UTC) - timedelta(days=75)
    await _create(auth_client, spot, recent)
    await _create(auth_client, spot, older)

    body = (
        await auth_client.get(
            "/api/v1/sessions",
            params={"since": (recent - timedelta(days=1)).date().isoformat()},
        )
    ).json()

    assert len(body) == 1


@pytest.mark.parametrize("route", ["/api/v1/sessions/trash"])
async def test_trash_requires_authentication(client, route):
    assert (await client.get(route)).status_code == 401
