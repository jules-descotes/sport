"""Le coefficient de marée — la formule, les pleines mers, le « ≈ ».

Les cas sont **fixés** : on part d'une hauteur de pleine mer connue et on
vérifie le coefficient à un point près. C'est la seule façon de tester une
formule dont la vérité est publiée ailleurs (l'annuaire SHOM) — la confronter
aux vraies valeurs est le travail de `scripts/check_tide_coefficient.py`, dont
le résultat est consigné dans `docs/COEFFICIENT-MAREE.md`.
"""
from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from app.models.forecast import Forecast
from app.services.tide_coefficient import (
    CALIBRATED,
    MEASURED_MAX_GAP,
    REFERENCE_MODEL,
    TideMark,
    with_calibration,
    MAX_COEFFICIENT,
    MIN_COEFFICIENT,
    MIN_WINDOW_HOURS,
    UNIT_HEIGHT_M,
    coefficient_from_height,
    ensure_reference_spot,
    high_tides,
    marks_from_levels,
    mean_level,
    nearest_mark,
)

NOW = datetime(2026, 9, 13, 0, 0, tzinfo=UTC)

# Période de la marée semi-diurne — 12 h 25 min, le cycle lunaire.
TIDE_PERIOD_H = 12 + 25 / 60


def height_for(coefficient: int, datum: float = 0.0) -> float:
    """La hauteur de pleine mer qui donne exactement ce coefficient."""
    return datum + coefficient / 100.0 * UNIT_HEIGHT_M


def series(
    amplitude_m: float,
    hours: int = 48,
    *,
    start: datetime = NOW,
    datum: float = 0.0,
    step_min: int = 60,
) -> list[tuple[datetime, float]]:
    """Une marée semi-diurne synthétique, échantillonnée à l'heure.

    `amplitude_m` est la hauteur de pleine mer au-dessus du niveau moyen : le
    sommet de la sinusoïde vaut donc `datum + amplitude_m`, ce qui est
    exactement le `H_PM` de la formule.
    """
    points: list[tuple[datetime, float]] = []
    for index in range(hours * 60 // step_min):
        ts = start + timedelta(minutes=index * step_min)
        phase = 2 * math.pi * (index * step_min / 60) / TIDE_PERIOD_H
        points.append((ts, datum + amplitude_m * math.cos(phase)))
    return points


# ── La formule ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("expected", [45, 70, 95, 110])
def test_three_known_high_tides_give_their_coefficient(expected: int) -> None:
    """C = (H_PM − N0) / 3,05 × 100, à un point près."""
    value, out_of_range = coefficient_from_height(height_for(expected), 0.0)
    assert abs(value - expected) <= 1
    assert out_of_range is False


def test_the_datum_is_subtracted_not_ignored() -> None:
    """Un modèle décalé de 10 cm ne doit pas valoir trois points pour toujours.

    C'est toute la raison d'être du niveau moyen glissant : Open-Meteo annonce
    un niveau relatif au niveau moyen, mais un biais constant du modèle se
    transformerait sinon en erreur permanente de coefficient.
    """
    biased = height_for(95, datum=0.10)
    assert coefficient_from_height(biased, 0.10)[0] == 95
    # Sans soustraction du datum, on lirait trois points de trop.
    assert coefficient_from_height(biased, 0.0)[0] == 98


def test_a_value_out_of_the_shom_scale_is_clamped_and_flagged() -> None:
    """Hors de 20–120, on n'est plus dans le domaine de la formule."""
    value, out_of_range = coefficient_from_height(height_for(150), 0.0)
    assert value == MAX_COEFFICIENT
    assert out_of_range is True

    value, out_of_range = coefficient_from_height(height_for(5), 0.0)
    assert value == MIN_COEFFICIENT
    assert out_of_range is True


# ── Les pleines mers ───────────────────────────────────────────────────────


def test_a_day_of_levels_yields_its_high_tides() -> None:
    """Deux pleines mers par jour, à peu près douze heures d'écart."""
    peaks = high_tides(series(2.9, hours=48))
    # 48 h de marée semi-diurne : trois sommets pleins, le quatrième tombe
    # hors de la fenêtre.
    assert 3 <= len(peaks) <= 4
    gaps = [
        (b[0] - a[0]).total_seconds() / 3600 for a, b in zip(peaks, peaks[1:])
    ]
    assert all(11 <= gap <= 14 for gap in gaps)


def test_the_edges_of_the_window_are_never_peaks() -> None:
    """Un bord n'est pas un sommet : on ne sait pas ce qu'il y a juste après."""
    levels = [
        (NOW, 3.0),
        (NOW + timedelta(hours=1), 2.0),
        (NOW + timedelta(hours=2), 1.0),
    ]
    assert high_tides(levels) == []


def test_a_flat_slack_counts_for_one_high_tide() -> None:
    """Deux heures au même niveau à l'étale, une seule pleine mer.

    Et elle tombe **entre** les deux heures du palier : c'est l'interpolation
    qui le dit, et c'est la bonne réponse — le sommet d'un plateau est au
    milieu, pas à son bord gauche.
    """
    levels = [
        (NOW, 1.0),
        (NOW + timedelta(hours=1), 2.9),
        (NOW + timedelta(hours=2), 2.9),
        (NOW + timedelta(hours=3), 1.0),
    ]
    peaks = high_tides(levels)
    assert len(peaks) == 1
    assert NOW + timedelta(hours=1) <= peaks[0][0] <= NOW + timedelta(hours=2)


def test_the_crest_is_interpolated_not_sampled() -> None:
    """L'échantillon horaire tombe à côté du sommet, et ça coûte trois points.

    Une marée a une période de 12 h 25 : la valeur relevée à l'heure pleine
    est jusqu'à 3 % sous le vrai sommet. Sans interpolation, le coefficient
    serait systématiquement trop bas — un biais, pas du bruit.
    """
    amplitude = height_for(95)
    # Sommet à mi-chemin entre deux heures pleines : le cas le plus
    # défavorable de la grille horaire.
    levels = [
        (
            NOW + timedelta(hours=hour),
            amplitude * math.cos(2 * math.pi * (hour + 0.5) / TIDE_PERIOD_H),
        )
        for hour in range(26)
    ]

    sampled = max(level for _, level in levels)
    crest = max(level for _, level in high_tides(levels))

    assert crest > sampled
    assert crest == pytest.approx(amplitude, abs=0.01)


def test_marks_carry_the_coefficient_of_each_high_tide() -> None:
    marks = marks_from_levels(
        series(height_for(95), hours=26), 0.0, window_hours=MIN_WINDOW_HOURS
    )
    assert marks
    assert all(abs(mark.value - 95) <= 1 for mark in marks)
    assert all(mark.approximate is False for mark in marks)


def test_a_short_reference_window_flags_the_coefficient() -> None:
    """Les premières semaines, le niveau moyen n'est pas encore établi."""
    marks = marks_from_levels(
        series(height_for(95), hours=26), 0.0, window_hours=24
    )
    assert marks
    assert all(mark.approximate for mark in marks)
    assert marks[0].reason == "fenêtre de référence trop courte"


def test_the_nearest_high_tide_qualifies_an_hour() -> None:
    """« Ce matin c'était 95 » désigne la marée du matin, pas celle du soir."""
    marks = marks_from_levels(
        series(height_for(95), hours=48), 0.0, window_hours=MIN_WINDOW_HOURS
    )
    first, second = marks[0], marks[1]

    # Une heure juste après la première pleine mer lui appartient.
    assert nearest_mark(marks, first.ts + timedelta(hours=1)) is first
    # Une heure juste avant la seconde appartient à la seconde.
    assert nearest_mark(marks, second.ts - timedelta(hours=1)) is second


def test_no_high_tide_means_no_coefficient() -> None:
    """Pas de donnée, pas de chiffre — jamais un zéro, qui se lirait morte-eau."""
    assert nearest_mark([], NOW) is None
    assert marks_from_levels([], 0.0, window_hours=MIN_WINDOW_HOURS) == []


# ── Le niveau moyen, lu en base ────────────────────────────────────────────


async def _write_levels(db_session, spot, levels) -> None:
    """Des lignes de niveau marin, telles que les écrit l'ingestion de Brest."""
    run_ts = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    for ts, level in levels:
        db_session.add(
            Forecast(
                spot_id=spot.id,
                ts=ts,
                run_ts=run_ts,
                source="open-meteo",
                model=REFERENCE_MODEL,
                sea_level_m=round(level, 4),
                fetched_at=run_ts,
            )
        )
    await db_session.commit()


async def test_mean_level_measures_the_model_bias(db_session) -> None:
    """Le datum est mesuré, pas supposé : c'est ce qui retire le biais."""
    reference = await ensure_reference_spot(db_session)

    start = datetime.now(UTC) - timedelta(days=10)
    await _write_levels(
        db_session, reference, series(2.9, hours=240, start=start, datum=0.25)
    )

    datum, window_hours = await mean_level(db_session, reference.id)

    # Dix jours de sinusoïde autour de 0,25 m : la moyenne y revient.
    assert datum == pytest.approx(0.25, abs=0.05)
    assert window_hours >= MIN_WINDOW_HOURS


async def test_mean_level_without_data_falls_back_to_zero(
    db_session,
) -> None:
    """Sans historique, on retombe sur le zéro théorique d'Open-Meteo.

    Et la fenêtre vide fait passer tous les coefficients en « ≈ » : on ne sait
    pas encore de quoi le modèle est capable.
    """
    reference = await ensure_reference_spot(db_session)
    datum, window_hours = await mean_level(db_session, reference.id)
    assert datum == 0.0
    assert window_hours == 0


# ── Ce que vaut le calcul face au SHOM ─────────────────────────────────────


def test_the_measured_gap_adds_its_own_reservation() -> None:
    """Six points d'écart contre l'annuaire : le coefficient part avec sa réserve.

    La campagne du 13/09 est une mesure extérieure, datée
    (`docs/COEFFICIENT-MAREE.md`) : elle ne change pas le calcul, elle change
    ce qu'on ose en dire.
    """
    mark = TideMark(ts=NOW, height_m=2.9, value=95, approximate=False)
    calibrated = with_calibration(mark)

    assert calibrated.value == 95
    if CALIBRATED:
        assert calibrated.approximate is False
    else:
        assert calibrated.approximate is True
        assert str(MEASURED_MAX_GAP) in (calibrated.reason or "")


def test_a_more_precise_reservation_wins() -> None:
    """« Fenêtre trop courte » est plus actionnable que « écart mesuré »."""
    mark = TideMark(
        ts=NOW,
        height_m=2.9,
        value=95,
        approximate=True,
        reason="fenêtre de référence trop courte",
    )
    assert with_calibration(mark).reason == "fenêtre de référence trop courte"
