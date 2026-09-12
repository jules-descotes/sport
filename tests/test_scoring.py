"""Score de cold start, sur des conditions dont la note est évidente.

L'échelle doit surtout être *ordonnée* : une journée parfaite au-dessus d'une
journée moyenne, au-dessus d'un jour à plat. Les valeurs exactes sont un
amorçage destiné à être remplacé au lot 3 ; l'ordre, lui, ne doit jamais
s'inverser.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.services.scoring import (
    Conditions,
    TideContext,
    build_conditions,
    conditions_line,
    score_conditions,
    tide_label,
)

# Plage de la côte landaise : elle regarde plein ouest.
ONSHORE_WEST = 270.0
TS = datetime(2026, 9, 12, 8, 0, tzinfo=UTC)


def conditions(**kwargs) -> Conditions:
    base = dict(
        wave_height_m=1.4,
        wave_period_s=12.0,
        wave_direction_deg=285.0,
        wind_speed_kt=8.0,
        wind_direction_deg=90.0,
        tide_position=0.5,
        tide_trend_m_per_h=0.3,
    )
    base.update(kwargs)
    return Conditions(ts=TS, **base)


# ── Les quatre jeux de référence ───────────────────────────────────────────


def test_perfect_day_scores_five() -> None:
    """1,4 m, 12 s, houle bien orientée, offshore modéré, mi-marée montante."""
    score = score_conditions(conditions(), ONSHORE_WEST)

    assert score.level == 5
    assert score.verdict == "OUI"
    assert "vent offshore" in score.reasons


def test_flat_day_scores_one_whatever_the_wind() -> None:
    """Un jour à plat reste un jour à plat, même avec un vent parfait.

    C'est la raison pour laquelle la taille est un facteur et non un terme : une
    somme pondérée donnerait ici une note moyenne.
    """
    score = score_conditions(
        conditions(wave_height_m=0.15, wave_period_s=6.0), ONSHORE_WEST
    )

    assert score.level == 1
    assert score.verdict == "NON"
    assert score.reasons == ["mer plate"]


def test_big_onshore_day_scores_one() -> None:
    """2,8 m hachés par 22 nœuds de vent de mer : injouable, malgré la taille."""
    score = score_conditions(
        conditions(
            wave_height_m=2.8,
            wave_period_s=9.0,
            wind_speed_kt=22.0,
            wind_direction_deg=270.0,
        ),
        ONSHORE_WEST,
    )

    assert score.level == 1
    assert score.verdict == "NON"
    assert "vent onshore appuyé" in score.reasons


def test_average_day_scores_in_the_middle() -> None:
    """1,2 m, 10 s, petit vent de mer : ni un jour à rater, ni un jour à poser."""
    score = score_conditions(
        conditions(
            wave_height_m=1.2,
            wave_period_s=10.0,
            wind_speed_kt=10.0,
            wind_direction_deg=250.0,
        ),
        ONSHORE_WEST,
    )

    assert score.level == 3
    assert score.verdict == "PEUT-ÊTRE"


# ── Ordre et monotonie ─────────────────────────────────────────────────────


def test_scores_are_ordered_from_worst_to_best() -> None:
    flat = score_conditions(conditions(wave_height_m=0.15), ONSHORE_WEST)
    onshore = score_conditions(
        conditions(wind_speed_kt=20.0, wind_direction_deg=270.0), ONSHORE_WEST
    )
    average = score_conditions(
        conditions(wave_height_m=1.0, wave_period_s=8.0, wind_speed_kt=12.0,
                   wind_direction_deg=250.0),
        ONSHORE_WEST,
    )
    perfect = score_conditions(conditions(), ONSHORE_WEST)

    assert flat.value < onshore.value < average.value < perfect.value


def test_offshore_beats_onshore_all_else_equal() -> None:
    offshore = score_conditions(conditions(wind_direction_deg=90.0), ONSHORE_WEST)
    onshore = score_conditions(conditions(wind_direction_deg=270.0), ONSHORE_WEST)
    assert offshore.value > onshore.value


def test_long_period_beats_short_period_all_else_equal() -> None:
    long_period = score_conditions(conditions(wave_period_s=14.0), ONSHORE_WEST)
    short_period = score_conditions(conditions(wave_period_s=6.0), ONSHORE_WEST)
    assert long_period.value > short_period.value


def test_misaligned_swell_is_penalised() -> None:
    """Une houle de sud sur une plage ouest n'arrive tout simplement pas."""
    aligned = score_conditions(conditions(wave_direction_deg=280.0), ONSHORE_WEST)
    misaligned = score_conditions(conditions(wave_direction_deg=180.0), ONSHORE_WEST)

    assert misaligned.value < aligned.value
    assert "houle mal orientée pour le spot" in misaligned.reasons


def test_unknown_orientation_still_produces_a_score() -> None:
    """Spot ajouté à la main depuis la carte : pas d'orientation, mais une note.

    Sans orientation, seule la force du vent compte — ce qui reste vrai partout.
    """
    score = score_conditions(conditions(), onshore_dir_deg=None)

    assert 1.0 <= score.value <= 5.0
    assert "alignment_deg" not in score.components
    assert "offshore_kt" not in score.components


def test_missing_wave_height_does_not_invent_a_score() -> None:
    score = score_conditions(Conditions(ts=TS), ONSHORE_WEST)

    assert score.value == 1.0
    assert score.reasons == ["prévision de houle indisponible"]


# ── Marée ──────────────────────────────────────────────────────────────────


def test_tide_context_reads_position_and_direction_from_sea_level() -> None:
    """Le niveau de la mer suffit : ni table des marées ni source de plus."""
    levels = {
        TS + timedelta(hours=hour): value
        for hour, value in enumerate([-1.8, -1.0, 0.0, 1.0, 1.8, 1.0, 0.0])
    }
    tide = TideContext.from_levels(levels)

    assert tide.range_m(TS) == pytest.approx(3.6)
    assert tide.position(TS) == pytest.approx(0.0)  # basse mer
    assert tide.position(TS + timedelta(hours=4)) == pytest.approx(1.0)  # pleine mer
    assert tide.position(TS + timedelta(hours=2)) == pytest.approx(0.5)  # mi-marée

    rising = tide.trend_m_per_h(TS + timedelta(hours=2))
    falling = tide.trend_m_per_h(TS + timedelta(hours=5))
    assert rising is not None and rising > 0
    assert falling is not None and falling < 0


def test_negligible_tide_range_yields_no_position() -> None:
    """En Méditerranée la marée ne dit rien : mieux vaut `None` qu'un bruit."""
    levels = {TS + timedelta(hours=h): 0.01 * h for h in range(6)}
    assert TideContext.from_levels(levels).position(TS) is None


def test_mid_tide_beats_slack_water() -> None:
    mid = score_conditions(conditions(tide_position=0.5), ONSHORE_WEST)
    low = score_conditions(conditions(tide_position=0.0), ONSHORE_WEST)
    assert mid.value > low.value


@pytest.mark.parametrize(
    "trend, expected",
    [(0.3, "marée montante"), (-0.3, "marée descendante"), (0.0, "marée étale")],
)
def test_tide_label_in_french(trend: float, expected: str) -> None:
    assert tide_label(conditions(tide_trend_m_per_h=trend)) == expected


# ── Mise en forme ──────────────────────────────────────────────────────────


def test_conditions_line_reads_like_a_bulletin() -> None:
    line = conditions_line(conditions())
    assert line == "houle 1,4 m / 12 s / ONO, vent E 8 kt, marée montante"


def test_build_conditions_scores_on_the_mean_period() -> None:
    """La note porte sur la période moyenne, même si le pic est disponible.

    MFWAM ne sert pas la période de pic ; la colonne se remplira au lot 1 bis
    avec la bouée CANDHIS. Basculer alors tout seul changerait la grandeur
    notée sans prévenir, alors que le barème est calibré sur la moyenne.
    """
    built = build_conditions(
        TS, {"wave_height_m": 1.2, "wave_period_s": 7.0, "wave_peak_period_s": 13.0}
    )
    assert built.wave_period_s == 7.0
