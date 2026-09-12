"""Géométrie de côte et d'angles.

Tout ce qui touche à l'orientation d'un spot vit ici. Deux conventions à ne
jamais perdre de vue :

1. **Les directions météo sont des provenances.** Un vent « 90° » vient de
   l'est, une houle « 290° » vient du nord-ouest. C'est la convention
   d'Open-Meteo comme celle des bulletins.
2. **Les lignes `natural=coastline` d'OSM sont orientées terre à gauche, mer à
   droite.** C'est une règle de saisie imposée par le projet, vérifiée par
   leurs outils de contrôle. Elle donne gratuitement le côté « mer » du trait
   de côte : la normale sortante est le cap du segment + 90°.

`onshore_dir_deg` est donc la direction dans laquelle on regarde la mer depuis
la plage — un vent qui vient de cette direction est onshore, un vent qui vient
de l'opposé est offshore.
"""
from __future__ import annotations

import math
from typing import Iterable, Optional, Sequence

EARTH_RADIUS_M = 6_371_008.8

# Coordonnée d'un point de trait de côte : (lat, lon).
Point = tuple[float, float]


def normalize_deg(angle: float) -> float:
    """Ramène un angle dans [0, 360)."""
    return angle % 360.0


def angular_diff_deg(a: float, b: float) -> float:
    """Écart angulaire absolu le plus court, dans [0, 180]."""
    return abs((a - b + 180.0) % 360.0 - 180.0)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Cap initial du grand cercle allant de 1 vers 2, dans [0, 360)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_lambda = math.radians(lon2 - lon1)
    y = math.sin(d_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(
        d_lambda
    )
    return normalize_deg(math.degrees(math.atan2(y, x)))


def onshore_from_coast_bearing(coast_bearing_deg: float) -> float:
    """Normale sortante du trait de côte OSM (terre à gauche → mer à +90°)."""
    return normalize_deg(coast_bearing_deg + 90.0)


def offshore_component_kt(
    wind_from_deg: float, wind_speed_kt: float, onshore_dir_deg: float
) -> float:
    """Composante offshore signée du vent, en nœuds (feature 11 du registre).

    Positive = le vent vient de la terre et lisse la vague. Négative = onshore,
    il la hache. La projection est celle du vecteur vent sur l'axe
    perpendiculaire à la côte ; le vent latéral (side-shore) donne zéro, ce qui
    est le comportement attendu.
    """
    return -wind_speed_kt * math.cos(math.radians(wind_from_deg - onshore_dir_deg))


def swell_alignment_deg(wave_from_deg: float, onshore_dir_deg: float) -> float:
    """Écart angulaire houle ↔ orientation du spot (feature 10 du registre).

    0° = la houle rentre pile en face. 90° = elle longe la côte.
    """
    return angular_diff_deg(wave_from_deg, onshore_dir_deg)


def wave_energy(height_m: float, period_s: float) -> float:
    """Énergie de la houle, proportionnelle à H²T (feature 9 du registre).

    Sans constante physique : seul l'ordre de grandeur relatif sert au modèle.
    C'est cette forme brute qui entre dans le vecteur de features — jamais la
    valeur mise à l'échelle de `wave_energy_kj`, qui n'est qu'un affichage.
    """
    return height_m * height_m * period_s


# Flux d'énergie d'une houle en eau profonde, par mètre de crête :
#
#     P = ρ g² H² T / (64 π)
#
# avec ρ = 1025 kg/m³ (eau de mer) et g = 9,81 m/s². Le coefficient vaut
# 1025 × 9,81² / (64 π) ≈ 490 W/m pour H en mètres et T en secondes, soit
# **0,49 kilojoule par seconde et par mètre de crête** — ce que les
# océanographes écrivent kW/m.
#
# C'est la mise à l'échelle physique de la feature 9 (∝ H²T) : la forme est
# exactement celle du registre, la constante ne fait que lui donner une unité
# lisible. Sur la côte landaise, 0,5 m / 7 s donne ~0,9 ; 1,4 m / 12 s ~11,5 ;
# 2,5 m / 15 s ~46. Un chiffre qui se lit à bout de bras.
WAVE_ENERGY_COEFFICIENT_KJ = 0.49


def wave_energy_kj(height_m: float, period_s: float) -> float:
    """Flux d'énergie de la houle, en kJ par seconde et par mètre de crête.

    Même grandeur que `wave_energy` — proportionnelle à H²T — avec sa
    constante physique, pour être affichée plutôt que donnée à un modèle.

    Deux vagues d'un mètre ne se valent pas : à 7 s de période elle porte
    2,4 kJ/s/m, à 15 s elle en porte 7,4. C'est ce rapport de trois que la
    seule hauteur ne dit pas, et c'est pour ça que la ligne existe.
    """
    return WAVE_ENERGY_COEFFICIENT_KJ * height_m * height_m * period_s


def compass_label(direction_deg: float) -> str:
    """Rose des vents en français, 16 secteurs — pour les phrases d'explication."""
    labels = (
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO",
    )
    index = int((normalize_deg(direction_deg) + 11.25) // 22.5) % 16
    return labels[index]


def bounding_box(
    lat: float, lon: float, radius_km: float
) -> tuple[float, float, float, float]:
    """Boîte englobante large, pour dégrossir en SQL avant le calcul exact.

    Sans elle, chaque ouverture de l'app balaierait le catalogue mondial en
    Python. La boîte déborde volontairement du cercle : c'est un premier tri,
    la distance exacte tranche ensuite.
    """
    lat_delta = radius_km / 111.0
    cos_lat = math.cos(math.radians(lat))
    # Près des pôles la boîte dégénère : on la laisse couvrir toute la
    # longitude plutôt que de diviser par un cosinus qui tend vers zéro.
    lon_delta = 180.0 if abs(cos_lat) < 1e-6 else radius_km / (111.0 * abs(cos_lat))
    return (
        lat - lat_delta,
        lat + lat_delta,
        max(-180.0, lon - lon_delta),
        min(180.0, lon + lon_delta),
    )


# ── Distance point ↔ segment ────────────────────────────────────────────────
#
# À l'échelle d'un trait de côte (quelques centaines de mètres), une projection
# équirectangulaire locale est exacte à mieux que le mètre, et elle évite de
# résoudre un problème de géodésie pour trouver le segment le plus proche.


def _local_xy(lat: float, lon: float, lat0: float, lon0: float) -> tuple[float, float]:
    x = math.radians(lon - lon0) * math.cos(math.radians(lat0)) * EARTH_RADIUS_M
    y = math.radians(lat - lat0) * EARTH_RADIUS_M
    return x, y


def point_to_segment_m(
    lat: float, lon: float, a: Point, b: Point
) -> tuple[float, float]:
    """Distance au segment [a, b] en mètres, et abscisse curviligne t ∈ [0, 1]."""
    ax, ay = _local_xy(a[0], a[1], lat, lon)
    bx, by = _local_xy(b[0], b[1], lat, lon)

    dx, dy = bx - ax, by - ay
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq == 0.0:
        return math.hypot(ax, ay), 0.0

    # Le point courant est l'origine du repère local : projeter (0,0) sur [a,b].
    t = max(0.0, min(1.0, -(ax * dx + ay * dy) / seg_len_sq))
    px, py = ax + t * dx, ay + t * dy
    return math.hypot(px, py), t


def _smoothed_bearing(way: Sequence[Point], index: int, smoothing_m: float) -> float:
    """Cap du trait de côte autour du segment `index`, lissé sur `smoothing_m`.

    Le détail d'OSM est très fin : un segment isolé peut faire trois mètres et
    pointer n'importe où (un rocher, une cale de mise à l'eau). On étend de
    part et d'autre jusqu'à couvrir la distance de lissage, et on prend le cap
    du segment global. L'orientation qui en sort est un *a priori* de cold
    start, pas une vérité (cf. PROJET.md §7.4) — une précision au degré près
    n'aurait aucun sens.
    """
    start, end = index, index + 1

    covered = 0.0
    while start > 0 and covered < smoothing_m:
        covered += haversine_m(*way[start - 1], *way[start])
        start -= 1

    covered = 0.0
    last = len(way) - 1
    while end < last and covered < smoothing_m:
        covered += haversine_m(*way[end], *way[end + 1])
        end += 1

    return bearing_deg(way[start][0], way[start][1], way[end][0], way[end][1])


def nearest_coast_bearing(
    lat: float,
    lon: float,
    ways: Iterable[Sequence[Point]],
    smoothing_m: float = 500.0,
    max_distance_m: float = 20_000.0,
) -> Optional[tuple[float, float]]:
    """Cap du trait de côte le plus proche, et distance au spot.

    Renvoie `None` si aucun trait de côte n'est exploitable dans le rayon :
    mieux vaut une orientation absente qu'une orientation fausse, un spot sans
    orientation reste notable sur la hauteur et la période seules.
    """
    best: Optional[tuple[float, int, Sequence[Point]]] = None

    for way in ways:
        if len(way) < 2:
            continue
        for i in range(len(way) - 1):
            distance, _ = point_to_segment_m(lat, lon, way[i], way[i + 1])
            if distance > max_distance_m:
                continue
            if best is None or distance < best[0]:
                best = (distance, i, way)

    if best is None:
        return None

    distance, index, way = best
    return _smoothed_bearing(way, index, smoothing_m), distance
