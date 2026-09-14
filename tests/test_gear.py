"""Matos — CRUD, compteur d'usure, et ce qu'on refuse de supprimer.

Deux règles portent tout le reste :

- **le compteur de sessions est calculé**, jamais stocké ;
- **on ne supprime pas du matos qui a servi**. Le lien session ↔ planche est
  de la donnée d'apprentissage (« proche de ta session du 12/10, tu étais en
  6'2 », cf. PROJET.md §7.2) ; le geste normal est de désactiver.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.enums import GearType

NOW = datetime(2026, 9, 12, 8, 0, tzinfo=UTC)


async def test_create_read_update_a_board(auth_client) -> None:
    created = await auth_client.post(
        "/api/v1/gear",
        json={
            "name": "6'2 Pyzel",
            "gear_type": GearType.BOARD.value,
            # 1,88 m, pas « 6'2 » : un pied-pouce est une unité composite, et
            # la base n'en stocke pas (cf. CLAUDE.md).
            "length_m": 1.88,
            "volume_l": 30.0,
            "discipline": "surf",
            "purchased_on": "2025-04-18",
        },
    )

    assert created.status_code == 201
    body = created.json()
    assert body["length_m"] == 1.88
    assert body["is_active"] is True

    updated = await auth_client.patch(
        f"/api/v1/gear/{body['id']}", json={"volume_l": 31.5}
    )
    assert updated.status_code == 200
    assert updated.json()["volume_l"] == 31.5
    # Ce qui n'a pas été envoyé n'a pas bougé.
    assert updated.json()["name"] == "6'2 Pyzel"

    listing = await auth_client.get("/api/v1/gear")
    assert [item["name"] for item in listing.json()] == ["6'2 Pyzel"]


async def test_a_mistyped_board_can_be_corrected_field_by_field(
    auth_client, user, make_gear
) -> None:
    """Se tromper de planche à la saisie n'est pas une fatalité.

    Le PATCH ne touche qu'aux champs envoyés : corriger une longueur ne doit
    pas ramener le volume à ce que la molette de l'écran savait afficher.
    """
    gear = await make_gear(user, name="6'2 Pizel", length_m=1.88, volume_l=30.0)

    fixed = await auth_client.patch(
        f"/api/v1/gear/{gear.id}",
        # 6'3, et un nom qui s'écrit comme sur la planche.
        json={"name": "6'3 Pyzel", "length_m": 1.905},
    )

    assert fixed.status_code == 200
    body = fixed.json()
    assert body["name"] == "6'3 Pyzel"
    assert body["length_m"] == 1.905
    assert body["volume_l"] == 30.0
    assert body["gear_type"] == GearType.BOARD.value


async def test_a_correction_cannot_erase_what_the_base_requires(
    auth_client, user, make_gear
) -> None:
    """`null` sur un champ non nullable est ignoré, pas passé à la base.

    Tout est optionnel dans `GearUpdate` — c'est ce qui permet de corriger un
    volume sans retaper le reste — donc rien n'empêche d'envoyer `name: null`.
    En base, ce serait une contrainte NOT NULL violée et un 500.
    """
    gear = await make_gear(user, name="6'2 Pyzel")

    response = await auth_client.patch(
        f"/api/v1/gear/{gear.id}", json={"name": None, "volume_l": 28.0}
    )

    assert response.status_code == 200
    assert response.json()["name"] == "6'2 Pyzel"
    # Ce qui était envoyable, lui, est bien passé.
    assert response.json()["volume_l"] == 28.0


async def test_a_length_outside_any_surfboard_is_refused(auth_client) -> None:
    """18 m n'est pas une planche, c'est une faute de frappe."""
    response = await auth_client.post(
        "/api/v1/gear", json={"name": "Erreur", "length_m": 18.0}
    )
    assert response.status_code == 422


async def test_deactivating_keeps_it_out_of_the_way_without_losing_it(
    auth_client, user, make_gear
) -> None:
    """Une planche revendue sort des pastilles de saisie, pas de l'historique."""
    gear = await make_gear(user)

    await auth_client.patch(f"/api/v1/gear/{gear.id}", json={"is_active": False})

    active_only = await auth_client.get("/api/v1/gear?include_inactive=false")
    assert active_only.json() == []

    everything = await auth_client.get("/api/v1/gear")
    assert len(everything.json()) == 1
    assert everything.json()[0]["is_active"] is False


async def test_session_count_and_last_use_are_computed(
    auth_client, user, make_spot, make_gear, fake_archive, archive_bundle
) -> None:
    """Le compteur vient des sessions, pas d'une colonne qui se désynchronise.

    `last_used_at` porte la présélection de l'écran de notation : la planche
    proposée est la dernière utilisée.
    """
    fake_archive(bundle=archive_bundle(NOW))
    spot = await make_spot()
    board = await make_gear(user, name="6'2 Pyzel")
    longboard = await make_gear(user, name="9'1 Log", length_m=2.77)

    for index, hours in enumerate((72, 24)):
        await auth_client.post(
            "/api/v1/sessions",
            json={
                "spot_id": spot.id,
                "started_at": (NOW - timedelta(hours=hours)).isoformat(),
                "duration_min": 90,
                "gear_id": board.id,
                "rating_conditions": 4,
                "rating_personal": 4 + index % 2,
            },
        )

    listing = await auth_client.get("/api/v1/gear")
    by_name = {item["name"]: item for item in listing.json()}

    assert by_name["6'2 Pyzel"]["session_count"] == 2
    assert by_name["9'1 Log"]["session_count"] == 0
    assert by_name["9'1 Log"]["last_used_at"] is None
    # La plus récente des deux, pas la première venue.
    assert datetime.fromisoformat(
        by_name["6'2 Pyzel"]["last_used_at"]
    ) == NOW - timedelta(hours=24)


async def test_unused_gear_can_be_deleted(auth_client, user, make_gear) -> None:
    gear = await make_gear(user)
    assert (await auth_client.delete(f"/api/v1/gear/{gear.id}")).status_code == 204
    assert (await auth_client.get("/api/v1/gear")).json() == []


async def test_deleting_used_gear_is_refused_and_says_why(
    auth_client, user, make_spot, make_gear, fake_archive, archive_bundle
) -> None:
    """Perdre le lien conditions ↔ planche pour ranger une liste serait un
    mauvais échange : le 409 propose la désactivation à la place."""
    fake_archive(bundle=archive_bundle(NOW))
    spot = await make_spot()
    gear = await make_gear(user)

    await auth_client.post(
        "/api/v1/sessions",
        json={
            "spot_id": spot.id,
            "started_at": NOW.isoformat(),
            "gear_id": gear.id,
        },
    )

    response = await auth_client.delete(f"/api/v1/gear/{gear.id}")
    assert response.status_code == 409
    assert "Désactive" in response.json()["detail"]


async def test_a_session_cannot_point_at_unknown_gear(
    auth_client, make_spot, fake_archive, archive_bundle
) -> None:
    fake_archive(bundle=archive_bundle(NOW))
    spot = await make_spot()

    response = await auth_client.post(
        "/api/v1/sessions",
        json={"spot_id": spot.id, "started_at": NOW.isoformat(), "gear_id": 4242},
    )
    assert response.status_code == 404


async def test_gear_needs_a_session(client) -> None:
    assert (await client.get("/api/v1/gear")).status_code == 401
