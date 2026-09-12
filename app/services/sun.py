"""Lever et coucher du soleil, calculés localement.

Open-Meteo sait les donner, mais pas gratuitement : ce serait un appel de plus
par spot et par passe, pour une grandeur purement astronomique qui tient en
trente lignes. Tout est calculé ici, donc disponible hors ligne et sans
consommer le budget d'appels.

Algorithme NOAA « sunrise equation », précision de l'ordre de la minute aux
latitudes qui nous concernent — largement suffisant pour décider si un créneau
de 8 h est dans le jour.

Sert aussi la feature 19 du registre (heure relative au lever / coucher), qui
entrera dans le modèle quand le volume de sessions le permettra.
"""
from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta
from typing import Optional

# Jour julien du 1er janvier 2000 à 12 h TU.
J2000 = 2451545.0
# Le disque solaire est considéré levé quand son bord supérieur touche
# l'horizon, réfraction atmosphérique comprise.
SUN_ALTITUDE_DEG = -0.833
EARTH_OBLIQUITY_DEG = 23.4397


def _julian_day_number(day: date) -> float:
    """Jour julien de `day` à 12 h TU (formule grégorienne de Fliegel)."""
    a = (14 - day.month) // 12
    y = day.year + 4800 - a
    m = day.month + 12 * a - 3
    jdn = (
        day.day
        + (153 * m + 2) // 5
        + 365 * y
        + y // 4
        - y // 100
        + y // 400
        - 32045
    )
    return float(jdn)


def _from_julian(jd: float) -> datetime:
    return datetime(2000, 1, 1, 12, tzinfo=UTC) + timedelta(days=jd - J2000)


def sun_events(day: date, lat: float, lon: float) -> tuple[Optional[datetime], Optional[datetime]]:
    """Lever et coucher en UTC pour la date locale approchée `day`.

    Renvoie `(None, None)` pendant le jour polaire ou la nuit polaire : aucun
    spot ne nous concerne au-delà du cercle polaire, mais un `None` explicite
    vaut mieux qu'un `ValueError` remonté depuis un `acos`.
    """
    n = _julian_day_number(day) - J2000 + 0.0008
    mean_solar_noon = n - lon / 360.0

    mean_anomaly = (357.5291 + 0.98560028 * mean_solar_noon) % 360.0
    m_rad = math.radians(mean_anomaly)
    center = (
        1.9148 * math.sin(m_rad)
        + 0.0200 * math.sin(2 * m_rad)
        + 0.0003 * math.sin(3 * m_rad)
    )
    ecliptic_longitude = (mean_anomaly + center + 180.0 + 102.9372) % 360.0
    lambda_rad = math.radians(ecliptic_longitude)

    solar_transit = (
        J2000
        + mean_solar_noon
        + 0.0053 * math.sin(m_rad)
        - 0.0069 * math.sin(2 * lambda_rad)
    )

    sin_declination = math.sin(lambda_rad) * math.sin(
        math.radians(EARTH_OBLIQUITY_DEG)
    )
    declination = math.asin(sin_declination)
    phi = math.radians(lat)

    numerator = math.sin(math.radians(SUN_ALTITUDE_DEG)) - math.sin(phi) * math.sin(
        declination
    )
    denominator = math.cos(phi) * math.cos(declination)
    if denominator == 0.0:
        return None, None

    cos_hour_angle = numerator / denominator
    if cos_hour_angle > 1.0 or cos_hour_angle < -1.0:
        return None, None

    hour_angle = math.degrees(math.acos(cos_hour_angle))
    return (
        _from_julian(solar_transit - hour_angle / 360.0),
        _from_julian(solar_transit + hour_angle / 360.0),
    )


def is_daylight(ts: datetime, lat: float, lon: float) -> bool:
    """Le créneau `ts` (UTC) est-il entre le lever et le coucher ?

    On surfe rarement de nuit : un créneau hors jour ne doit jamais être
    proposé, même s'il porte la meilleure note de la semaine.
    """
    sunrise, sunset = sun_events(ts.date(), lat, lon)
    if sunrise is None or sunset is None:
        # Nuit ou jour polaire : on ne bloque rien, faute de mieux.
        return True
    return sunrise <= ts <= sunset


def next_daylight_window(
    now: datetime, lat: float, lon: float
) -> tuple[datetime, datetime]:
    """Prochaine fenêtre de jour : celle en cours, sinon celle de demain.

    C'est l'horizon du verdict de l'écran d'accueil — « je vais à l'eau, oui ou
    non » ne se pose pas pour après-demain.
    """
    for offset in range(0, 3):
        day = (now + timedelta(days=offset)).date()
        sunrise, sunset = sun_events(day, lat, lon)
        if sunrise is None or sunset is None:
            continue
        if now <= sunset:
            return max(now, sunrise), sunset
    # Repli : une journée pleine, plutôt qu'une exception sur l'écran d'accueil.
    return now, now + timedelta(days=1)
