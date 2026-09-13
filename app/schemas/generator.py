"""Composer une séance — ce qui entre, ce qui sort.

Décidé le 13/09 (retours n° 3). Trois écrans, trois réponses : le groupe, la
durée, le matériel. Puis **trois propositions**, chacune avec le principe qui
la justifie en une ligne.

Le principe n'est pas une décoration. Une proposition qu'on ne comprend pas se
remplace au hasard, et on finit par ne plus la lire — c'est la leçon du lot 4
appliquée au générateur.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.training import ExerciseRead


class LevelRead(BaseModel):
    """Le niveau d'un groupe, **et d'où il vient**.

    La provenance est rendue à l'écran, et c'est délibéré : « déduit de
    14 séries » se discute, « niveau 3 » ne se discute pas. Un niveau qu'on ne
    peut pas discuter est un niveau qu'on n'ira jamais corriger.
    """

    model_config = ConfigDict(from_attributes=True)

    group: str
    group_label: str
    level: int
    # `deduit` · `defaut` · `manuel`
    origin: str
    sets_counted: int = 0
    best_reps: Optional[int] = None
    best_seconds: Optional[int] = None


class LevelOverride(BaseModel):
    """La correction à la main. Elle gagne toujours.

    Jules peut se savoir plus fort que ce que son historique montre — une
    reprise après un plâtre, un mois passé à grimper. Une déduction ne discute
    pas avec quelqu'un qui était là.
    """

    group: str
    # `null` **efface** la correction et rend la main à la déduction. C'est le
    # geste « en fait non, reprends ce que tu vois » ; sans lui, une correction
    # posée un jour resterait vraie pour toujours.
    level: Optional[int] = Field(default=None, ge=1, le=5)


class GeneratedItemRead(BaseModel):
    """Une ligne de séance générée. Même forme qu'une ligne de formule."""

    exercise: ExerciseRead
    sets: int
    reps: Optional[int] = None
    duration_s: Optional[int] = None
    rest_s: int = 0
    note: Optional[str] = None
    # Les deux minutes d'échauffement, prises dans la mobilité du groupe.
    # Marquées : un échauffement compté comme une série fausserait le niveau
    # déduit la fois d'après.
    warmup: bool = False


class GeneratedWorkoutRead(BaseModel):
    key: str
    name: str
    principle: str
    duration_min: int
    items: list[GeneratedItemRead] = []


class GenerateRequest(BaseModel):
    """La demande. Tout a un défaut : on peut composer sans rien choisir."""

    groups: list[str] = Field(default_factory=lambda: ["abdos"], min_length=1)
    duration_min: int = Field(default=15, ge=5, le=90)
    # Vide = poids du corps seul. C'est le cas du parking de plage, et c'est le
    # plus fréquent.
    equipment: list[str] = Field(default_factory=list)
    intent: str = "entretien"
    # Fait varier les propositions sans casser le déterminisme : même demande
    # et même sel, mêmes trois séances. Le bouton « autre chose » incrémente.
    variant: int = Field(default=0, ge=0, le=99)


class GenerateResponse(BaseModel):
    """Trois séances, ou moins quand le catalogue ne permet pas trois.

    **Jamais trois fois la même.** Une liste de trois cartes identiques n'est
    pas un choix, c'est un bug qu'on a maquillé.
    """

    workouts: list[GeneratedWorkoutRead] = []
    # Le niveau retenu pour chaque groupe demandé, pour que l'écran puisse
    # dire « à ton niveau » sans le recalculer.
    levels: list[LevelRead] = []
    # Combien d'exercices étaient disponibles. Rendu parce qu'un pool vide a
    # une cause — pas de nom français, pas d'image, pas le bon matériel — et
    # que l'écran doit pouvoir le dire au lieu d'afficher une page blanche.
    pool_size: int = 0
    # Ce qui a écarté des exercices, en clair. Une liste vide veut dire que
    # tout le catalogue du groupe était utilisable.
    reasons: list[str] = []


class SaveGeneratedRequest(BaseModel):
    """Sauver une séance générée comme formule personnelle.

    Une séance générée qui a plu se refait ; sans ce geste, il faudrait
    retrouver la même combinaison de demandes, ce que personne ne fera.
    """

    key: str
    name: str = Field(min_length=1, max_length=80)
    groups: list[str] = Field(default_factory=lambda: ["abdos"], min_length=1)
    duration_min: int = Field(default=15, ge=5, le=90)
    equipment: list[str] = Field(default_factory=list)
    intent: str = "entretien"
    variant: int = Field(default=0, ge=0, le=99)
