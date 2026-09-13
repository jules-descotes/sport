"""Les seuils de qualité, et les défauts qui sont ceux de Jules.

Les valeurs par défaut vivent **ici**, dans le code, et pas dans une migration
ni dans une colonne `server_default` : elles se corrigent à la relecture, et on
n'écrit pas une migration par changement d'avis.

Elles sont celles que Jules a données le 13/09, mot pour mot : « période de
mieux en mieux à partir de 8 s ; vent top sous 10 kt puis de plus en plus
marqué ; houle ça commence à 1,2 m puis mieux en grossissant ».
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Les défauts de Jules. Ce ne sont pas des « valeurs raisonnables » trouvées
# quelque part : ce sont les siennes, et c'est la seule raison pour laquelle
# elles ont le droit d'être des défauts.
DEFAULTS: dict[str, float] = {
    "period_good_s": 8.0,
    "period_great_s": 12.0,
    "wind_top_kt": 10.0,
    "wind_strong_kt": 15.0,
    "wind_very_strong_kt": 20.0,
    "wave_min_m": 1.2,
    "wave_good_m": 1.8,
    "wave_big_m": 2.5,
}


class ThresholdsBase(BaseModel):
    """Les huit nombres, bornés à des grandeurs qui existent.

    Les bornes sont larges : ce sont les goûts de quelqu'un, pas un barème. Le
    seul refus est l'absurde — une période de 40 s n'est pas une préférence,
    c'est une faute de frappe.
    """

    period_good_s: float = Field(default=DEFAULTS["period_good_s"], ge=3, le=20)
    period_great_s: float = Field(default=DEFAULTS["period_great_s"], ge=4, le=25)

    wind_top_kt: float = Field(default=DEFAULTS["wind_top_kt"], ge=1, le=40)
    wind_strong_kt: float = Field(default=DEFAULTS["wind_strong_kt"], ge=2, le=50)
    wind_very_strong_kt: float = Field(
        default=DEFAULTS["wind_very_strong_kt"], ge=3, le=60
    )

    wave_min_m: float = Field(default=DEFAULTS["wave_min_m"], ge=0.1, le=6)
    wave_good_m: float = Field(default=DEFAULTS["wave_good_m"], ge=0.2, le=8)
    wave_big_m: float = Field(default=DEFAULTS["wave_big_m"], ge=0.3, le=12)

    @model_validator(mode="after")
    def _ordered(self) -> "ThresholdsBase":
        """Les seuils d'un même axe montent. Sinon la rampe se replie.

        Refusé plutôt que réordonné en silence : intervertir « bon » et « très
        bon » se corrige d'un tap si on le dit, et se paie en couleurs
        incompréhensibles pendant des semaines si on ne le dit pas.
        """
        if self.period_great_s <= self.period_good_s:
            raise ValueError(
                "La période « très bon » doit dépasser la période « bon »."
            )
        if not (
            self.wind_top_kt < self.wind_strong_kt < self.wind_very_strong_kt
        ):
            raise ValueError(
                "Les trois seuils de vent doivent aller en montant."
            )
        if not (self.wave_min_m < self.wave_good_m < self.wave_big_m):
            raise ValueError(
                "Les trois seuils de houle doivent aller en montant."
            )
        return self


class ThresholdsRead(ThresholdsBase):
    model_config = ConfigDict(from_attributes=True)


class ThresholdsUpdate(BaseModel):
    """Une correction partielle : on règle un curseur, pas les huit.

    Tout est optionnel et le serveur repart des valeurs en place — envoyer les
    huit à chaque fois obligerait l'écran à les connaître toutes pour en
    changer une, et une valeur oubliée retomberait au défaut sans prévenir.
    """

    period_good_s: Optional[float] = Field(default=None, ge=3, le=20)
    period_great_s: Optional[float] = Field(default=None, ge=4, le=25)
    wind_top_kt: Optional[float] = Field(default=None, ge=1, le=40)
    wind_strong_kt: Optional[float] = Field(default=None, ge=2, le=50)
    wind_very_strong_kt: Optional[float] = Field(default=None, ge=3, le=60)
    wave_min_m: Optional[float] = Field(default=None, ge=0.1, le=6)
    wave_good_m: Optional[float] = Field(default=None, ge=0.2, le=8)
    wave_big_m: Optional[float] = Field(default=None, ge=0.3, le=12)
