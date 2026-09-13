"""Les critères de Jules — correspondance, fenêtres annoncées, et pondération.

Décidé le 13/09. Ce sont **ses** règles : elles priment sur l'orientation
calculée depuis le trait de côte OSM, qui ne sait rien du récif de Parlementia
ni de la fosse de la Gravière (cf. PROJET.md §7.4).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.services.scoring import (
    Conditions,
    RULE_HARD_MISS_CEILING,
    RULE_MATCH_FLOOR,
    score_conditions,
)
from app.services.spot_rules import (
    SpotRules,
    evaluate,
    group_windows,
    sector8,
    tide_phase,
    window_details,
    window_sentence,
)

NOW = datetime(2026, 9, 13, 8, 0, tzinfo=UTC)

# « Parlementia marche en houle d'ouest de 1,2 à 2,5 m, période au moins 11 s,
# vent d'est, marée montante. » La phrase de Jules, en données.
PARLEMENTIA = SpotRules(
    wave_height_min_m=1.2,
    wave_height_max_m=2.5,
    wave_period_min_s=11.0,
    swell_sectors=("O", "NO"),
    wind_sectors=("E", "SE"),
    wind_max_kt=15.0,
    tide_phases=("rising",),
    hour_min=7,
    hour_max=19,
)

GOOD = dict(
    wave_height_m=1.6,
    wave_period_s=13.0,
    wave_direction_deg=290.0,  # ONO -> secteur NO
    wind_speed_kt=6.0,
    wind_direction_deg=95.0,  # E
    tide_position=0.5,
    tide_rising=True,
    local_hour=10,
)


# ── La rose à huit points, et les phases ───────────────────────────────────


@pytest.mark.parametrize(
    "degrees,expected",
    [
        (0, "N"),
        (10, "N"),
        (44, "NE"),
        (90, "E"),
        (200, "S"),
        (225, "SO"),
        (270, "O"),
        (315, "NO"),
        (359, "N"),
    ],
)
def test_the_eight_point_rose(degrees: float, expected: str) -> None:
    """On ne saisit pas « 285° » sur une plage, on saisit « ouest »."""
    assert sector8(degrees) == expected


def test_an_unknown_direction_has_no_sector() -> None:
    assert sector8(None) is None


@pytest.mark.parametrize(
    "position,rising,expected",
    [
        (0.05, True, "low"),
        (0.95, False, "high"),
        (0.5, True, "rising"),
        (0.5, False, "falling"),
        # À pleine mer la pente est nulle : c'est la position qui nomme, pas
        # le sens — « ni montante ni descendante » n'est pas une phase.
        (0.9, None, "high"),
        (0.5, None, None),
        (None, True, None),
    ],
)
def test_the_tide_phase(position, rising, expected) -> None:
    assert tide_phase(position, rising) == expected


# ── Cinq scénarios de correspondance ───────────────────────────────────────


def test_no_rule_at_all_constrains_nothing() -> None:
    """Jules n'a rien dit : on ne lui invente pas d'avis.

    Ni correspondance ni échec — `unconstrained`. C'est ce qui empêche la note
    d'être plancher ou plafonnée sur un spot dont personne n'a décrit les
    conditions.
    """
    verdict = evaluate(SpotRules(), **GOOD)
    assert verdict.unconstrained is True
    assert verdict.matches is False
    assert verdict.hard_miss is False


def test_everything_satisfied_is_a_match() -> None:
    verdict = evaluate(PARLEMENTIA, **GOOD)
    assert verdict.matches is True
    assert verdict.hard_miss is False
    assert verdict.misses == []


def test_too_big_is_a_hard_miss() -> None:
    """Au-dessus du maximum, c'est injouable et il l'a dit."""
    verdict = evaluate(PARLEMENTIA, **{**GOOD, "wave_height_m": 3.4})
    assert verdict.matches is False
    assert verdict.hard_miss is True
    assert "plus de 2,5 m de houle" in verdict.misses


def test_too_small_is_a_soft_miss() -> None:
    """Trop petit rate la correspondance, mais ne disqualifie pas.

    La note générique sait déjà dire qu'une mer de 60 cm est faible ; la
    plafonner à 2 en plus ferait compter la même information deux fois.
    """
    verdict = evaluate(PARLEMENTIA, **{**GOOD, "wave_height_m": 0.6})
    assert verdict.matches is False
    assert verdict.hard_miss is False


def test_the_wrong_swell_sector_misses() -> None:
    verdict = evaluate(PARLEMENTIA, **{**GOOD, "wave_direction_deg": 180.0})
    assert verdict.matches is False
    assert verdict.hard_miss is False
    assert "houle de S" in verdict.misses


def test_the_wrong_tide_phase_misses() -> None:
    verdict = evaluate(
        PARLEMENTIA, **{**GOOD, "tide_position": 0.5, "tide_rising": False}
    )
    assert verdict.matches is False
    assert "marée descendante" in verdict.misses


def test_outside_the_preferred_hours_misses() -> None:
    verdict = evaluate(PARLEMENTIA, **{**GOOD, "local_hour": 5})
    assert verdict.matches is False
    assert "avant 7 h" in verdict.misses


def test_missing_data_never_fails_a_criterion() -> None:
    """Une colonne absente ne doit pas faire taire toutes les annonces.

    Si Open-Meteo cesse un jour de servir la période, traiter l'absence comme
    un échec supprimerait toutes les correspondances — et le silence se
    lirait comme « rien ne marche », ce qui est faux.
    """
    verdict = evaluate(PARLEMENTIA, **{**GOOD, "wave_period_s": None})
    assert verdict.matches is True


# ── La pondération de la note (règle C.4) ──────────────────────────────────


def _conditions(**overrides) -> Conditions:
    values = {
        "wave_height_m": 1.6,
        "wave_period_s": 13.0,
        "wave_direction_deg": 290.0,
        "wind_speed_kt": 6.0,
        "wind_direction_deg": 95.0,
        "tide_position": 0.5,
        "tide_trend_m_per_h": 0.3,
        **overrides,
    }
    return Conditions(ts=NOW, **values)


def test_a_matching_slot_never_scores_below_three() -> None:
    """Il a décrit ce spot ; notre géométrie n'a pas à le contredire.

    Le spot regarde ici plein sud (`onshore_dir_deg=180`), donc une houle
    d'ouest lui arrive de travers et l'alignement générique l'écraserait. Ses
    secteurs disent le contraire, et ce sont eux qui comptent.
    """
    score = score_conditions(_conditions(), 180.0, PARLEMENTIA, local_hour=10)
    assert score.value >= RULE_MATCH_FLOOR
    assert "correspond à tes critères" in score.reasons


def test_a_hard_miss_never_scores_above_two() -> None:
    """Inutile de trouver des qualités de période à une mer injouable."""
    conditions = _conditions(wave_height_m=3.4)
    score = score_conditions(conditions, 280.0, PARLEMENTIA, local_hour=10)
    assert score.value <= RULE_HARD_MISS_CEILING
    assert score.reasons[0] == "plus de 2,5 m de houle"


def test_a_soft_miss_leaves_the_generic_score_alone() -> None:
    """Ni plancher ni plafond : le calcul générique garde la main.

    Mer parfaite, mais à 5 h du matin — hors des heures préférées. Ce n'est
    pas une correspondance, donc pas de plancher ; ce n'est pas non plus un
    critère dur, donc pas de plafond : la note reste celle de la mer. La
    plafonner à 2 parce que Jules préfère surfer après 7 h reviendrait à
    confondre « il n'ira pas » et « c'est mauvais ».
    """
    score = score_conditions(_conditions(), 280.0, PARLEMENTIA, local_hour=5)

    assert "correspond à tes critères" not in score.reasons
    assert score.value > RULE_HARD_MISS_CEILING
    assert score.components["rule_match"] == 0.0


def test_the_sectors_replace_the_computed_orientation() -> None:
    """Son *a priori* prime sur le nôtre, et il le remplace entièrement.

    Même créneau, même spot : sans règles, l'orientation calculée juge une
    houle d'ouest sur une côte qui regarde le sud et écrase la note. Avec ses
    secteurs, elle est acceptée.
    """
    conditions = _conditions()
    generic = score_conditions(conditions, 180.0)
    guided = score_conditions(conditions, 180.0, PARLEMENTIA, local_hour=10)

    assert generic.components["alignment"] < 0.5
    assert guided.components["alignment"] == 1.0
    assert guided.value > generic.value


def test_without_rules_nothing_changes() -> None:
    """Le calcul du lot 1, intact. C'est la garantie de non-régression."""
    conditions = _conditions()
    assert score_conditions(conditions, 280.0).value == score_conditions(
        conditions, 280.0, SpotRules()
    ).value


# ── Les fenêtres annoncées ─────────────────────────────────────────────────


def _hour(offset: int, score: float = 3.5) -> tuple[datetime, dict]:
    return (
        NOW + timedelta(hours=offset),
        {
            "score": score,
            "wave_height_m": 1.6,
            "wave_period_s": 13.0,
            "wave_direction_deg": 290.0,
            "wind_speed_kt": 6.0,
            "wind_direction_deg": 95.0,
            "tide_phase": "rising",
        },
    )


def test_consecutive_hours_become_one_window() -> None:
    """« dim. 10 h, dim. 11 h, dim. 12 h » est la même chose écrite trois fois."""
    windows = group_windows(1, [_hour(0), _hour(1), _hour(2)])
    assert len(windows) == 1
    assert windows[0].start == NOW
    # La fenêtre va jusqu'à la **fin** du dernier créneau : un créneau de 10 h
    # couvre l'heure de 10 h à 11 h.
    assert windows[0].end == NOW + timedelta(hours=3)


def test_a_single_missed_hour_does_not_split_the_window() -> None:
    """Une heure qui rate de peu au milieu d'une bonne matinée."""
    windows = group_windows(1, [_hour(0), _hour(1), _hour(3)])
    assert len(windows) == 1


def test_a_real_gap_splits_the_window() -> None:
    """Matin et soir sont deux occasions, pas une longue journée."""
    windows = group_windows(1, [_hour(0), _hour(1), _hour(9), _hour(10)])
    assert len(windows) == 2


def test_the_window_keeps_the_numbers_of_its_best_hour() -> None:
    """Ce qu'on affiche est le sommet, pas une moyenne — on y va pour ça."""
    windows = group_windows(
        1, [_hour(0, score=2.8), _hour(1, score=4.4), _hour(2, score=3.1)]
    )
    assert windows[0].best_ts == NOW + timedelta(hours=1)
    assert windows[0].best_score == 4.4


def test_the_sentence_stays_in_the_conditional() -> None:
    """Des critères larges contre une prévision, ce n'est pas une promesse."""
    window = group_windows(1, [_hour(2), _hour(3), _hour(4)])[0]
    sentence = window_sentence(window, "Parlementia", NOW, "Europe/Paris")

    assert sentence.startswith("Parlementia devrait marcher")
    assert "auj." in sentence
    assert window_details(window) == "1,6 m / 13 s / ONO · vent E 6 kt · marée montante"
