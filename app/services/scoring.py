"""Note de 1 à 5 par spot et par créneau — règles génériques de cold start.

Ce module ne sait rien d'aucun spot en particulier, et c'est volontaire : il
n'existe pas de fenêtre par spot au lot 1, et il n'en existera jamais de
saisie à la main. L'orientation de la côte, calculée depuis OSM, est le seul
paramètre propre au spot qui entre ici.

Ces règles sont un **amorçage**, pas une vérité (cf. PROJET.md §7.4). Elles
servent jusqu'à ce que quarante sessions soient notées, puis la régression
prend le relais, puis le plus proche voisin. Leur seul travail est que la reco
soit utile dès le premier jour, et qu'elle ne dise jamais de bêtise grossière.

Deux choix de forme méritent d'être explicités :

- **La taille et le vent sont des facteurs, pas des termes.** Un jour à plat
  reste un jour à plat même avec un vent parfait, et un coup de vent d'ouest à
  22 nœuds ne se rattrape pas avec une belle période. Une somme pondérée
  donnerait 3/5 à ces deux journées ; un produit donne 1/5, ce qui est la
  bonne réponse.
- **Les seuils sont en unités de base** (mètres, secondes, nœuds), lisibles
  tels quels, jamais en « pieds » ni en « km/h ».
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional, Sequence

from app.services.geo import (
    compass_label,
    offshore_component_kt,
    swell_alignment_deg,
    wave_energy,
)

# ── Barèmes ────────────────────────────────────────────────────────────────
#
# Chaque barème est une courbe affine par morceaux : (valeur, note de 0 à 1).
# Les points intermédiaires sont interpolés, les extrêmes prolongés à plat.

SIZE_CURVE: tuple[tuple[float, float], ...] = (
    (0.30, 0.00),  # à plat
    (0.50, 0.12),
    (0.80, 0.80),
    (1.00, 1.00),
    (2.00, 1.00),  # le créneau de référence
    (3.00, 0.55),
    (4.50, 0.15),
    (6.00, 0.05),  # hors de portée
)

# Calibrée sur la **période moyenne** servie par MFWAM, et sur elle seule
# (cf. `build_conditions` plus bas). Valeurs relevées sur la côte landaise :
# ~7 s pour une petite mer du vent, ~13 s pour une houle d'ouest de mars.
PERIOD_CURVE: tuple[tuple[float, float], ...] = (
    (4.00, 0.05),  # clapot
    (6.00, 0.20),
    (8.00, 0.45),
    (11.00, 0.85),  # la houle s'ordonne
    (14.00, 1.00),
    (20.00, 1.00),
)

# Écart angulaire houle ↔ orientation du spot (feature 10 du registre).
ALIGNMENT_CURVE: tuple[tuple[float, float], ...] = (
    (0.00, 1.00),
    (30.00, 1.00),
    (60.00, 0.75),
    (90.00, 0.30),
    (120.00, 0.08),  # la houle vient de derrière la terre
    (180.00, 0.05),
)

# En dessous, la mer est lisse quelle que soit la direction du vent.
GLASSY_WIND_KT = 4.0
# Au-dessus, le vent pèse de tout son poids ; entre les deux, on interpole.
FULL_WIND_KT = 18.0
# Un offshore trop fort tient la vague debout et empêche de partir.
TOO_OFFSHORE_KT = 25.0

# Plancher du facteur de vent : même un coup de vent onshore ne met pas la note
# à zéro, il l'écrase.
WIND_FLOOR = 0.15

# Poids du terme de qualité, somme égale à 1.
W_BASE = 0.30
W_PERIOD = 0.45
W_TIDE = 0.25

# Seuils de verdict sur la note continue.
VERDICT_YES = 3.5
VERDICT_MAYBE = 2.5


def _piecewise(curve: Sequence[tuple[float, float]], value: float) -> float:
    """Interpolation affine par morceaux, prolongée à plat aux extrémités."""
    if value <= curve[0][0]:
        return curve[0][1]
    for (x0, y0), (x1, y1) in zip(curve, curve[1:]):
        if value <= x1:
            span = x1 - x0
            if span == 0:
                return y1
            return y0 + (y1 - y0) * (value - x0) / span
    return curve[-1][1]


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


# ── Marée ──────────────────────────────────────────────────────────────────


@dataclass
class TideContext:
    """Position dans la marée, déduite de `sea_level_height_msl`.

    Open-Meteo donne un niveau, pas une pleine mer : la position relative se
    calcule en comparant chaque heure aux extrêmes du jour, et le sens se lit
    sur la pente entre l'heure précédente et la suivante. Ça évite une source
    de marées supplémentaire, et ça marche partout dans le monde.

    Le marnage du jour (feature 8 du registre) tombe du même calcul.
    """

    levels: dict[datetime, float] = field(default_factory=dict)
    extremes: dict[date, tuple[float, float]] = field(default_factory=dict)

    @classmethod
    def from_levels(cls, levels: dict[datetime, Optional[float]]) -> "TideContext":
        clean = {ts: value for ts, value in levels.items() if value is not None}
        extremes: dict[date, tuple[float, float]] = {}
        for ts, value in clean.items():
            day = ts.date()
            low, high = extremes.get(day, (value, value))
            extremes[day] = (min(low, value), max(high, value))
        return cls(levels=clean, extremes=extremes)

    def range_m(self, ts: datetime) -> Optional[float]:
        """Marnage du jour, en mètres."""
        bounds = self.extremes.get(ts.date())
        if bounds is None:
            return None
        return bounds[1] - bounds[0]

    def position(self, ts: datetime) -> Optional[float]:
        """0 = basse mer, 1 = pleine mer, sur le marnage du jour."""
        bounds = self.extremes.get(ts.date())
        level = self.levels.get(ts)
        if bounds is None or level is None:
            return None
        low, high = bounds
        if high - low < 0.15:
            # Marnage négligeable (Méditerranée, lac) : la marée ne dit rien.
            return None
        return _clamp((level - low) / (high - low))

    def trend_m_per_h(self, ts: datetime) -> Optional[float]:
        """Pente du niveau de la mer : positive = marée montante."""
        before = self.levels.get(ts - timedelta(hours=1))
        after = self.levels.get(ts + timedelta(hours=1))
        if before is not None and after is not None:
            return (after - before) / 2.0
        current = self.levels.get(ts)
        if current is None:
            return None
        if after is not None:
            return after - current
        if before is not None:
            return current - before
        return None


# ── Conditions d'un créneau ────────────────────────────────────────────────


@dataclass
class Conditions:
    """Les grandeurs d'un créneau, déjà en unités de base."""

    ts: datetime
    wave_height_m: Optional[float] = None
    wave_period_s: Optional[float] = None
    wave_direction_deg: Optional[float] = None
    wind_speed_kt: Optional[float] = None
    wind_gust_kt: Optional[float] = None
    wind_direction_deg: Optional[float] = None
    sea_level_m: Optional[float] = None
    tide_position: Optional[float] = None
    tide_trend_m_per_h: Optional[float] = None
    tide_range_m: Optional[float] = None
    water_temperature_c: Optional[float] = None

    @property
    def rising(self) -> Optional[bool]:
        if self.tide_trend_m_per_h is None:
            return None
        if abs(self.tide_trend_m_per_h) < 0.02:
            return None  # étale
        return self.tide_trend_m_per_h > 0


@dataclass
class Score:
    """Note continue, note entière, et de quoi écrire la phrase d'explication."""

    value: float
    components: dict[str, float]
    reasons: list[str]

    @property
    def level(self) -> int:
        """1 à 5 — c'est ce niveau qui choisit la couleur de la cellule."""
        return int(_clamp(round(self.value), 1, 5))

    @property
    def verdict(self) -> str:
        if self.value >= VERDICT_YES:
            return "OUI"
        if self.value >= VERDICT_MAYBE:
            return "PEUT-ÊTRE"
        return "NON"


def wind_factor(
    wind_speed_kt: Optional[float],
    wind_direction_deg: Optional[float],
    onshore_dir_deg: Optional[float],
) -> tuple[float, Optional[float]]:
    """Facteur de vent dans [WIND_FLOOR, 1], et composante offshore signée.

    Sans orientation de côte connue, on ne peut rien dire du sens du vent : on
    se rabat sur sa seule force, ce qui reste vrai partout — un vent fort est
    plus souvent un problème qu'un cadeau.
    """
    if wind_speed_kt is None:
        return 1.0, None

    if onshore_dir_deg is None or wind_direction_deg is None:
        strength = _clamp((wind_speed_kt - GLASSY_WIND_KT) / (FULL_WIND_KT - GLASSY_WIND_KT))
        return _clamp(1.0 - 0.55 * strength, WIND_FLOOR, 1.0), None

    offshore = offshore_component_kt(
        wind_direction_deg, wind_speed_kt, onshore_dir_deg
    )

    # Direction : -1 plein onshore, +1 plein offshore.
    direction_score = _clamp(0.5 + 0.5 * (offshore / max(wind_speed_kt, 1.0)))

    # Amplitude : à 4 nœuds la direction n'a aucune importance, à 18 elle fait
    # tout. Entre les deux, on mélange avec une « bonne note par défaut ».
    weight = _clamp(
        (wind_speed_kt - GLASSY_WIND_KT) / (FULL_WIND_KT - GLASSY_WIND_KT)
    )
    factor = (1.0 - weight) * 0.92 + weight * direction_score

    if offshore > TOO_OFFSHORE_KT:
        factor *= 0.85

    return _clamp(factor, WIND_FLOOR, 1.0), offshore


def score_conditions(
    conditions: Conditions, onshore_dir_deg: Optional[float] = None
) -> Score:
    """Note de 1 à 5 d'un créneau, à partir des règles génériques."""
    reasons: list[str] = []

    height = conditions.wave_height_m
    period = conditions.wave_period_s

    if height is None:
        # Sans hauteur de houle il n'y a rien à noter : une note inventée serait
        # pire qu'une absence de note.
        return Score(
            value=1.0,
            components={},
            reasons=["prévision de houle indisponible"],
        )

    size = _piecewise(SIZE_CURVE, height)
    period_score = _piecewise(PERIOD_CURVE, period) if period is not None else 0.5

    alignment_score = 1.0
    alignment_deg: Optional[float] = None
    if onshore_dir_deg is not None and conditions.wave_direction_deg is not None:
        alignment_deg = swell_alignment_deg(
            conditions.wave_direction_deg, onshore_dir_deg
        )
        alignment_score = _piecewise(ALIGNMENT_CURVE, alignment_deg)

    # La houle mal orientée n'arrive tout simplement pas : elle réduit la
    # taille utile, elle ne « retire pas des points ».
    effective_size = size * alignment_score

    factor_wind, offshore = wind_factor(
        conditions.wind_speed_kt, conditions.wind_direction_deg, onshore_dir_deg
    )

    tide_score = 0.75
    if conditions.tide_position is not None:
        # Règle générique, faute de mieux : la mi-marée marche presque partout,
        # les étales beaucoup moins. Un spot qui dément cette règle le dira de
        # lui-même dans les notes, et le modèle appris l'écrasera.
        tide_score = 1.0 - 0.9 * abs(conditions.tide_position - 0.5)
        if conditions.rising:
            tide_score = _clamp(tide_score + 0.05)

    quality = effective_size * factor_wind * (
        W_BASE + W_PERIOD * period_score + W_TIDE * tide_score
    )
    value = 1.0 + 4.0 * _clamp(quality)

    # ── Phrases d'explication ──────────────────────────────────────────────
    #
    # Dans l'ordre de ce qui décide la note, et rien de plus : « mer plate,
    # vent offshore » est une phrase absurde. Dès qu'il n'y a pas de vague,
    # c'est toute l'explication, et les qualités de vent ou de période ne sont
    # que du bruit.
    if height < 0.35:
        reasons.append("mer plate")
    elif size < 0.5:
        reasons.append("trop petit")
    elif height > 3.0:
        reasons.append("trop gros")

    if alignment_deg is not None and alignment_score < 0.5:
        reasons.append("houle mal orientée pour le spot")

    surfable = effective_size >= 0.5

    if offshore is not None and conditions.wind_speed_kt is not None:
        if offshore < -12.0:
            reasons.append("vent onshore appuyé")
        elif offshore < -4.0:
            reasons.append("vent onshore")
        elif surfable and conditions.wind_speed_kt <= GLASSY_WIND_KT:
            reasons.append("pas de vent")
        elif surfable and offshore > 3.0:
            reasons.append("vent offshore")

    if surfable and period is not None and period >= 12.0:
        reasons.append("longue période")

    return Score(
        value=round(value, 2),
        components={
            "size": round(size, 3),
            "period": round(period_score, 3),
            "alignment": round(alignment_score, 3),
            "wind": round(factor_wind, 3),
            "tide": round(tide_score, 3),
            "energy": round(
                wave_energy(height, period) if period is not None else 0.0, 2
            ),
            **({"offshore_kt": round(offshore, 1)} if offshore is not None else {}),
            **(
                {"alignment_deg": round(alignment_deg, 1)}
                if alignment_deg is not None
                else {}
            ),
        },
        reasons=reasons,
    )


# ── Mise en français ───────────────────────────────────────────────────────


def _fr(value: float, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}".replace(".", ",")


def tide_label(conditions: Conditions) -> Optional[str]:
    rising = conditions.rising
    if rising is None:
        if conditions.tide_position is None:
            return None
        return "marée étale"
    return "marée montante" if rising else "marée descendante"


def conditions_line(conditions: Conditions) -> str:
    """« houle 1,4 m / 12 s / NO, vent E 8 kt, marée montante »."""
    parts: list[str] = []

    if conditions.wave_height_m is not None:
        swell = f"houle {_fr(conditions.wave_height_m)} m"
        if conditions.wave_period_s is not None:
            swell += f" / {_fr(conditions.wave_period_s, 0)} s"
        if conditions.wave_direction_deg is not None:
            swell += f" / {compass_label(conditions.wave_direction_deg)}"
        parts.append(swell)

    if conditions.wind_speed_kt is not None:
        wind = "vent"
        if conditions.wind_direction_deg is not None:
            wind += f" {compass_label(conditions.wind_direction_deg)}"
        wind += f" {_fr(conditions.wind_speed_kt, 0)} kt"
        parts.append(wind)

    tide = tide_label(conditions)
    if tide:
        parts.append(tide)

    return ", ".join(parts)


def build_conditions(
    ts: datetime,
    values: dict[str, Optional[float]],
    tide: Optional[TideContext] = None,
) -> Conditions:
    """Assemble un créneau depuis une ligne de `forecasts`.

    **La période notée est toujours la période moyenne**, jamais la période de
    pic, et ce n'est pas un oubli : MFWAM via Open-Meteo ne sert pas
    `wave_peak_period` — la colonne existe et reste vide. On la stocke quand
    même (« on stocke large, on modélise étroit »), et la bouée CANDHIS la
    remplira au lot 1 bis.

    Basculer automatiquement sur la période de pic le jour où la colonne se
    remplit changerait la grandeur notée sans prévenir : `PERIOD_CURVE` est
    calibrée sur la période moyenne, et Tp vaut 25 à 40 % de plus que T02. Le
    jour où l'on voudra noter sur Tp, ce sera avec sa propre courbe et une
    décision explicite.
    """
    period = values.get("wave_period_s")

    conditions = Conditions(
        ts=ts,
        wave_height_m=values.get("wave_height_m"),
        wave_period_s=period,
        wave_direction_deg=values.get("wave_direction_deg"),
        wind_speed_kt=values.get("wind_speed_kt"),
        wind_gust_kt=values.get("wind_gust_kt"),
        wind_direction_deg=values.get("wind_direction_deg"),
        sea_level_m=values.get("sea_level_m"),
        water_temperature_c=values.get("water_temperature_c"),
    )

    if tide is not None:
        conditions.tide_position = tide.position(ts)
        conditions.tide_trend_m_per_h = tide.trend_m_per_h(ts)
        conditions.tide_range_m = tide.range_m(ts)

    return conditions
