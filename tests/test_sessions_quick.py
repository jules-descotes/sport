"""`POST /sessions/quick` — le chemin des quinze secondes.

C'est l'endpoint dont dépend tout le lot, et il est le seul du projet dont
l'échec ne se verrait pas : une session perdue ne laisse aucune trace. Ce que
ces tests protègent :

- le **spot est deviné** — le plus proche à moins de 2 km, sinon le favori du
  profil, et la réponse dit lequel des deux ;
- l'appel est **idempotent** — deux déclenchements du raccourci dans la même
  minute donnent une seule session ;
- l'authentification passe par un **jeton Bearer révocable**, parce que le
  raccourci iOS n'a pas de cookies ;
- le volet `forecast` du snapshot **n'inclut aucun run émis après le début** de
  la session — c'est du décalage train/serve, et il ne se voit qu'en production.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.enums import SessionStatus
from app.models.profile import Profile
from app.models.surf_session import SurfSession
from app.services.forecast_ingest import upsert_forecast_rows
from app.services.openmeteo import HourlyBundle
from app.services.sessions import QUICK_DEFAULT_DURATION_MIN

# Sortie de l'eau en fin de matinée, côte landaise.
SESSION_END = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)
SESSION_START = SESSION_END - timedelta(minutes=QUICK_DEFAULT_DURATION_MIN)

# La Gravière est à 43.664 / −1.440 dans les fixtures. Deux points : l'un dans
# l'eau juste devant, l'autre à une quinzaine de kilomètres dans les terres.
IN_FRONT_OF_THE_SPOT = (43.6655, -1.4415)
FAR_INLAND = (43.6640, -1.2500)


async def _set_home_spot(db_session, user, spot):
    profile = (
        await db_session.execute(select(Profile).where(Profile.user_id == user.id))
    ).scalar_one()
    profile.home_spot_id = spot.id
    await db_session.commit()


async def _bearer_headers(auth_client) -> dict[str, str]:
    response = await auth_client.post(
        "/api/v1/auth/tokens", json={"name": "Raccourci iPhone"}
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['token']}"}


# ── Le spot est deviné ─────────────────────────────────────────────────────


async def test_quick_picks_the_nearest_spot(
    auth_client, make_spot, fake_archive, archive_bundle
) -> None:
    """Debout sur le sable, la position suffit à nommer le spot."""
    fake_archive(bundle=archive_bundle(SESSION_END))
    spot = await make_spot()
    lat, lon = IN_FRONT_OF_THE_SPOT

    response = await auth_client.post(
        "/api/v1/sessions/quick",
        json={"lat": lat, "lon": lon, "ended_at": SESSION_END.isoformat()},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["created"] is True
    assert body["spot_source"] == "nearest"
    assert body["spot_distance_km"] < 0.5
    assert body["session"]["spot_id"] == spot.id
    assert body["session"]["spot"]["name"] == spot.name


async def test_quick_falls_back_on_the_profile_favourite(
    auth_client, db_session, user, make_spot, fake_archive, archive_bundle
) -> None:
    """Hors zone connue, on rattache au favori plutôt que d'inventer un spot.

    Le favori sera souvent faux dans ce cas — c'est assumé : `spot_source` le
    signale, et l'écran de notation propose les cinq plus proches en un tap.
    Refuser la session, en revanche, la perdrait pour de bon.
    """
    fake_archive(bundle=archive_bundle(SESSION_END))
    spot = await make_spot()
    await _set_home_spot(db_session, user, spot)
    lat, lon = FAR_INLAND

    response = await auth_client.post(
        "/api/v1/sessions/quick",
        json={"lat": lat, "lon": lon, "ended_at": SESSION_END.isoformat()},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["spot_source"] == "home"
    assert body["spot_distance_km"] is None
    assert body["session"]["spot_id"] == spot.id


async def test_quick_without_position_uses_the_favourite(
    auth_client, db_session, user, make_spot, fake_archive, archive_bundle
) -> None:
    """Géoloc refusée dans les Raccourcis : la session existe quand même."""
    fake_archive(bundle=archive_bundle(SESSION_END))
    spot = await make_spot()
    await _set_home_spot(db_session, user, spot)

    response = await auth_client.post(
        "/api/v1/sessions/quick", json={"ended_at": SESSION_END.isoformat()}
    )

    assert response.status_code == 201
    assert response.json()["session"]["spot_id"] == spot.id


async def test_quick_without_spot_nor_favourite_says_what_to_do(
    auth_client, fake_archive, archive_bundle
) -> None:
    """Rien à quoi rattacher la session : on refuse, et on dit quoi faire."""
    fake_archive(bundle=archive_bundle(SESSION_END))

    response = await auth_client.post(
        "/api/v1/sessions/quick",
        json={"lat": FAR_INLAND[0], "lon": FAR_INLAND[1]},
    )

    assert response.status_code == 409
    assert "favori" in response.json()["detail"]


# ── Ce que le serveur déduit ───────────────────────────────────────────────


async def test_quick_estimates_the_start_and_marks_it_as_such(
    auth_client, make_spot, fake_archive, archive_bundle
) -> None:
    """Fin − 90 min, et `start_estimated` dit que c'est une estimation.

    Sans ce drapeau, une heure devinée par le serveur se lirait plus tard comme
    une heure relevée — et la fenêtre de conditions figée autour d'elle avec.
    """
    fake_archive(bundle=archive_bundle(SESSION_END))
    await make_spot()

    response = await auth_client.post(
        "/api/v1/sessions/quick",
        json={
            "lat": IN_FRONT_OF_THE_SPOT[0],
            "lon": IN_FRONT_OF_THE_SPOT[1],
            "ended_at": SESSION_END.isoformat(),
        },
    )

    session = response.json()["session"]
    assert session["duration_min"] == QUICK_DEFAULT_DURATION_MIN
    assert datetime.fromisoformat(session["started_at"]) == SESSION_START
    assert session["start_estimated"] is True
    # Elle part « à noter » : c'est tout l'intérêt de couper la saisie en deux.
    assert session["status"] == SessionStatus.TO_RATE.value
    assert session["rating_conditions"] is None


async def test_quick_returns_a_deep_link_to_the_rating_screen(
    auth_client, make_spot, fake_archive, archive_bundle
) -> None:
    """Le raccourci ouvre ce lien juste après l'envoi.

    C'est ce qui fait que « noter plus tard » ne veut pas dire « ne jamais
    noter » : l'écran de notation est à un tap de la sortie de l'eau.
    """
    fake_archive(bundle=archive_bundle(SESSION_END))
    await make_spot()

    response = await auth_client.post(
        "/api/v1/sessions/quick",
        json={
            "lat": IN_FRONT_OF_THE_SPOT[0],
            "lon": IN_FRONT_OF_THE_SPOT[1],
            "ended_at": SESSION_END.isoformat(),
        },
    )

    body = response.json()
    session_id = body["session"]["id"]
    assert body["rate_path"] == f"/sessions/{session_id}/noter"
    assert body["rate_url"].endswith(f"/sessions/{session_id}/noter")
    assert body["rate_url"].startswith("http")


async def test_quick_freezes_the_conditions_window(
    auth_client, make_spot, fake_archive, archive_bundle
) -> None:
    """La fenêtre T−2 h / T−1 h / T0 est figée à la sortie de l'eau.

    C'est la seule décision de modèle irrattrapable après coup : un point
    unique ne porte aucune tendance, et la tendance est un des signaux les plus
    forts (cf. CLAUDE.md, règle 7).
    """
    fake_archive(bundle=archive_bundle(SESSION_END))
    await make_spot()

    response = await auth_client.post(
        "/api/v1/sessions/quick",
        json={
            "lat": IN_FRONT_OF_THE_SPOT[0],
            "lon": IN_FRONT_OF_THE_SPOT[1],
            "ended_at": SESSION_END.isoformat(),
        },
    )

    snapshot = response.json()["session"]["conditions_snapshot"]
    # Le chemin rapide estime 90 min : la fenêtre couvre l'heure entamée après
    # le départ, en plus des deux heures d'approche.
    assert snapshot["window_hours"] == [-2, -1, 0, 1]
    assert [entry["offset_h"] for entry in snapshot["observed"]] == [-2, -1, 0, 1]
    # Houle montante dans le jeu d'archive : la tendance doit se voir.
    assert snapshot["trends"]["observed"]["wave_height_m"] > 0


async def test_quick_survives_an_unreachable_archive(
    auth_client, make_spot, fake_archive
) -> None:
    """Parking sans réseau : la session s'enregistre, le volet manquant se dit.

    Perdre une session pour un timeout serait le comble — le risque du projet
    est la friction de saisie, pas la rareté des données.
    """
    fake_archive(fail=True)
    await make_spot()

    response = await auth_client.post(
        "/api/v1/sessions/quick",
        json={
            "lat": IN_FRONT_OF_THE_SPOT[0],
            "lon": IN_FRONT_OF_THE_SPOT[1],
            "ended_at": SESSION_END.isoformat(),
        },
    )

    assert response.status_code == 201
    snapshot = response.json()["session"]["conditions_snapshot"]
    assert snapshot["observed"] == []
    assert snapshot["observed_error"]


# ── Volet forecast : rien qui vienne d'après ───────────────────────────────


async def test_forecast_panel_excludes_runs_emitted_after_the_start(
    auth_client, db_session, make_spot, fake_archive, archive_bundle
) -> None:
    """Une passe d'ingestion postérieure au début est un constat déguisé.

    La retenir donnerait au modèle une information dont il ne disposait pas au
    moment de prédire : c'est le décalage train/serve de PROJET.md §7.1, dans
    sa version la plus discrète — celle qui ne se voit qu'en production.
    """
    fake_archive(bundle=archive_bundle(SESSION_END))
    spot = await make_spot()

    window = [SESSION_START.replace(minute=0) + timedelta(hours=h) for h in (-2, -1, 0)]
    # Ce qu'on avait sous les yeux avant d'aller à l'eau.
    await upsert_forecast_rows(
        db_session,
        spot.id,
        HourlyBundle(rows={ts: {"wave_height_m": 0.9} for ts in window}),
        run_ts=SESSION_START - timedelta(hours=3),
    )
    # Et la passe d'après, qui « savait » ce qui s'était vraiment passé.
    await upsert_forecast_rows(
        db_session,
        spot.id,
        HourlyBundle(rows={ts: {"wave_height_m": 2.6} for ts in window}),
        run_ts=SESSION_END + timedelta(hours=2),
    )

    response = await auth_client.post(
        "/api/v1/sessions/quick",
        json={
            "lat": IN_FRONT_OF_THE_SPOT[0],
            "lon": IN_FRONT_OF_THE_SPOT[1],
            "ended_at": SESSION_END.isoformat(),
        },
    )

    panel = response.json()["session"]["conditions_snapshot"]["forecast"]
    assert len(panel) == 3
    assert all(entry["wave_height_m"] == 0.9 for entry in panel)


# ── Idempotence ────────────────────────────────────────────────────────────


async def test_two_quick_calls_in_a_row_make_one_session(
    auth_client, db_session, make_spot, fake_archive, archive_bundle
) -> None:
    """Un raccourci iOS se déclenche deux fois pour un doigt mouillé.

    Une session en double pollue l'historique autant qu'une session manquante :
    le modèle compterait deux fois la même journée.
    """
    fake_archive(bundle=archive_bundle(SESSION_END))
    await make_spot()
    payload = {
        "lat": IN_FRONT_OF_THE_SPOT[0],
        "lon": IN_FRONT_OF_THE_SPOT[1],
        "ended_at": SESSION_END.isoformat(),
    }

    first = await auth_client.post("/api/v1/sessions/quick", json=payload)
    # Cinq minutes plus tard, le temps de remonter à la voiture.
    payload["ended_at"] = (SESSION_END + timedelta(minutes=5)).isoformat()
    second = await auth_client.post("/api/v1/sessions/quick", json=payload)

    assert first.json()["created"] is True
    assert second.json()["created"] is False
    assert second.json()["session"]["id"] == first.json()["session"]["id"]

    count = await db_session.execute(select(SurfSession))
    assert len(count.scalars().all()) == 1


async def test_two_real_sessions_in_a_day_are_two_sessions(
    auth_client, db_session, make_spot, fake_archive, archive_bundle
) -> None:
    """La fenêtre d'idempotence ne doit pas manger la session du soir."""
    fake_archive(bundle=archive_bundle(SESSION_END))
    await make_spot()

    morning = await auth_client.post(
        "/api/v1/sessions/quick",
        json={
            "lat": IN_FRONT_OF_THE_SPOT[0],
            "lon": IN_FRONT_OF_THE_SPOT[1],
            "ended_at": SESSION_END.isoformat(),
        },
    )
    evening = await auth_client.post(
        "/api/v1/sessions/quick",
        json={
            "lat": IN_FRONT_OF_THE_SPOT[0],
            "lon": IN_FRONT_OF_THE_SPOT[1],
            "ended_at": (SESSION_END + timedelta(hours=8)).isoformat(),
        },
    )

    assert evening.json()["created"] is True
    assert evening.json()["session"]["id"] != morning.json()["session"]["id"]

    count = await db_session.execute(select(SurfSession))
    assert len(count.scalars().all()) == 2


async def test_client_uuid_is_idempotent_outside_the_window(
    auth_client, db_session, make_spot, fake_archive, archive_bundle
) -> None:
    """La file hors ligne rejoue ses envois : trois tentatives, une session.

    Le `client_uuid` est l'idempotence **exacte**, indépendante de l'horloge :
    une file bloquée trois jours sur le parking rejoue au retour du réseau, et
    la fenêtre de dix minutes est alors largement dépassée.
    """
    fake_archive(bundle=archive_bundle(SESSION_END))
    await make_spot()
    payload = {
        "lat": IN_FRONT_OF_THE_SPOT[0],
        "lon": IN_FRONT_OF_THE_SPOT[1],
        "ended_at": SESSION_END.isoformat(),
        "client_uuid": "9f8b-parking-sans-reseau",
    }

    first = await auth_client.post("/api/v1/sessions/quick", json=payload)
    payload["ended_at"] = (SESSION_END + timedelta(days=3)).isoformat()
    replay = await auth_client.post("/api/v1/sessions/quick", json=payload)

    assert replay.json()["created"] is False
    assert replay.json()["session"]["id"] == first.json()["session"]["id"]

    count = await db_session.execute(select(SurfSession))
    assert len(count.scalars().all()) == 1


# ── Authentification par jeton Bearer ──────────────────────────────────────


async def test_quick_accepts_a_bearer_token_without_any_cookie(
    auth_client, bearer_client, make_spot, fake_archive, archive_bundle
) -> None:
    """Le raccourci iOS n'a pas de magasin de cookies. C'est tout le sujet."""
    fake_archive(bundle=archive_bundle(SESSION_END))
    await make_spot()
    headers = await _bearer_headers(auth_client)

    assert not bearer_client.cookies

    response = await bearer_client.post(
        "/api/v1/sessions/quick",
        json={
            "lat": IN_FRONT_OF_THE_SPOT[0],
            "lon": IN_FRONT_OF_THE_SPOT[1],
            "ended_at": SESSION_END.isoformat(),
        },
        headers=headers,
    )

    assert response.status_code == 201


async def test_quick_without_any_credential_is_refused(bearer_client) -> None:
    response = await bearer_client.post("/api/v1/sessions/quick", json={})
    assert response.status_code == 401


async def test_a_revoked_bearer_token_is_refused(
    auth_client, bearer_client, make_spot, fake_archive, archive_bundle
) -> None:
    """Un JWT ne se révoque pas tout seul — c'est le registre qui le coupe.

    Sans `api_tokens`, couper le jeton d'un téléphone perdu voudrait dire
    changer `SECRET_KEY`, donc déconnecter aussi le navigateur.
    """
    fake_archive(bundle=archive_bundle(SESSION_END))
    await make_spot()

    created = await auth_client.post("/api/v1/auth/tokens", json={"name": "iPhone"})
    token_id = created.json()["id"]
    headers = {"Authorization": f"Bearer {created.json()['token']}"}

    before = await bearer_client.get("/api/v1/auth/me", headers=headers)
    assert before.status_code == 200

    revoked = await auth_client.delete(f"/api/v1/auth/tokens/{token_id}")
    assert revoked.status_code == 204

    after = await bearer_client.post(
        "/api/v1/sessions/quick",
        json={
            "lat": IN_FRONT_OF_THE_SPOT[0],
            "lon": IN_FRONT_OF_THE_SPOT[1],
            "ended_at": SESSION_END.isoformat(),
        },
        headers=headers,
    )
    assert after.status_code == 401


async def test_an_expired_bearer_token_is_refused(
    auth_client, bearer_client, db_session
) -> None:
    """L'expiration est dans le JWT **et** dans le registre : les deux mordent."""
    from app.models.api_token import ApiToken

    created = await auth_client.post("/api/v1/auth/tokens", json={"name": "iPhone"})
    headers = {"Authorization": f"Bearer {created.json()['token']}"}

    row = (
        await db_session.execute(
            select(ApiToken).where(ApiToken.id == created.json()["id"])
        )
    ).scalar_one()
    row.expires_at = datetime.now(UTC) - timedelta(days=1)
    await db_session.commit()

    response = await bearer_client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 401


async def test_the_token_value_is_returned_exactly_once(auth_client) -> None:
    """La valeur n'est pas stockée : seul le `jti` l'est."""
    created = await auth_client.post("/api/v1/auth/tokens", json={"name": "iPhone"})
    assert created.json()["token"]

    listing = await auth_client.get("/api/v1/auth/tokens")
    assert listing.status_code == 200
    assert len(listing.json()) == 1
    assert "token" not in listing.json()[0]


async def test_using_a_token_records_when(auth_client, bearer_client) -> None:
    """`last_used_at` est ce qui permet de repérer un jeton qui ne sert plus."""
    created = await auth_client.post("/api/v1/auth/tokens", json={"name": "iPhone"})
    headers = {"Authorization": f"Bearer {created.json()['token']}"}
    assert created.json()["last_used_at"] is None

    await bearer_client.get("/api/v1/auth/me", headers=headers)

    listing = await auth_client.get("/api/v1/auth/tokens")
    assert listing.json()[0]["last_used_at"] is not None


@pytest.mark.parametrize("method,path", [("post", "/api/v1/auth/tokens")])
async def test_tokens_need_a_session(client, method, path) -> None:
    response = await getattr(client, method)(path, json={"name": "x"})
    assert response.status_code == 401
