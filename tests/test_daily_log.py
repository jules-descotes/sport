"""Journal quotidien : les seuls exemples négatifs que le modèle verra jamais."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select

from app.models.daily_log import DailyLog


async def test_today_is_unanswered_before_the_first_swipe(auth_client) -> None:
    response = await auth_client.get("/api/v1/daily-log/today")

    assert response.status_code == 200
    body = response.json()
    assert body["answered"] is False
    assert body["entry"] is None


async def test_swipe_records_the_day(auth_client) -> None:
    response = await auth_client.post(
        "/api/v1/daily-log", json={"status": "surfed"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "surfed"

    today = await auth_client.get("/api/v1/daily-log/today")
    assert today.json()["answered"] is True


async def test_watched_and_passed_records_the_spot_and_the_reason(
    auth_client, make_spot
) -> None:
    """C'est là que l'information est la plus utile au modèle."""
    spot = await make_spot()

    response = await auth_client.post(
        "/api/v1/daily-log",
        json={
            "status": "watched_and_passed",
            "spot_id": spot.id,
            "reason": "trop de monde, vent qui se lève",
        },
    )

    body = response.json()
    assert body["status"] == "watched_and_passed"
    assert body["spot_id"] == spot.id
    assert body["reason"].startswith("trop de monde")


async def test_double_tap_does_not_create_two_rows(auth_client, db_session) -> None:
    """Un double tap sur le parking ne doit pas créer deux lignes."""
    await auth_client.post("/api/v1/daily-log", json={"status": "surfed"})
    await auth_client.post("/api/v1/daily-log", json={"status": "surfed"})

    count = (
        await db_session.execute(select(func.count()).select_from(DailyLog))
    ).scalar_one()
    assert count == 1


async def test_a_wrong_answer_can_be_corrected(auth_client) -> None:
    """Se tromper de bouton doit se rattraper d'un autre tap."""
    await auth_client.post("/api/v1/daily-log", json={"status": "not_watched"})

    response = await auth_client.post("/api/v1/daily-log", json={"status": "surfed"})

    assert response.json()["status"] == "surfed"


async def test_a_past_day_can_be_filled_in(auth_client) -> None:
    """Le jour est une date locale : on peut rattraper hier."""
    response = await auth_client.post(
        "/api/v1/daily-log", json={"day": "2026-09-10", "status": "watched_and_passed"}
    )

    assert response.json()["day"] == "2026-09-10"

    today = await auth_client.get("/api/v1/daily-log/today")
    assert today.json()["answered"] is False


async def test_unknown_status_is_rejected(auth_client) -> None:
    response = await auth_client.post(
        "/api/v1/daily-log", json={"status": "je-sais-pas"}
    )
    assert response.status_code == 422


async def test_unknown_spot_is_rejected(auth_client) -> None:
    response = await auth_client.post(
        "/api/v1/daily-log", json={"status": "watched_and_passed", "spot_id": 9999}
    )
    assert response.status_code == 404


async def test_history_is_listed_most_recent_first(auth_client) -> None:
    for day, status_value in [
        ("2026-09-08", "surfed"),
        ("2026-09-09", "not_watched"),
        ("2026-09-10", "watched_and_passed"),
    ]:
        await auth_client.post(
            "/api/v1/daily-log", json={"day": day, "status": status_value}
        )

    response = await auth_client.get(
        "/api/v1/daily-log", params={"since": "2026-09-09"}
    )

    body = response.json()
    assert [entry["day"] for entry in body] == ["2026-09-10", "2026-09-09"]


async def test_daily_log_requires_authentication(client) -> None:
    assert (await client.post("/api/v1/daily-log", json={"status": "surfed"})).status_code == 401
    assert (await client.get("/api/v1/daily-log/today")).status_code == 401


async def test_today_uses_the_profile_timezone(auth_client, user, db_session) -> None:
    """À 1 h du matin à Paris, UTC est encore la veille."""
    user.profile.timezone = "Pacific/Auckland"
    await db_session.commit()

    response = await auth_client.get("/api/v1/daily-log/today")

    from datetime import datetime
    from zoneinfo import ZoneInfo

    expected = datetime.now(ZoneInfo("Pacific/Auckland")).date()
    assert response.json()["day"] == expected.isoformat()
    assert isinstance(date.fromisoformat(response.json()["day"]), date)
