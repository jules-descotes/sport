"""La dépense estimée d'une journée, telle qu'elle sort à l'écran.

**« Estimée » est le mot, et il est affiché.** Une dépense de surf n'est pas
mesurable : le MET du compendium vaut pour « surf, général », la durée est
arrondie au quart d'heure, et la taille des vagues est un souvenir. Le chiffre
est utile — il dit si la journée a coûté 200 ou 700 kcal — et il serait
malhonnête au kcal près. La cible calorique ne s'y fie d'ailleurs pas
aveuglément : c'est `calibration_kcal`, corrigé par la balance toutes les deux
à trois semaines, qui rattrape ce que cette estimation ne sait pas
(cf. PROJET.md §5).
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class ExpenditureItemRead(BaseModel):
    """Une ligne du détail, ouverte au tap depuis l'écran Jour."""

    model_config = ConfigDict(from_attributes=True)

    kind: str
    label: str
    minutes: int
    # Le MET retenu. Affiché dans le détail et pas sur la ligne : c'est
    # l'explication du chiffre, pas le chiffre.
    met: float
    kcal: int
    # Ce qui a modulé le MET, en clair : « grandes vagues », « renfo ».
    detail: Optional[str] = None


class DayExpenditureRead(BaseModel):
    """Ce que la journée a coûté **en plus** de ne rien faire.

    « En plus » : le métabolisme de repos est retranché. Une heure à 5 MET ne
    coûte pas 5 × poids, elle coûte 4 × poids de plus que de rester assis, et
    oublier ce détail surestime la dépense de 20 à 30 %.
    """

    surf_min: int = 0
    surf_kcal: int = 0
    workout_min: int = 0
    workout_kcal: int = 0
    total_kcal: int = 0
    items: list[ExpenditureItemRead] = []
    # Le poids retenu pour le calcul. Rendu parce qu'il change tout : une
    # estimation faite sur un poids par défaut n'a pas la même valeur qu'une
    # estimation faite sur la pesée de dimanche.
    weight_kg: float
    # Vrai quand le poids vient d'un défaut faute de pesée. L'écran le dit
    # plutôt que de faire passer une estimation pour un calcul.
    weight_estimated: bool = False
