"""Le tableau horaire de l'écran Surf, et l'énergie de houle qui en est la ligne neuve.

L'écran Surf est passé d'une grille 5 j × 8 créneaux à un tableau **heure par
heure** sur cinq jours (décidé le 13/09). Ce qui se teste ici :

- l'**énergie** (feature 9 du registre) sur des valeurs calculées à la main ;
- le **pas horaire** : cent vingt points au lieu de quarante, et le pas de
  trois heures qui sert encore l'écran Jour ;
- le **lever et le coucher** rendus par journée, pour griser la nuit d'un trait ;
- le **détail d'un créneau**, seul endroit où les directions sont chiffrées, et
  son écart avec le run de la veille au soir.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.services.geo import wave_energy, wave_energy_kj
from tests.conftest import ONSHORE_WEST


# ── Énergie de la houle ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("height_m", "period_s", "expected_kj"),
    [
        # 0,49 × H² × T — vérifié à la main, trois ordres de grandeur.
        # Petite mer du vent de fin d'été : ça ne porte rien.
        (0.5, 8.0, 0.98),
        # La session type de la côte landaise.
        (1.0, 10.0, 4.90),
        # Houle d'ouest de mars : vingt-quatre fois l'énergie de la première.
        (2.0, 12.0, 23.52),
    ],
)
def test_wave_energy_kj_on_known_values(height_m, period_s, expected_kj) -> None:
    assert wave_energy_kj(height_m, period_s) == pytest.approx(expected_kj, abs=0.01)


def test_energy_separates_two_waves_of_the_same_height() -> None:
    """C'est toute la raison d'être de la ligne : un mètre n'est pas un mètre.

    À 15 s de période, un mètre porte plus de deux fois l'énergie du même
    mètre à 7 s — et la hauteur seule ne le dit pas.
    """
    short = wave_energy_kj(1.0, 7.0)
    long = wave_energy_kj(1.0, 15.0)

    assert long / short == pytest.approx(15.0 / 7.0)


def test_raw_feature_keeps_its_shape() -> None:
    """`wave_energy` reste la forme brute du registre (∝ H²T).

    C'est elle qui entre dans le vecteur de features, jamais la version mise à
    l'échelle : changer la constante d'affichage ne doit pas déplacer les
    features d'un historique d'apprentissage.
    """
    assert wave_energy(2.0, 12.0) == pytest.approx(48.0)
    assert wave_energy_kj(2.0, 12.0) == pytest.approx(0.49 * wave_energy(2.0, 12.0))


# ── Tableau horaire ────────────────────────────────────────────────────────


async def test_forecast_is_hourly_by_default(auth_client, make_spot, make_forecast):
    """Le tableau de Surf est horaire : une colonne par heure, pas une sur trois."""
    spot = await make_spot()
    start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    await make_forecast(spot, start=start, hours=72)

    response = await auth_client.get(
        f"/api/v1/spots/{spot.slug}/forecast", params={"days": 3, "step_hours": 1}
    )

    assert response.status_code == 200
    points = response.json()["points"]
    hours = {datetime.fromisoformat(point["ts"]).hour for point in points}
    # Les vingt-quatre heures sont représentées, pas seulement 0/3/6/9…
    assert len(hours) == 24
    assert len(points) > 40


async def test_the_table_starts_at_the_beginning_of_the_day(
    auth_client, make_spot, make_forecast
):
    """Le tableau de Surf montre **la matinée**, pas seulement ce qui reste.

    Il s'ouvrait à l'heure courante : à 14 h, les prévisions de 6 h et de 9 h
    étaient en base et visibles nulle part. Ce sont pourtant celles qu'on relit
    le soir pour comprendre la session du matin — et celles sur lesquelles
    pointent les créneaux de la bande de l'écran Jour.
    """
    zone = ZoneInfo("Europe/Paris")
    now = datetime.now(UTC)
    day_start = (
        now.astimezone(zone)
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .astimezone(UTC)
    )

    spot = await make_spot()
    await make_forecast(spot, start=day_start, hours=96, run_ts=day_start)

    response = await auth_client.get(
        f"/api/v1/spots/{spot.slug}/forecast", params={"days": 3, "step_hours": 1}
    )

    points = response.json()["points"]
    first = datetime.fromisoformat(points[0]["ts"])
    assert first <= day_start

    # Et la matinée ne se paie pas sur la fin de la prévision : trois jours
    # demandés, trois jours servis à partir de maintenant.
    last = datetime.fromisoformat(points[-1]["ts"])
    assert last >= now + timedelta(days=2, hours=12)


async def test_three_hour_step_still_serves_the_day_screen(
    auth_client, make_spot, make_forecast
):
    """L'écran Jour résume en huit créneaux : le pas de trois heures reste."""
    spot = await make_spot()
    start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    await make_forecast(spot, start=start, hours=48)

    response = await auth_client.get(
        f"/api/v1/spots/{spot.slug}/forecast", params={"days": 2, "step_hours": 3}
    )

    points = response.json()["points"]
    assert all(datetime.fromisoformat(point["ts"]).hour % 3 == 0 for point in points)


async def test_every_point_carries_energy_and_alignment(
    auth_client, make_spot, make_forecast
):
    spot = await make_spot()
    await make_forecast(spot, hours=24, wave_height_m=1.4, wave_period_s=12.0)

    response = await auth_client.get(f"/api/v1/spots/{spot.slug}/forecast")
    point = response.json()["points"][0]

    assert point["wave_energy_kj"] == pytest.approx(0.49 * 1.4 * 1.4 * 12.0, abs=0.1)
    # Houle de 285°, spot orienté 270° : quinze degrés d'écart.
    assert point["swell_alignment_deg"] == pytest.approx(15.0, abs=0.1)


async def test_sun_is_rendered_once_per_day(auth_client, make_spot, make_forecast):
    """Le tableau grise la nuit d'un trait : il lui faut les deux bornes, pas
    un booléen par heure."""
    spot = await make_spot()
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    await make_forecast(spot, start=start, hours=72)

    body = (
        await auth_client.get(
            f"/api/v1/spots/{spot.slug}/forecast", params={"days": 3}
        )
    ).json()

    days = {entry["day"] for entry in body["sun"]}
    rendered = {point["ts"][:10] for point in body["points"]}
    assert days == rendered
    assert all(
        entry["sunrise"] is not None and entry["sunset"] is not None
        for entry in body["sun"]
    )


async def test_night_slots_are_rendered_but_flagged(
    auth_client, make_spot, make_forecast
):
    """Une colonne manquante décalerait toute la lecture : la nuit s'éteint,
    elle ne disparaît pas."""
    spot = await make_spot()
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    await make_forecast(spot, start=start, hours=48)

    points = (
        await auth_client.get(f"/api/v1/spots/{spot.slug}/forecast")
    ).json()["points"]

    assert any(point["daylight"] is False for point in points)
    assert any(point["daylight"] is True for point in points)


async def test_secondary_swell_is_rendered_when_present(
    auth_client, make_spot, make_forecast, db_session
):
    """La ligne repliable du second train : une houle croisée explique une mer
    désordonnée que la hauteur totale ne raconte pas."""
    from sqlalchemy import select

    from app.models.forecast import Forecast

    spot = await make_spot()
    await make_forecast(spot, hours=6)

    rows = (
        await db_session.execute(select(Forecast).where(Forecast.spot_id == spot.id))
    ).scalars().all()
    for row in rows:
        row.secondary_swell_height_m = 0.6
        row.secondary_swell_direction_deg = 200.0
        row.secondary_swell_period_s = 6.0
    await db_session.commit()

    point = (
        await auth_client.get(f"/api/v1/spots/{spot.slug}/forecast")
    ).json()["points"][0]

    assert point["secondary_swell_height_m"] == 0.6
    assert point["secondary_swell_direction_deg"] == 200.0


# ── Détail d'un créneau ────────────────────────────────────────────────────


async def test_slot_detail_spells_out_the_directions(
    auth_client, make_spot, make_forecast
):
    """C'est le seul endroit du produit où une direction est un nombre."""
    spot = await make_spot(onshore_dir_deg=ONSHORE_WEST)
    start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    await make_forecast(spot, start=start, hours=24)

    target = start + timedelta(hours=3)
    response = await auth_client.get(
        f"/api/v1/spots/{spot.slug}/slot", params={"ts": target.isoformat()}
    )

    assert response.status_code == 200
    body = response.json()
    # Houle 285° = ONO, vent 90° = E, spot regardant vers l'ouest.
    assert body["wave_direction_label"] == "ONO"
    assert body["wind_direction_label"] == "E"
    assert body["onshore_direction_label"] == "O"
    assert body["point"]["swell_alignment_deg"] == pytest.approx(15.0, abs=0.1)
    # Vent d'est sur une côte ouest : offshore franc, donc positif.
    assert body["point"]["wind_offshore_kt"] > 0


async def test_slot_detail_refuses_an_hour_it_has_no_forecast_for(
    auth_client, make_spot, make_forecast
):
    spot = await make_spot()
    await make_forecast(spot, hours=6)

    far = datetime.now(UTC) + timedelta(days=30)
    response = await auth_client.get(
        f"/api/v1/spots/{spot.slug}/slot", params={"ts": far.isoformat()}
    )

    assert response.status_code == 404


async def test_slot_detail_reports_the_change_since_last_evening(
    auth_client, make_spot, make_forecast
):
    """Le bénéfice visible de `run_ts` : « annoncé 40 cm plus haut qu'hier soir ».

    Sans historisation des runs, cette section n'existerait pas — la passe du
    matin aurait écrasé celle de la veille.
    """
    spot = await make_spot()
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    target = now + timedelta(hours=6)

    # Le run de la veille, bien avant 20 h locale d'hier.
    await make_forecast(
        spot,
        start=now,
        hours=24,
        run_ts=now - timedelta(days=1, hours=12),
        wave_height_m=1.0,
        wave_period_s=10.0,
    )
    # Le run de ce matin : quarante centimètres de plus.
    await make_forecast(
        spot,
        start=now,
        hours=24,
        run_ts=now,
        wave_height_m=1.4,
        wave_period_s=11.0,
    )

    body = (
        await auth_client.get(
            f"/api/v1/spots/{spot.slug}/slot", params={"ts": target.isoformat()}
        )
    ).json()

    assert body["previous_run_ts"] is not None
    assert body["delta"]["wave_height_m"] == pytest.approx(0.4, abs=0.001)
    assert body["delta"]["wave_period_s"] == pytest.approx(1.0, abs=0.001)


async def test_slot_detail_serves_the_latest_run(
    auth_client, make_spot, make_forecast
):
    """Une heure porte autant de lignes que de passes : on sert la dernière."""
    spot = await make_spot()
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    target = now + timedelta(hours=2)

    await make_forecast(
        spot, start=now, hours=12, run_ts=now - timedelta(hours=6), wave_height_m=0.8
    )
    await make_forecast(spot, start=now, hours=12, run_ts=now, wave_height_m=1.9)

    body = (
        await auth_client.get(
            f"/api/v1/spots/{spot.slug}/slot", params={"ts": target.isoformat()}
        )
    ).json()

    assert body["point"]["wave_height_m"] == 1.9


async def test_slot_detail_never_ingests(
    auth_client, make_spot, make_forecast, monkeypatch
):
    """Rafraîchir ici rendrait un détail qui ne correspondrait plus à la
    cellule qu'on vient de toucher."""
    from app.api.routes import spots as spots_routes

    calls: list[int] = []

    async def _boom(db, spot_list):
        calls.append(len(spot_list))
        return []

    monkeypatch.setattr(spots_routes, "ensure_fresh", _boom)

    spot = await make_spot()
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    await make_forecast(spot, start=now, hours=12)

    await auth_client.get(
        f"/api/v1/spots/{spot.slug}/slot", params={"ts": now.isoformat()}
    )

    assert calls == []
