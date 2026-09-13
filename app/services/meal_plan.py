"""Le menu de la semaine — un glouton lisible, pas une IA.

Décidé dès le cadrage (PROJET.md §9) : « un algo glouton sur une banque de
recettes taggées suffit, pas besoin d'IA ». C'est vrai, et il y a une raison
plus forte que la simplicité : **un menu qu'on ne comprend pas ne se suit
pas**. Quand le générateur propose du poisson trois soirs de suite, on doit
pouvoir dire pourquoi — ici, parce que la contrainte de protéines était haute
et que la variété n'a pas suffi à l'emporter.

Le glouton remplit les créneaux dans l'ordre de la semaine, et choisit à chaque
fois la recette qui **minimise un coût**. Le coût mélange trois choses :

1. **L'écart aux macros restantes de la journée.** C'est le terme principal :
   on veut finir la journée près de la cible, pas au-dessus ni très en dessous.
2. **La répétition.** Une recette déjà servie dans la semaine coûte plus cher,
   et beaucoup plus cher si c'était dans les deux derniers jours. C'est ce qui
   empêche les trois poissons d'affilée.
3. **Le temps de préparation**, très légèrement. À macros égales, la recette de
   dix minutes passe devant celle de vingt-cinq — un menu qui demande une heure
   de cuisine tous les soirs ne tient pas une semaine.

Le tirage est **déterministe à graine donnée** : régénérer un repas doit donner
autre chose, mais régénérer toute la semaine deux fois avec la même graine doit
donner le même menu. Un générateur non reproductible est indébogable.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional, Sequence

# Les repas d'une journée, dans l'ordre où ils se vivent.
MEALS: tuple[str, ...] = ("breakfast", "lunch", "snack", "dinner")

# Part de la cible calorique attribuée à chaque repas. Le déjeuner et le dîner
# portent l'essentiel ; l'en-cas est ce qu'il est — un en-cas.
MEAL_SHARE: dict[str, float] = {
    "breakfast": 0.25,
    "lunch": 0.35,
    "snack": 0.10,
    "dinner": 0.30,
}

# Poids du terme de répétition. Élevé dans les deux derniers jours, faible
# ensuite : revoir un plat le jeudi quand on l'a mangé lundi n'est pas un
# problème, le revoir mardi en est un.
REPEAT_COST_RECENT = 600.0
REPEAT_COST_WEEK = 180.0
RECENT_DAYS = 2

# Poids du temps de préparation, en « kilocalories d'écart » par minute. Très
# faible à dessein : c'est un départage à macros égales, pas un critère.
PREP_COST_PER_MIN = 3.0

# Poids de l'écart de protéines, rapporté au gramme. Les protéines sont la
# contrainte qu'on tient vraiment ; les glucides s'ajustent d'eux-mêmes.
PROTEIN_COST_PER_G = 12.0

# En dessous, une recette sans valeurs nutritionnelles ne peut pas être
# comparée : on la garde éligible mais on lui applique un coût neutre, plutôt
# que de l'écarter. Sinon, tant que Ciqual n'est pas importé, aucun menu ne
# pourrait se générer.
NEUTRAL_COST = 400.0


@dataclass(frozen=True)
class Candidate:
    """Une recette, vue par le générateur. Détachée de l'ORM pour se tester."""

    id: int
    slug: str
    name: str
    meals: tuple[str, ...]
    tags: tuple[str, ...]
    prep_min: int
    kcal: Optional[float] = None
    protein_g: Optional[float] = None
    carb_g: Optional[float] = None
    fat_g: Optional[float] = None


@dataclass
class PlannedMeal:
    day_index: int
    meal: str
    recipe: Candidate
    servings: float = 1.0

    @property
    def kcal(self) -> float:
        return (self.recipe.kcal or 0.0) * self.servings

    @property
    def protein_g(self) -> float:
        return (self.recipe.protein_g or 0.0) * self.servings


@dataclass
class WeekPlan:
    meals: list[PlannedMeal] = field(default_factory=list)

    def of_day(self, day_index: int) -> list[PlannedMeal]:
        return [meal for meal in self.meals if meal.day_index == day_index]

    def kcal_of_day(self, day_index: int) -> float:
        return sum(meal.kcal for meal in self.of_day(day_index))

    def protein_of_day(self, day_index: int) -> float:
        return sum(meal.protein_g for meal in self.of_day(day_index))


def meal_cost(
    candidate: Candidate,
    *,
    kcal_slot: float,
    protein_slot: float,
    last_seen_day: Optional[int],
    day_index: int,
) -> float:
    """Ce que coûte de servir cette recette à ce créneau. Plus bas est mieux.

    Un candidat sans valeurs nutritionnelles reçoit un coût **neutre** plutôt
    que d'être écarté : tant que la table Ciqual n'est pas importée, aucune
    recette n'a de macros, et refuser de générer laisserait l'écran vide.
    """
    if candidate.kcal is None:
        cost = NEUTRAL_COST
    else:
        cost = abs(candidate.kcal - kcal_slot)
        if candidate.protein_g is not None and protein_slot > 0:
            cost += PROTEIN_COST_PER_G * abs(candidate.protein_g - protein_slot)

    if last_seen_day is not None:
        gap = day_index - last_seen_day
        cost += REPEAT_COST_RECENT if gap <= RECENT_DAYS else REPEAT_COST_WEEK

    cost += PREP_COST_PER_MIN * candidate.prep_min
    return cost


def pick(
    candidates: Sequence[Candidate],
    *,
    meal: str,
    day_index: int,
    kcal_slot: float,
    protein_slot: float,
    last_seen: dict[int, int],
    rng: random.Random,
    exclude: frozenset[int] = frozenset(),
) -> Optional[Candidate]:
    """La meilleure recette pour ce créneau, avec un peu de hasard.

    On tire **parmi les trois meilleures** plutôt que de prendre la première :
    un glouton strictement déterministe sur une banque de quarante recettes
    donnerait le même menu toutes les semaines, et un menu identique chaque
    semaine cesse d'être lu. Le hasard reste borné — on ne va jamais chercher
    le vingtième candidat.
    """
    eligible = [
        candidate
        for candidate in candidates
        if meal in candidate.meals and candidate.id not in exclude
    ]
    if not eligible:
        return None

    scored = sorted(
        eligible,
        key=lambda candidate: meal_cost(
            candidate,
            kcal_slot=kcal_slot,
            protein_slot=protein_slot,
            last_seen_day=last_seen.get(candidate.id),
            day_index=day_index,
        ),
    )
    return rng.choice(scored[: min(3, len(scored))])


def generate_week(
    candidates: Sequence[Candidate],
    *,
    kcal_target: float,
    protein_target: float,
    days: int = 7,
    seed: Optional[int] = None,
) -> WeekPlan:
    """Remplit les vingt-huit créneaux de la semaine.

    La cible du jour est répartie entre les repas selon `MEAL_SHARE`, puis
    **ajustée en cours de journée** : ce qui n'a pas été servi au déjeuner
    reste disponible pour le dîner. C'est ce qui empêche une journée de finir
    systématiquement 300 kcal sous la cible parce que le petit déjeuner était
    léger.
    """
    rng = random.Random(seed)
    plan = WeekPlan()
    last_seen: dict[int, int] = {}

    for day_index in range(days):
        remaining_kcal = kcal_target
        remaining_protein = protein_target
        remaining_share = 1.0

        for meal in MEALS:
            share = MEAL_SHARE[meal]
            # Part du reste, et non part de la cible : une journée qui a pris
            # du retard le rattrape au repas suivant.
            slot_kcal = remaining_kcal * (share / remaining_share)
            slot_protein = remaining_protein * (share / remaining_share)

            chosen = pick(
                candidates,
                meal=meal,
                day_index=day_index,
                kcal_slot=slot_kcal,
                protein_slot=slot_protein,
                last_seen=last_seen,
                rng=rng,
            )
            remaining_share -= share
            if chosen is None:
                continue

            plan.meals.append(
                PlannedMeal(day_index=day_index, meal=meal, recipe=chosen)
            )
            last_seen[chosen.id] = day_index
            remaining_kcal -= chosen.kcal or 0.0
            remaining_protein -= chosen.protein_g or 0.0

    return plan


def regenerate_meal(
    plan: WeekPlan,
    candidates: Sequence[Candidate],
    *,
    day_index: int,
    meal: str,
    kcal_target: float,
    protein_target: float,
    seed: Optional[int] = None,
) -> Optional[Candidate]:
    """Remplace **un** repas, sans toucher au reste de la semaine.

    La recette en place est exclue : régénérer doit proposer autre chose, sinon
    le bouton ne sert à rien. Les autres recettes du jour le sont aussi — deux
    fois le même plat dans la journée serait un comble.
    """
    current = next(
        (
            item
            for item in plan.meals
            if item.day_index == day_index and item.meal == meal
        ),
        None,
    )
    same_day = {item.recipe.id for item in plan.of_day(day_index)}
    last_seen = {
        item.recipe.id: item.day_index
        for item in plan.meals
        if not (item.day_index == day_index and item.meal == meal)
    }

    served = sum(
        item.kcal for item in plan.of_day(day_index) if item is not current
    )
    served_protein = sum(
        item.protein_g for item in plan.of_day(day_index) if item is not current
    )

    return pick(
        candidates,
        meal=meal,
        day_index=day_index,
        kcal_slot=max(0.0, kcal_target - served),
        protein_slot=max(0.0, protein_target - served_protein),
        last_seen=last_seen,
        rng=random.Random(seed),
        exclude=frozenset(same_day),
    )


# ── La liste de courses ────────────────────────────────────────────────────


@dataclass
class ShoppingLine:
    label: str
    quantity_g: float
    food_group: Optional[str] = None


def shopping_list(
    items: Sequence[tuple[str, float, Optional[str]]],
) -> list[ShoppingLine]:
    """Agrège les ingrédients de la semaine — **le vrai intérêt du menu**.

    Sept dîners qui demandent chacun deux cents grammes de riz, c'est un kilo
    quatre de riz, et c'est ça qu'on veut lire au supermarché — pas sept lignes
    de riz.

    L'agrégation se fait sur le **libellé**, pas sur l'identifiant Ciqual :
    deux recettes peuvent pointer sur des lignes Ciqual différentes pour ce qui
    est, dans le caddie, le même paquet de riz.
    """
    totals: dict[str, ShoppingLine] = {}
    for label, quantity_g, group in items:
        key = label.strip().lower()
        line = totals.get(key)
        if line is None:
            totals[key] = ShoppingLine(
                label=label.strip(), quantity_g=quantity_g, food_group=group
            )
        else:
            line.quantity_g += quantity_g

    return sorted(
        totals.values(),
        # Par rayon puis par quantité décroissante : on fait ses courses dans
        # l'ordre des rayons, pas dans l'ordre alphabétique.
        key=lambda line: (line.food_group or "zzz", -line.quantity_g),
    )
