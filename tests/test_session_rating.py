"""Notation d'une session — le second temps de la saisie.

Le chemin rapide enregistre en quinze secondes et devine ce qu'il peut ; la
notation corrige, complète, et fait basculer la session en `rated`. Ce que ces
tests protègent :

- le statut est **déduit des deux notes**, jamais posé par le client ;
- corriger le spot ou l'heure **refait le snapshot** — sinon la session reste
  étiquetée avec les conditions d'une autre plage ou d'un autre moment ;
- le volet `observed` manquant est **rattrapé à la notation**, qui se fait au
  sec ;
- l'écran Jour reçoit tout ce qu'il lui faut en **un seul aller-retour**.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.enums import SessionStatus

NOW = datetime(2026, 9, 12, 9, 0, tzinfo=UTC)


async def _quick(auth_client, lat=43.6655, lon=-1.4415, ended_at=None):
    response = await auth_client.post(
        "/api/v1/sessions/quick",
        json={
            "lat": lat,
            "lon": lon,
            "ended_at": (ended_at or NOW).isoformat(),
        },
    )
    assert response.status_code == 201
    return response.json()["session"]


# ── Le statut est déduit ───────────────────────────────────────────────────


async def test_one_rating_alone_does_not_close_the_session(
    auth_client, make_spot, fake_archive, archive_bundle
) -> None:
    """Deux notes, jamais une seule (cf. CLAUDE.md, règle 6).

    Une session notée sur les conditions mais pas sur le ressenti sortirait de
    l'écran Jour sans être exploitable — or c'est justement le mélange des deux
    que la double note existe pour éviter.
    """
    fake_archive(bundle=archive_bundle(NOW))
    await make_spot()
    session = await _quick(auth_client)

    half = await auth_client.patch(
        f"/api/v1/sessions/{session['id']}", json={"rating_conditions": 4}
    )
    assert half.json()["status"] == SessionStatus.TO_RATE.value

    full = await auth_client.patch(
        f"/api/v1/sessions/{session['id']}", json={"rating_personal": 3}
    )
    assert full.json()["status"] == SessionStatus.RATED.value
    assert full.json()["rating_conditions"] == 4
    assert full.json()["rating_personal"] == 3


async def test_rating_records_the_board_and_the_wave_count(
    auth_client, user, make_spot, make_gear, fake_archive, archive_bundle
) -> None:
    fake_archive(bundle=archive_bundle(NOW))
    await make_spot()
    board = await make_gear(user)
    session = await _quick(auth_client)

    response = await auth_client.patch(
        f"/api/v1/sessions/{session['id']}",
        json={
            "rating_conditions": 5,
            "rating_personal": 4,
            "gear_id": board.id,
            "wave_count": 12,
            "duration_min": 105,
            "notes": "Gauche du pic, marée montante.",
        },
    )

    body = response.json()
    assert body["gear"]["name"] == board.name
    assert body["wave_count"] == 12
    assert body["duration_min"] == 105
    assert body["status"] == SessionStatus.RATED.value


# ── Corriger ce que le serveur avait deviné ────────────────────────────────


async def test_correcting_the_spot_refreezes_the_conditions(
    auth_client, make_spot, fake_archive, archive_bundle
) -> None:
    """Le chemin rapide devine le spot ; le corriger doit tout refaire suivre.

    Garder le snapshot de l'ancienne plage étiquetterait la session avec les
    conditions d'un autre endroit — et c'est cette ligne exacte qui servira à
    entraîner le modèle.
    """
    fake_archive(bundle=archive_bundle(NOW))
    await make_spot()
    # Un pic voisin, à quelques centaines de mètres : l'orientation diffère.
    other = await make_spot(
        name="Les Culs Nus", slug="les-culs-nus", lat=43.67, lon=-1.443
    )
    calls = fake_archive(bundle=archive_bundle(NOW))

    session = await _quick(auth_client)
    calls.clear()

    response = await auth_client.patch(
        f"/api/v1/sessions/{session['id']}",
        json={"spot_id": other.id, "rating_conditions": 3, "rating_personal": 3},
    )

    assert response.json()["spot_id"] == other.id
    # L'archive a bien été réinterrogée, et sur les coordonnées du **nouveau** spot.
    assert calls == [(other.lat, other.lon)]


async def test_moving_the_start_by_an_hour_refreezes_the_window(
    auth_client, make_spot, fake_archive, archive_bundle
) -> None:
    """Le début du chemin rapide est une estimation (fin − 90 min)."""
    fake_archive(bundle=archive_bundle(NOW))
    await make_spot()
    session = await _quick(auth_client)
    assert session["start_estimated"] is True

    corrected_start = datetime.fromisoformat(session["started_at"]) - timedelta(hours=2)
    response = await auth_client.patch(
        f"/api/v1/sessions/{session['id']}",
        json={"started_at": corrected_start.isoformat()},
    )

    body = response.json()
    # Ce n'est plus une estimation dès qu'on y a touché.
    assert body["start_estimated"] is False
    reference = datetime.fromisoformat(body["conditions_snapshot"]["reference_ts"])
    assert reference == corrected_start.replace(minute=0)


async def test_nudging_the_start_by_fifteen_minutes_keeps_the_window(
    auth_client, make_spot, fake_archive, archive_bundle
) -> None:
    """Les molettes vont par quinze minutes ; la fenêtre est calée à l'heure.

    Refaire le snapshot à chaque cran de molette coûterait un appel d'archive
    par tap, pour une fenêtre rigoureusement identique.
    """
    fake_archive(bundle=archive_bundle(NOW))
    await make_spot()
    session = await _quick(auth_client)
    calls = fake_archive(bundle=archive_bundle(NOW))

    nudged = datetime.fromisoformat(session["started_at"]) + timedelta(minutes=15)
    response = await auth_client.patch(
        f"/api/v1/sessions/{session['id']}", json={"started_at": nudged.isoformat()}
    )

    assert response.status_code == 200
    assert calls == []


async def test_a_missing_observed_panel_is_caught_up_when_rating(
    auth_client, make_spot, fake_archive, archive_bundle
) -> None:
    """Parking sans réseau à la sortie, wifi à la maison : on complète alors.

    C'est le rattrapage naturel, et il ne coûte rien puisqu'on est déjà en
    train d'écrire la ligne.
    """
    fake_archive(fail=True)
    await make_spot()
    session = await _quick(auth_client)
    assert session["conditions_snapshot"]["observed"] == []

    # De retour au sec.
    fake_archive(bundle=archive_bundle(NOW))
    response = await auth_client.patch(
        f"/api/v1/sessions/{session['id']}",
        json={"rating_conditions": 4, "rating_personal": 4},
    )

    snapshot = response.json()["conditions_snapshot"]
    assert len(snapshot["observed"]) == 3
    assert "observed_error" not in snapshot


# ── L'écran Jour ───────────────────────────────────────────────────────────


async def test_today_returns_pending_and_the_day_in_one_call(
    auth_client, make_spot, fake_archive, archive_bundle
) -> None:
    """Deux requêtes coûteraient deux allers-retours sur l'écran qu'on ouvre
    debout, sur un réseau de parking de plage."""
    fake_archive(bundle=archive_bundle(NOW))
    await make_spot()
    session = await _quick(auth_client)

    pending = await auth_client.get("/api/v1/sessions/today")
    assert [item["id"] for item in pending.json()["to_rate"]] == [session["id"]]
    assert [item["id"] for item in pending.json()["today"]] == [session["id"]]

    await auth_client.patch(
        f"/api/v1/sessions/{session['id']}",
        json={"rating_conditions": 4, "rating_personal": 5},
    )

    after = await auth_client.get("/api/v1/sessions/today")
    # Notée : le bloc « à noter » disparaît, la session du jour reste en pied.
    assert after.json()["to_rate"] == []
    assert [item["rating_conditions"] for item in after.json()["today"]] == [4]


async def test_an_old_unrated_session_keeps_asking(
    auth_client, make_spot, fake_archive, archive_bundle
) -> None:
    """Une session de samedi oubliée doit se rappeler au bon souvenir lundi.

    `to_rate` n'est pas filtré sur la journée : une session non notée ne vaut
    rien pour le modèle, et si l'écran cesse de la réclamer elle ne sera
    jamais notée.
    """
    fake_archive(bundle=archive_bundle(NOW))
    await make_spot()
    old = await _quick(auth_client, ended_at=NOW - timedelta(days=3))

    journal = await auth_client.get("/api/v1/sessions/today")
    assert [item["id"] for item in journal.json()["to_rate"]] == [old["id"]]
    # Elle n'est pas d'aujourd'hui pour autant.
    assert journal.json()["today"] == []


# ── Historique ─────────────────────────────────────────────────────────────


async def test_history_is_most_recent_first_and_carries_the_spot(
    auth_client, make_spot, fake_archive, archive_bundle
) -> None:
    """L'historique affiche le nom du spot : une requête par ligne serait absurde."""
    fake_archive(bundle=archive_bundle(NOW))
    spot = await make_spot()
    older = await _quick(auth_client, ended_at=NOW - timedelta(days=2))
    newer = await _quick(auth_client, ended_at=NOW)

    listing = await auth_client.get("/api/v1/sessions")
    body = listing.json()

    assert [item["id"] for item in body] == [newer["id"], older["id"]]
    assert body[0]["spot"]["name"] == spot.name


async def test_history_filters_on_status(
    auth_client, make_spot, fake_archive, archive_bundle
) -> None:
    fake_archive(bundle=archive_bundle(NOW))
    await make_spot()
    first = await _quick(auth_client, ended_at=NOW - timedelta(days=2))
    await _quick(auth_client, ended_at=NOW)

    await auth_client.patch(
        f"/api/v1/sessions/{first['id']}",
        json={"rating_conditions": 2, "rating_personal": 2},
    )

    rated = await auth_client.get("/api/v1/sessions?status=rated")
    assert [item["id"] for item in rated.json()] == [first["id"]]


async def test_a_ghost_session_can_be_deleted(
    auth_client, make_spot, fake_archive, archive_bundle
) -> None:
    """Un déclenchement de raccourci dans la poche doit avoir une issue.

    Sinon l'écran Jour porte pour toujours un bloc « à noter » qu'on ne peut
    pas noter, et on finit par ne plus le lire du tout.
    """
    fake_archive(bundle=archive_bundle(NOW))
    await make_spot()
    session = await _quick(auth_client)

    assert (
        await auth_client.delete(f"/api/v1/sessions/{session['id']}")
    ).status_code == 204
    assert (
        await auth_client.get(f"/api/v1/sessions/{session['id']}")
    ).status_code == 404


async def test_a_session_of_someone_else_is_invisible(
    auth_client, db_session, make_spot, fake_archive, archive_bundle
) -> None:
    """`user_id` est posé partout dès la première migration (cf. PROJET.md §11)."""
    from app.core.security import hash_password
    from app.models.surf_session import SurfSession
    from app.models.user import User

    fake_archive(bundle=archive_bundle(NOW))
    spot = await make_spot()

    other = User(email="pote@example.com", hashed_password=hash_password("x"))
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)

    theirs = SurfSession(
        user_id=other.id, spot_id=spot.id, started_at=NOW, discipline="surf"
    )
    db_session.add(theirs)
    await db_session.commit()
    await db_session.refresh(theirs)

    assert (await auth_client.get(f"/api/v1/sessions/{theirs.id}")).status_code == 404
    assert (await auth_client.get("/api/v1/sessions")).json() == []
