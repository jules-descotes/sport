from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.types import UtcDatetime


# ── Objectifs ──────────────────────────────────────────────────────────────


class MeasurementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    measured_on: date
    value: float
    note: Optional[str] = None


class MeasurementCreate(BaseModel):
    """Une mesure, posée à la molette. Aucun clavier n'est nécessaire.

    `measured_on` par défaut aujourd'hui : on mesure le jour où on mesure. La
    saisie rétroactive existe quand même — on retrouve parfois un chiffre noté
    sur un papier.
    """

    value: float
    measured_on: Optional[date] = None
    note: Optional[str] = Field(default=None, max_length=500)


class ObjectiveRead(BaseModel):
    """Une jauge : départ, aujourd'hui, cible — et ce qu'il reste à faire.

    `start_value` est la **première mesure**, jamais une valeur saisie. Tant
    qu'il n'y a aucune mesure, tout est nul et l'écran le dit : une jauge à
    moitié pleine se lirait comme un relevé.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    measure: str
    unit: str
    # `up` = plus c'est haut, mieux c'est ; `down` = l'inverse.
    direction: str
    target_value: Optional[float] = None
    start_value: Optional[float] = None
    current_value: Optional[float] = None
    # 0 au départ, 1 sur la cible. Nul tant qu'il manque une des trois bornes.
    ratio: Optional[float] = None
    last_measured_on: Optional[date] = None
    measure_every_days: int = 21
    # Vrai quand la fréquence de mesure est dépassée — ou qu'aucune mesure
    # n'existe. L'écran Training affiche alors le rappel « mesurer ».
    needs_measurement: bool = False
    measurements: list[MeasurementRead] = []


# ── Bibliothèque ───────────────────────────────────────────────────────────


class ExerciseRead(BaseModel):
    """Un exercice — **avec sa source et sa licence**, toujours."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    category: str
    muscle_group: Optional[str] = None
    instructions: Optional[str] = None
    image_url: Optional[str] = None
    source: str
    license: Optional[str] = None
    source_url: Optional[str] = None


class FormulaItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int
    sets: int
    # L'un **ou** l'autre : un gainage se tient, une rotation se compte.
    reps: Optional[int] = None
    duration_s: Optional[int] = None
    tempo: Optional[str] = None
    rest_s: int = 0
    note: Optional[str] = None
    exercise: ExerciseRead


class FormulaRead(BaseModel):
    """Une séance type, avec **le principe qui la justifie**."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    duration_min: int
    weekly_target: int
    principle: str
    objective_slugs: list[str] = []
    tags: list[str] = []
    variant_of: Optional[str] = None
    family: str
    items: list[FormulaItemRead] = []
    # Séances complètes faites cette semaine, comptées **par famille** : trois
    # Réveils différents dans la semaine, c'est trois réveils.
    done_this_week: int = 0


# ── Séances ────────────────────────────────────────────────────────────────


class WorkoutSetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int
    exercise_name: str
    reps: Optional[int] = None
    duration_s: Optional[int] = None
    # Vrai quand on est passé au suivant. Distinct d'une série absente : l'une
    # dit qu'un exercice ne passe pas, l'autre que la séance était trop longue.
    skipped: bool = False


class WorkoutSetInput(BaseModel):
    position: int
    exercise_id: Optional[int] = None
    formula_item_id: Optional[int] = None
    exercise_name: str = Field(max_length=120)
    reps: Optional[int] = Field(default=None, ge=0, le=500)
    duration_s: Optional[int] = Field(default=None, ge=0, le=3600)
    skipped: bool = False


class WorkoutStart(BaseModel):
    formula_id: int
    started_at: Optional[datetime] = None


class WorkoutFinish(BaseModel):
    """La fin d'une séance : un écran, un tap.

    `completed` et `cut_short` ne sont **pas** déduits l'un de l'autre par le
    client : le serveur les tranche à partir des séries réellement faites. Une
    séance arrêtée à la sixième minute d'une formule de vingt-huit est une
    information, et laisser le client la déclarer complète l'effacerait.
    """

    ended_at: Optional[datetime] = None
    feeling: Optional[int] = Field(default=None, ge=1, le=5)
    notes: Optional[str] = Field(default=None, max_length=1000)
    sets: list[WorkoutSetInput] = []


class WorkoutRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    formula_id: Optional[int] = None
    formula_name: str
    formula_family: Optional[str] = None
    started_at: UtcDatetime
    ended_at: Optional[UtcDatetime] = None
    completed: bool = False
    # Comptée à part, et jamais confondue avec une séance faite.
    cut_short: bool = False
    feeling: Optional[int] = None
    notes: Optional[str] = None
    duration_min: Optional[int] = None
    sets: list[WorkoutSetRead] = []


# ── Écran Training ─────────────────────────────────────────────────────────


class ProposalRead(BaseModel):
    """La séance du jour — **une seule**, remplaçable en un tap."""

    formula: Optional[FormulaRead] = None
    # La phrase qui dit pourquoi celle-ci : une proposition qu'on ne comprend
    # pas se remplace au hasard, et on finit par ne plus la lire.
    reason: str
    alternatives: list[FormulaRead] = []
    # Jours de surf d'affilée. Au-delà de trois, le renfo est écarté.
    surf_streak: int = 0


class TrainingOverview(BaseModel):
    """Tout l'écran Training en un aller-retour.

    Quatre requêtes séparées coûteraient quatre allers-retours sur un réseau
    de parking de plage, pour un écran qu'on ouvre debout.
    """

    objectives: list[ObjectiveRead] = []
    formulas: list[FormulaRead] = []
    proposal: ProposalRead
    recent: list[WorkoutRead] = []
