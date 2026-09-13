"""Les critères de Jules, confrontés à la prévision.

Décidé le 13/09. Deux usages, et un seul jeu de règles :

- **`evaluate`** — ce créneau correspond-il aux critères de ce spot ? La
  réponse sert la note (`scoring.score_conditions`) autant que l'annonce.
- **`match_windows`** — sur les trois prochains jours, quelles fenêtres
  correspondent, pour quel favori ? C'est ce que Jour affiche sous le bloc de
  mer : « Parlementia devrait marcher — dim. 10 h à 13 h ».

**Ce que « correspondre » veut dire.** Toutes les contraintes posées doivent
être satisfaites ; celles qui ne sont pas posées ne contraignent rien. Un jeu
de règles entièrement vide correspond donc à tout, ce qui est la bonne
réponse : Jules n'a rien dit, on ne lui invente pas d'avis.

**Dur et mou.** Deux critères disqualifient vraiment : une houle **au-dessus**
du maximum, et un vent **au-dessus** du maximum. Ce sont les deux « c'est
injouable » — trop gros, trop de vent. Tout le reste (trop petit, période
courte, mauvais secteur, mauvaise marée, mauvaise heure) fait simplement rater
la correspondance : c'est peut-être moyen, ce n'est pas disqualifiant, et la
note générique sait déjà le dire.

La distinction porte la pondération du §7 (règle C.4 du 13/09) :

- un créneau **qui correspond** ne peut pas être noté sous 3 — ses critères
  valent mieux que notre géométrie ;
- un créneau qui **rate un critère dur** ne peut pas dépasser 2 — inutile de
  lui trouver des qualités de période.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Iterable, Optional, Sequence
from zoneinfo import ZoneInfo

# Rose à **huit** points. On ne saisit pas « 285° » sur une plage, on saisit
# « ouest » ; la rose à seize points de `geo.compass_label` sert à lire.
SECTORS_8 = ("N", "NE", "E", "SE", "S", "SO", "O", "NO")

TIDE_PHASES = ("low", "rising", "high", "falling")

# Sous ce quart du marnage on est à basse mer, au-dessus des trois quarts à
# pleine mer ; entre les deux, c'est le sens qui nomme la phase.
LOW_TIDE_MAX = 0.25
HIGH_TIDE_MIN = 0.75


def sector8(direction_deg: Optional[float]) -> Optional[str]:
    """Le secteur à huit points d'une direction de provenance."""
    if direction_deg is None:
        return None
    normalized = direction_deg % 360.0
    return SECTORS_8[int((normalized + 22.5) // 45) % 8]


def tide_phase(
    position: Optional[float], rising: Optional[bool]
) -> Optional[str]:
    """`low`, `rising`, `high` ou `falling`, depuis la position dans la marée.

    Les étales sont nommées par leur position et non par leur sens : à pleine
    mer la pente est nulle, et « ni montante ni descendante » n'est pas une
    phase qu'on saisit.
    """
    if position is None:
        return None
    if position <= LOW_TIDE_MAX:
        return "low"
    if position >= HIGH_TIDE_MIN:
        return "high"
    if rising is None:
        return None
    return "rising" if rising else "falling"


@dataclass(frozen=True)
class SpotRules:
    """Les critères d'un spot, tels qu'ils entrent dans le calcul.

    Détaché du modèle SQLAlchemy à dessein : `scoring.py` ne doit rien savoir
    de la base, et ces règles se testent alors sans session.
    """

    wave_height_min_m: Optional[float] = None
    wave_height_max_m: Optional[float] = None
    wave_period_min_s: Optional[float] = None
    swell_sectors: tuple[str, ...] = ()
    wind_sectors: tuple[str, ...] = ()
    wind_max_kt: Optional[float] = None
    tide_phases: tuple[str, ...] = ()
    hour_min: Optional[int] = None
    hour_max: Optional[int] = None

    @property
    def empty(self) -> bool:
        """Vrai quand aucun critère n'est posé. Un tel jeu accepte tout."""
        return not any(
            (
                self.wave_height_min_m is not None,
                self.wave_height_max_m is not None,
                self.wave_period_min_s is not None,
                self.swell_sectors,
                self.wind_sectors,
                self.wind_max_kt is not None,
                self.tide_phases,
                self.hour_min is not None,
                self.hour_max is not None,
            )
        )

    @classmethod
    def from_model(cls, row) -> "SpotRules":
        """Depuis une ligne `spot_rules`. `None` donne un jeu vide."""
        if row is None:
            return cls()
        return cls(
            wave_height_min_m=row.wave_height_min_m,
            wave_height_max_m=row.wave_height_max_m,
            wave_period_min_s=row.wave_period_min_s,
            swell_sectors=tuple(row.swell_sectors or ()),
            wind_sectors=tuple(row.wind_sectors or ()),
            wind_max_kt=row.wind_max_kt,
            tide_phases=tuple(row.tide_phases or ()),
            hour_min=row.hour_min,
            hour_max=row.hour_max,
        )


@dataclass
class RuleMatch:
    """Le verdict d'un créneau face aux critères d'un spot."""

    # Vrai quand **toutes** les contraintes posées sont satisfaites.
    matches: bool
    # Vrai quand une contrainte disqualifiante est dépassée : trop gros, trop
    # de vent. C'est elle qui plafonne la note à 2.
    hard_miss: bool
    # Ce qui a coincé, en français, pour l'explication à l'écran.
    misses: list[str] = field(default_factory=list)
    # Vrai quand aucun critère n'était posé : « correspond » ne veut alors rien
    # dire, et la note ne doit être ni plancher ni plafonnée.
    unconstrained: bool = False


def _fr(value: float, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}".replace(".", ",")


def evaluate(
    rules: SpotRules,
    *,
    wave_height_m: Optional[float] = None,
    wave_period_s: Optional[float] = None,
    wave_direction_deg: Optional[float] = None,
    wind_speed_kt: Optional[float] = None,
    wind_direction_deg: Optional[float] = None,
    tide_position: Optional[float] = None,
    tide_rising: Optional[bool] = None,
    local_hour: Optional[int] = None,
) -> RuleMatch:
    """Confronte un créneau aux critères d'un spot.

    **Une donnée manquante ne fait jamais rater un critère.** Si la période
    n'est pas connue, la contrainte de période ne s'applique pas : elle n'est
    ni satisfaite ni violée. Traiter l'absence comme un échec ferait disparaître
    toutes les annonces le jour où une colonne d'Open-Meteo tombe, et le
    silence se lirait comme « rien ne marche ».
    """
    if rules.empty:
        return RuleMatch(matches=False, hard_miss=False, unconstrained=True)

    misses: list[str] = []
    hard = False

    if rules.wave_height_max_m is not None and wave_height_m is not None:
        if wave_height_m > rules.wave_height_max_m:
            misses.append(f"plus de {_fr(rules.wave_height_max_m)} m de houle")
            hard = True

    if rules.wave_height_min_m is not None and wave_height_m is not None:
        if wave_height_m < rules.wave_height_min_m:
            misses.append(f"moins de {_fr(rules.wave_height_min_m)} m de houle")

    if rules.wave_period_min_s is not None and wave_period_s is not None:
        if wave_period_s < rules.wave_period_min_s:
            misses.append(f"période sous {_fr(rules.wave_period_min_s, 0)} s")

    if rules.swell_sectors and wave_direction_deg is not None:
        sector = sector8(wave_direction_deg)
        if sector not in rules.swell_sectors:
            misses.append(f"houle de {sector}")

    if rules.wind_max_kt is not None and wind_speed_kt is not None:
        if wind_speed_kt > rules.wind_max_kt:
            misses.append(f"plus de {_fr(rules.wind_max_kt, 0)} kt de vent")
            hard = True

    if rules.wind_sectors and wind_direction_deg is not None:
        sector = sector8(wind_direction_deg)
        if sector not in rules.wind_sectors:
            misses.append(f"vent de {sector}")

    if rules.tide_phases:
        phase = tide_phase(tide_position, tide_rising)
        if phase is not None and phase not in rules.tide_phases:
            misses.append(PHASE_LABELS.get(phase, phase))

    if local_hour is not None:
        if rules.hour_min is not None and local_hour < rules.hour_min:
            misses.append(f"avant {rules.hour_min} h")
        if rules.hour_max is not None and local_hour > rules.hour_max:
            misses.append(f"après {rules.hour_max} h")

    return RuleMatch(matches=not misses, hard_miss=hard, misses=misses)


PHASE_LABELS = {
    "low": "basse mer",
    "rising": "marée montante",
    "high": "pleine mer",
    "falling": "marée descendante",
}


# ── Les fenêtres annoncées sur Jour ────────────────────────────────────────


@dataclass
class MatchWindow:
    """Une plage horaire continue où un spot correspond à ses critères."""

    spot_id: int
    start: datetime
    end: datetime
    # Le créneau le mieux noté de la fenêtre — celui qu'on ouvre au tap.
    best_ts: datetime
    best_score: float
    wave_height_m: Optional[float]
    wave_period_s: Optional[float]
    wave_direction_deg: Optional[float]
    wind_speed_kt: Optional[float]
    wind_direction_deg: Optional[float]
    tide_phase: Optional[str]

    @property
    def hours(self) -> float:
        return (self.end - self.start).total_seconds() / 3600.0


def local_hour(ts: datetime, timezone: str = "Europe/Paris") -> int:
    try:
        zone = ZoneInfo(timezone)
    except Exception:
        zone = ZoneInfo("Europe/Paris")
    return ts.astimezone(zone).hour


def group_windows(
    spot_id: int,
    matching: Sequence[tuple[datetime, dict]],
    *,
    max_gap_h: int = 1,
) -> list[MatchWindow]:
    """Regroupe des créneaux correspondants en plages continues.

    Une annonce heure par heure serait illisible : « dim. 10 h, dim. 11 h,
    dim. 12 h » est la même information écrite trois fois. On regroupe donc, et
    la fenêtre s'étend jusqu'à la **fin** du dernier créneau retenu — un créneau
    de 12 h couvre l'heure de 12 h à 13 h.

    `max_gap_h` tolère un trou d'une heure : une seule heure qui rate de peu au
    milieu d'une bonne matinée ne doit pas couper l'annonce en deux.
    """
    windows: list[MatchWindow] = []
    current: list[tuple[datetime, dict]] = []

    def flush() -> None:
        if not current:
            return
        best_ts, best = max(current, key=lambda item: item[1]["score"])
        windows.append(
            MatchWindow(
                spot_id=spot_id,
                start=current[0][0],
                end=current[-1][0] + timedelta(hours=1),
                best_ts=best_ts,
                best_score=best["score"],
                wave_height_m=best.get("wave_height_m"),
                wave_period_s=best.get("wave_period_s"),
                wave_direction_deg=best.get("wave_direction_deg"),
                wind_speed_kt=best.get("wind_speed_kt"),
                wind_direction_deg=best.get("wind_direction_deg"),
                tide_phase=best.get("tide_phase"),
            )
        )
        current.clear()

    for ts, values in sorted(matching, key=lambda item: item[0]):
        if current and (ts - current[-1][0]) > timedelta(hours=max_gap_h + 1):
            flush()
        current.append((ts, values))
    flush()

    return windows


def _day_name(ts_local: datetime, now_local: datetime) -> str:
    days = ("lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim.")
    delta = (ts_local.date() - now_local.date()).days
    if delta == 0:
        return "auj."
    if delta == 1:
        return "demain"
    return days[ts_local.weekday()]


def window_sentence(
    window: MatchWindow,
    spot_name: str,
    now: datetime,
    timezone: str = "Europe/Paris",
) -> str:
    """« Parlementia devrait marcher — dim. 10 h à 13 h ».

    Le conditionnel est voulu : ce sont des critères larges confrontés à une
    prévision, pas une promesse. Écrire « Parlementia marche » sur une donnée
    à trois jours serait une affirmation qu'on ne peut pas tenir.
    """
    try:
        zone = ZoneInfo(timezone)
    except Exception:
        zone = ZoneInfo("Europe/Paris")

    start = window.start.astimezone(zone)
    end = window.end.astimezone(zone)
    now_local = now.astimezone(zone)

    day = _day_name(start, now_local)
    span = (
        f"{start.hour} h"
        if window.hours <= 1
        else f"{start.hour} h à {end.hour} h"
    )
    return f"{spot_name} devrait marcher — {day} {span}"


def window_details(window: MatchWindow) -> str:
    """« 1,6 m / 13 s / NO · vent E 6 kt · montante » — les chiffres du sommet."""
    from app.services.geo import compass_label

    parts: list[str] = []
    if window.wave_height_m is not None:
        swell = f"{_fr(window.wave_height_m)} m"
        if window.wave_period_s is not None:
            swell += f" / {_fr(window.wave_period_s, 0)} s"
        if window.wave_direction_deg is not None:
            swell += f" / {compass_label(window.wave_direction_deg)}"
        parts.append(swell)

    if window.wind_speed_kt is not None:
        wind = "vent"
        if window.wind_direction_deg is not None:
            wind += f" {compass_label(window.wind_direction_deg)}"
        wind += f" {_fr(window.wind_speed_kt, 0)} kt"
        parts.append(wind)

    if window.tide_phase:
        parts.append(PHASE_LABELS.get(window.tide_phase, window.tide_phase))

    return " · ".join(parts)


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def flatten(rules_by_spot: dict[int, SpotRules], spot_ids: Iterable[int]) -> dict[int, SpotRules]:
    """Un jeu de règles par spot, vide pour ceux qui n'en ont pas.

    Les appelants n'ont alors jamais à tester la présence : un spot sans
    critères se comporte comme un spot dont les critères acceptent tout.
    """
    return {spot_id: rules_by_spot.get(spot_id, SpotRules()) for spot_id in spot_ids}
