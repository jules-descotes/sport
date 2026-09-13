from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.models.enums import Discipline, SessionStatus
from app.schemas.gear import GearRead
from app.schemas.spot import SpotRead
from app.services.geo import wave_energy_kj
from app.schemas.types import UtcDatetime


class SurfSessionCreate(BaseModel):
    """Enregistrement complet — le formulaire, ou la file hors ligne.

    `started_at` peut être dans le passé : une session rétroactive déclenche le
    même backfill d'archive qu'une session enregistrée sur le parking.
    """

    spot_id: int
    started_at: datetime
    duration_min: Optional[int] = Field(default=None, gt=0, le=600)
    discipline: Discipline = Discipline.SURF

    # Deux notes, jamais une seule (cf. CLAUDE.md, règle 6).
    rating_conditions: Optional[int] = Field(default=None, ge=1, le=5)
    rating_personal: Optional[int] = Field(default=None, ge=1, le=5)

    gear_id: Optional[int] = None
    wave_count: Optional[int] = Field(default=None, ge=0, le=500)
    crowd: Optional[int] = Field(default=None, ge=1, le=5)
    notes: Optional[str] = Field(default=None, max_length=2000)
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lon: Optional[float] = Field(default=None, ge=-180, le=180)
    # Fabriqué par le téléphone avant l'envoi : c'est lui qui rend la file
    # hors ligne rejouable sans doublon.
    client_uuid: Optional[str] = Field(default=None, max_length=64)


class SurfSessionUpdate(BaseModel):
    """La notation, et les corrections qui vont avec.

    Tout est optionnel parce que l'écran de notation enregistre en un seul
    envoi ce que l'utilisateur a touché, et lui seul. Le passage en `rated` est
    décidé par le serveur — il regarde si les deux notes sont là — et jamais
    par le client : une session à moitié notée resterait sinon marquée notée,
    et sortirait de l'écran Jour sans être exploitable.
    """

    spot_id: Optional[int] = None
    started_at: Optional[datetime] = None
    duration_min: Optional[int] = Field(default=None, gt=0, le=600)
    discipline: Optional[Discipline] = None
    rating_conditions: Optional[int] = Field(default=None, ge=1, le=5)
    rating_personal: Optional[int] = Field(default=None, ge=1, le=5)
    gear_id: Optional[int] = None
    wave_count: Optional[int] = Field(default=None, ge=0, le=500)
    crowd: Optional[int] = Field(default=None, ge=1, le=5)
    notes: Optional[str] = Field(default=None, max_length=2000)


class SurfSessionQuick(BaseModel):
    """Le chemin des quinze secondes — sortie de l'eau, raccourci iPhone.

    Entrée minimale et rien de plus : une position et une heure de fin. Tout
    le reste est déduit par le serveur, parce que tout champ supplémentaire est
    un tap de plus sur une plage, et que 240 formulaires par an à 90 secondes
    pièce font six heures de saisie et un abandon au bout de trois mois
    (cf. PROJET.md §7.2).
    """

    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lon: Optional[float] = Field(default=None, ge=-180, le=180)
    # Défaut : maintenant. Le raccourci n'a donc qu'à envoyer la position.
    ended_at: Optional[datetime] = None
    duration_min: Optional[int] = Field(default=None, gt=0, le=600)
    discipline: Discipline = Discipline.SURF
    client_uuid: Optional[str] = Field(default=None, max_length=64)


def _with_energy(entries: Any) -> list[dict[str, Any]]:
    """Recopie les points d'une fenêtre en leur ajoutant l'énergie de houle.

    **Calculée à la lecture, jamais stockée.** L'énergie est une fonction pure
    de la hauteur et de la période, toutes deux déjà figées dans le snapshot :
    la stocker ferait une troisième copie de la même information, qui finirait
    par diverger le jour où la constante bougerait.

    Et elle est calculée **ici**, côté serveur, avec la même fonction que
    l'écran Surf. Deux implémentations de `0,49 × H² × T` — une par écran —
    afficheraient un jour deux chiffres différents pour la même houle, et la
    seule chose à en conclure serait qu'on ne peut se fier à aucun des deux.

    La forme brute `H²T` du vecteur de features ne bouge pas : elle vit dans
    `geo.wave_energy`, sans constante, et c'est elle qui entre dans le modèle
    (cf. CLAUDE.md, registre §7.4, feature 9).
    """
    if not isinstance(entries, list):
        return []
    enriched: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        # Copie : le dictionnaire vient de la colonne JSON de l'ORM, et le
        # modifier sur place retoucherait l'objet en session.
        point = dict(entry)
        height = point.get("wave_height_m")
        period = point.get("wave_period_s")
        point["wave_energy_kj"] = (
            None
            if height is None or period is None
            else round(wave_energy_kj(height, period), 1)
        )
        enriched.append(point)
    return enriched


class SurfSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_validator("conditions_snapshot", mode="after")
    @classmethod
    def _add_energy(cls, value: Any) -> Optional[dict[str, Any]]:
        """L'énergie s'ajoute aux deux volets, et à eux seuls."""
        if not isinstance(value, dict):
            return value
        snapshot = dict(value)
        for side in ("forecast", "observed"):
            if side in snapshot:
                snapshot[side] = _with_energy(snapshot[side])
        return snapshot

    @model_validator(mode="after")
    def _headline_energy(self) -> "SurfSessionRead":
        """L'énergie de la session : celle de T0, mesurée de préférence.

        Une colonne dans l'historique a besoin d'un seul chiffre, pas d'une
        fenêtre. On prend l'heure de la session elle-même (`offset_h == 0`), et
        on préfère le volet `observed` : c'est ce qui s'est passé, pas ce qui
        était annoncé — et c'est la grandeur sur laquelle le modèle de goût
        s'entraîne (cf. PROJET.md §7.3).
        """
        snapshot = self.conditions_snapshot
        if not isinstance(snapshot, dict):
            return self
        for side in ("observed", "forecast"):
            for entry in snapshot.get(side) or []:
                if isinstance(entry, dict) and entry.get("offset_h") == 0:
                    energy = entry.get("wave_energy_kj")
                    if energy is not None:
                        self.wave_energy_kj = energy
                        return self
        return self

    @field_validator("snapshot_history", mode="before")
    @classmethod
    def _history_never_null(cls, value: Any) -> list[dict[str, Any]]:
        """La colonne est nulle tant qu'aucun snapshot n'a été remplacé.

        Un `null` obligerait chaque écran à retester ; une liste vide se rend
        toute seule.
        """
        return value or []

    id: int
    spot_id: int
    # Rendu avec la session : l'historique affiche le nom du spot, et faire une
    # requête par ligne pour l'obtenir serait absurde.
    spot: Optional[SpotRead] = None
    # UTC explicite : sans décalage, le front lirait ces heures comme locales.
    started_at: UtcDatetime
    duration_min: Optional[int] = None
    discipline: str
    status: str = SessionStatus.TO_RATE.value
    rating_conditions: Optional[int] = None
    rating_personal: Optional[int] = None
    gear_id: Optional[int] = None
    gear: Optional[GearRead] = None
    wave_count: Optional[int] = None
    crowd: Optional[int] = None
    notes: Optional[str] = None
    photo_url: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    client_uuid: Optional[str] = None
    # Vrai quand le début vient du chemin rapide (fin − 90 min) et n'a pas été
    # corrigé : une estimation ne doit pas se lire comme une mesure.
    start_estimated: bool = False
    # Figé à l'enregistrement, en fenêtre T−2 h / T−1 h / T0, deux volets.
    conditions_snapshot: Optional[dict[str, Any]] = None
    # Les snapshots remplacés, du plus ancien au plus récent. Rendus en entier
    # et pas seulement comptés : le détail d'une session les montre, et c'est
    # le seul moyen de voir qu'une correction a changé ce que le modèle
    # apprendra de cette ligne.
    snapshot_history: list[dict[str, Any]] = []
    # Non nul = en corbeille. Trente jours, puis purge par le job planifié.
    deleted_at: Optional[UtcDatetime] = None
    created_at: UtcDatetime
    # Énergie de la houle à l'heure de la session, en kJ/s par mètre de crête.
    # Dérivée du snapshot à la lecture (cf. `_headline_energy`), jamais stockée :
    # c'est la colonne « énergie » de l'historique, et le chiffre du détail.
    wave_energy_kj: Optional[float] = None


class QuickSessionResponse(BaseModel):
    """Réponse du chemin rapide, taillée pour le raccourci iOS.

    `rate_url` est le lien profond que le raccourci ouvre juste après l'envoi :
    l'app s'ouvre sur l'écran de notation de la session qui vient d'être
    créée. C'est ce qui fait que « noter plus tard » ne veut pas dire
    « ne jamais noter ».
    """

    session: SurfSessionRead
    # Faux quand l'appel est retombé sur une session déjà enregistrée : deux
    # taps rapprochés sur le raccourci donnent une seule session.
    created: bool
    # `nearest` — un spot du catalogue à moins de 2 km ;
    # `home` — repli sur le spot favori du profil, hors zone connue.
    spot_source: str
    spot_distance_km: Optional[float] = None
    rate_url: str
    rate_path: str


class SessionJournal(BaseModel):
    """Ce dont l'écran Jour a besoin, en un seul aller-retour.

    Deux requêtes séparées coûteraient deux allers-retours sur le seul écran
    qu'on ouvre debout, sur un réseau de parking de plage.
    """

    to_rate: list[SurfSessionRead] = []
    today: list[SurfSessionRead] = []
