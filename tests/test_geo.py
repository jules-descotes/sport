"""Géométrie de côte et d'angles.

Les cas d'orientation sont construits sur la convention OSM : une ligne
`natural=coastline` est tracée **terre à gauche, mer à droite**. La normale
sortante — donc `onshore_dir_deg` — est le cap du segment + 90°.
"""
from __future__ import annotations

import pytest

from app.services.geo import (
    angular_diff_deg,
    bearing_deg,
    bounding_box,
    compass_label,
    haversine_m,
    nearest_coast_bearing,
    offshore_component_kt,
    onshore_from_coast_bearing,
    point_to_segment_m,
    swell_alignment_deg,
    wave_energy,
)


def test_haversine_matches_known_distance() -> None:
    """Hossegor → Biarritz : une trentaine de kilomètres à vol d'oiseau."""
    distance_km = haversine_m(43.664, -1.440, 43.483, -1.559) / 1000.0
    assert 21.0 < distance_km < 24.0


@pytest.mark.parametrize(
    "lat2, lon2, expected",
    [
        (44.0, -1.44, 0.0),  # plein nord
        (43.664, -1.0, 90.0),  # plein est
        (43.0, -1.44, 180.0),  # plein sud
        (43.664, -2.0, 270.0),  # plein ouest
    ],
)
def test_bearing_cardinal_directions(lat2: float, lon2: float, expected: float) -> None:
    assert bearing_deg(43.664, -1.44, lat2, lon2) == pytest.approx(expected, abs=0.5)


def test_angular_diff_wraps_around_north() -> None:
    assert angular_diff_deg(350.0, 10.0) == pytest.approx(20.0)
    assert angular_diff_deg(10.0, 350.0) == pytest.approx(20.0)
    assert angular_diff_deg(0.0, 180.0) == pytest.approx(180.0)


# ── Orientation de côte : trois cas connus ─────────────────────────────────
#
# Chaque trait de côte est une ligne droite, tracée dans le sens imposé par
# OSM. Le spot est posé côté mer, à quelques centaines de mètres.

COTE_LANDAISE = [(43.70, -1.44), (43.66, -1.44), (43.62, -1.44)]
"""Ligne nord → sud, terre à l'est : une plage qui regarde plein ouest."""

COTE_NORMANDE = [(49.34, -0.60), (49.34, -0.50), (49.34, -0.40)]
"""Ligne ouest → est, terre au nord : une plage qui regarde plein sud."""

COTE_MEDITERRANEENNE = [(43.20, 5.50), (43.24, 5.50), (43.28, 5.50)]
"""Ligne sud → nord, terre à l'ouest : une plage qui regarde plein est."""


@pytest.mark.parametrize(
    "way, spot_lat, spot_lon, expected_coast, expected_onshore",
    [
        (COTE_LANDAISE, 43.66, -1.45, 180.0, 270.0),
        (COTE_NORMANDE, 49.335, -0.50, 90.0, 180.0),
        (COTE_MEDITERRANEENNE, 43.24, 5.51, 0.0, 90.0),
    ],
)
def test_coast_orientation_on_known_cases(
    way: list[tuple[float, float]],
    spot_lat: float,
    spot_lon: float,
    expected_coast: float,
    expected_onshore: float,
) -> None:
    found = nearest_coast_bearing(spot_lat, spot_lon, [way])
    assert found is not None

    coast_bearing, distance_m = found
    assert coast_bearing % 360 == pytest.approx(expected_coast, abs=1.0)
    assert onshore_from_coast_bearing(coast_bearing) == pytest.approx(
        expected_onshore, abs=1.0
    )
    # Le spot est à moins d'un kilomètre du trait de côte retenu.
    assert distance_m < 1200.0


def test_nearest_coast_picks_the_closest_of_several_coastlines() -> None:
    """Deux côtes dans la zone : c'est bien la plus proche qui décide."""
    found = nearest_coast_bearing(43.66, -1.45, [COTE_MEDITERRANEENNE, COTE_LANDAISE])
    assert found is not None
    assert onshore_from_coast_bearing(found[0]) == pytest.approx(270.0, abs=1.0)


def test_no_coastline_within_range_returns_none() -> None:
    """Spot de rivière ou piscine à vagues : pas d'orientation inventée.

    Mieux vaut une orientation absente qu'une orientation fausse — `scoring.py`
    sait noter sans, sur la hauteur et la période seules.
    """
    assert nearest_coast_bearing(45.76, 4.83, [COTE_LANDAISE]) is None


def test_point_to_segment_projects_inside_the_segment() -> None:
    distance_m, t = point_to_segment_m(43.66, -1.45, (43.70, -1.44), (43.62, -1.44))
    assert 0.0 < t < 1.0
    assert distance_m == pytest.approx(805.0, rel=0.05)


# ── Vent et houle ──────────────────────────────────────────────────────────


def test_offshore_component_is_positive_for_land_wind() -> None:
    """Plage face à l'ouest : un vent d'est vient de la terre, donc offshore."""
    assert offshore_component_kt(90.0, 15.0, 270.0) == pytest.approx(15.0, abs=0.01)


def test_offshore_component_is_negative_for_sea_wind() -> None:
    assert offshore_component_kt(270.0, 15.0, 270.0) == pytest.approx(-15.0, abs=0.01)


def test_side_shore_wind_has_no_offshore_component() -> None:
    """Vent de nord sur une plage ouest : ni l'un ni l'autre, donc zéro."""
    assert offshore_component_kt(0.0, 15.0, 270.0) == pytest.approx(0.0, abs=0.01)


def test_swell_alignment_is_zero_when_swell_faces_the_beach() -> None:
    assert swell_alignment_deg(270.0, 270.0) == pytest.approx(0.0)
    assert swell_alignment_deg(300.0, 270.0) == pytest.approx(30.0)
    assert swell_alignment_deg(180.0, 270.0) == pytest.approx(90.0)


def test_wave_energy_grows_with_height_squared_and_period() -> None:
    assert wave_energy(2.0, 10.0) == pytest.approx(4 * wave_energy(1.0, 10.0))
    assert wave_energy(1.0, 20.0) == pytest.approx(2 * wave_energy(1.0, 10.0))


@pytest.mark.parametrize(
    "degrees, label",
    [(0, "N"), (90, "E"), (180, "S"), (270, "O"), (315, "NO"), (359, "N")],
)
def test_compass_label_in_french(degrees: float, label: str) -> None:
    assert compass_label(degrees) == label


def test_bounding_box_covers_the_radius() -> None:
    min_lat, max_lat, min_lon, max_lon = bounding_box(43.664, -1.44, 40.0)
    assert min_lat < 43.664 < max_lat
    assert min_lon < -1.44 < max_lon
    # La boîte doit englober le cercle, donc déborder : un point à 39 km plein
    # ouest doit y être.
    assert min_lon < -1.44 - 39.0 / (111.0 * 0.72)
