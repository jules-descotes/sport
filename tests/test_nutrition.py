"""Nutrition — la cible, sa correction par la balance, le menu, le journal.

La cible calorique est un calcul qu'on ne peut pas vérifier à l'œil : trois
termes s'additionnent, un quatrième se corrige tout seul, et une erreur de
signe passerait inaperçue pendant des mois. C'est exactement ce que les tests
sont là pour tenir.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.services.food_units import to_shopping_unit, unit_key
from app.services.meal_plan import (
    MEAL_SHARE,
    PLANNED_MEALS,
    Candidate,
    day_share,
    generate_week,
    regenerate_meal,
    shopping_list,
)
from app.services.nutrition import (
    GOAL_KCAL,
    KCAL_PER_KG,
    MAX_CALIBRATION_STEP_KCAL,
    MIN_CALIBRATION_DAYS,
    RESTING_MET,
    activity_kcal,
    basal_metabolic_rate,
    compute_calibration,
    macro_split,
    surf_met,
)


# ── Mifflin-St Jeor ────────────────────────────────────────────────────────


def test_mifflin_on_three_profiles() -> None:
    """Trois profils, trois valeurs connues.

    La formule : 10 × poids + 6,25 × taille − 5 × âge, plus 5 chez l'homme et
    moins 161 chez la femme.
    """
    # Homme, 75 kg, 178 cm, 35 ans.
    assert basal_metabolic_rate(75, 178, 35, "male") == pytest.approx(1692.5, abs=0.5)
    # Femme, 62 kg, 166 cm, 30 ans.
    assert basal_metabolic_rate(62, 166, 30, "female") == pytest.approx(
        1346.5, abs=0.5
    )
    # Homme, 90 kg, 185 cm, 45 ans.
    assert basal_metabolic_rate(90, 185, 45, "male") == pytest.approx(1836.25, abs=0.5)


def test_an_unknown_sex_takes_the_average() -> None:
    """La seule réponse honnête à un champ vide.

    L'écart entre les deux constantes est de 166 kcal, du même ordre que ce
    que la calibration rattrape en deux semaines — supposer un sexe serait à
    la fois inutile et faux.
    """
    male = basal_metabolic_rate(75, 178, 35, "male")
    female = basal_metabolic_rate(75, 178, 35, "female")
    unknown = basal_metabolic_rate(75, 178, 35, None)

    assert unknown == pytest.approx((male + female) / 2, abs=0.1)


# ── La dépense d'une session ───────────────────────────────────────────────


def test_the_surf_met_decreases_with_duration() -> None:
    """La première heure est une heure de rame, la troisième une heure d'attente."""
    assert surf_met(60) > surf_met(120) > surf_met(240)


def test_a_zero_length_session_costs_nothing() -> None:
    assert surf_met(0) == 0.0
    assert activity_kcal(5.0, 75, 0) == 0.0


def test_the_resting_metabolism_is_subtracted() -> None:
    """Une heure à 5 MET coûte 4 × poids de plus que rien faire, pas 5.

    Oublier ce « −1 » surestime la dépense de 20 à 30 % — et sur une année de
    surf, ça fait plusieurs kilos de cible qui n'existent pas.
    """
    assert activity_kcal(5.0, 75, 60) == pytest.approx((5.0 - RESTING_MET) * 75)


def test_an_activity_below_resting_costs_nothing() -> None:
    """Pas de dépense négative : rester assis ne fait pas maigrir."""
    assert activity_kcal(0.5, 75, 60) == 0.0


def test_a_two_hour_session_costs_a_real_meal() -> None:
    """Le garde-fou de plausibilité : entre 400 et 800 kcal, pas 2 000."""
    kcal = activity_kcal(surf_met(120), 75, 120)
    assert 400 < kcal < 800


# ── La répartition des macros ──────────────────────────────────────────────


def test_protein_follows_body_weight_not_calories() -> None:
    """1,8 g/kg est 1,8 g/kg, qu'on soit en déficit ou non."""
    lean, _, _ = macro_split(2000, 75, 1.8, 0.28)
    full, _, _ = macro_split(3200, 75, 1.8, 0.28)
    assert lean == full == 135


def test_carbs_absorb_the_rest() -> None:
    """Ce sont eux la variable d'ajustement — le bon choix quand on rame."""
    protein, carb, fat = macro_split(2800, 75, 1.8, 0.28)
    total = protein * 4 + carb * 4 + fat * 9
    assert total == pytest.approx(2800, abs=10)


def test_macros_never_go_negative() -> None:
    """Une cible basse avec des protéines hautes ne doit pas rendre −30 g."""
    protein, carb, fat = macro_split(1200, 95, 2.5, 0.35)
    assert min(protein, carb, fat) >= 0


# ── La recalibration ───────────────────────────────────────────────────────


def test_no_calibration_before_two_weeks() -> None:
    """Une variation de poids sur dix jours est de l'eau, pas du tissu."""
    result = compute_calibration(
        current_kcal=0, days=10, weight_change_kg=-1.0, goal_kcal=-350
    )
    assert result.applied is False
    assert str(MIN_CALIBRATION_DAYS) in result.reason


def test_no_calibration_when_the_log_is_half_empty() -> None:
    """L'écart mesurerait ce qui n'a pas été noté, pas ce qui a été mangé.

    Corriger sur ce signal-là reviendrait à punir l'oubli.
    """
    result = compute_calibration(
        current_kcal=0,
        days=21,
        weight_change_kg=-1.0,
        goal_kcal=-350,
        logged_ratio=0.3,
    )
    assert result.applied is False
    assert "journalis" in result.reason


def test_a_stalled_weight_on_a_deficit_lowers_the_target() -> None:
    """Trois semaines de déficit et zéro kilo : la cible était trop haute.

    Le déficit visé était de 350 kcal par jour ; il ne s'est rien passé, donc
    la cible doit descendre — c'est le cœur du mécanisme.
    """
    result = compute_calibration(
        current_kcal=0, days=21, weight_change_kg=0.0, goal_kcal=-350
    )
    assert result.applied is True
    assert result.adjustment_kcal < 0


def test_losing_faster_than_planned_raises_the_target() -> None:
    """Un kilo de plus que prévu : on mange trop peu, la cible monte.

    C'est le sens qui compte, et il n'est pas intuitif — se tromper ici ferait
    diverger la cible au lieu de la faire converger, et l'erreur ne se verrait
    qu'au bout de trois pesées.
    """
    expected = GOAL_KCAL["cut"] * 21 / KCAL_PER_KG

    faster = compute_calibration(
        current_kcal=0,
        days=21,
        weight_change_kg=expected - 1.0,
        goal_kcal=GOAL_KCAL["cut"],
    )
    assert faster.applied is True
    assert faster.adjustment_kcal > 0

    slower = compute_calibration(
        current_kcal=0,
        days=21,
        weight_change_kg=expected + 1.0,
        goal_kcal=GOAL_KCAL["cut"],
    )
    assert slower.adjustment_kcal < 0


def test_the_correction_is_capped_per_pass() -> None:
    """Une correction de 600 kcal d'un coup ferait osciller la cible.

    On converge, on ne saute pas d'une pesée à l'autre.
    """
    result = compute_calibration(
        current_kcal=0, days=14, weight_change_kg=3.0, goal_kcal=0
    )
    assert abs(result.adjustment_kcal) <= MAX_CALIBRATION_STEP_KCAL


def test_three_simulated_weeks_converge() -> None:
    """Trois passes doivent rapprocher la cible, pas la faire osciller.

    On simule un métabolisme réel plus bas que la formule de 300 kcal : le
    poids ne bouge pas alors qu'on vise un déficit, et la calibration doit
    descendre à chaque passe sans jamais repartir vers le haut.
    """
    calibration = 0.0
    adjustments = []
    for _ in range(3):
        result = compute_calibration(
            current_kcal=calibration,
            days=21,
            weight_change_kg=0.0,
            goal_kcal=GOAL_KCAL["cut"],
        )
        calibration = result.new_calibration_kcal
        adjustments.append(result.adjustment_kcal)

    assert all(value < 0 for value in adjustments)
    assert calibration < -300


# ── Le générateur de menu ──────────────────────────────────────────────────


def _candidate(index: int, meal: str, kcal: float, protein: float) -> Candidate:
    return Candidate(
        id=index,
        slug=f"r{index}",
        name=f"Recette {index}",
        meals=(meal,),
        tags=(),
        prep_min=10,
        kcal=kcal,
        protein_g=protein,
    )


def _bank() -> list[Candidate]:
    """Six recettes par repas, de tailles variées."""
    bank: list[Candidate] = []
    index = 1
    for meal, base in (
        ("breakfast", 450),
        ("lunch", 700),
        ("snack", 250),
        ("dinner", 650),
    ):
        for step in range(6):
            bank.append(
                _candidate(index, meal, base + step * 80, 20 + step * 6)
            )
            index += 1
    return bank


def test_a_week_plans_lunch_and_dinner_only() -> None:
    """Quatorze créneaux, pas vingt-huit.

    Le petit déjeuner et l'en-cas continuent de se journaliser ; ils ne se
    prévoient plus. Un en-cas planifié est un en-cas qu'on ne mange pas.
    """
    plan = generate_week(_bank(), kcal_target=2600, protein_target=140, seed=1)
    assert len(plan.meals) == 7 * len(PLANNED_MEALS)
    for day in range(7):
        assert {item.meal for item in plan.of_day(day)} == set(PLANNED_MEALS)


def test_the_two_planned_meals_keep_their_share_of_the_day() -> None:
    """Ils portent leur part de la cible — 65 % — et pas la journée entière.

    C'est ce que vérifie ce test, et c'est le piège du passage à deux repas :
    en retirant les parts du petit déjeuner et de l'en-cas de la répartition,
    le générateur aurait proposé des dîners à 900 kcal. Elles restent dans
    `MEAL_SHARE` exactement pour ça.
    """
    share = MEAL_SHARE["lunch"] + MEAL_SHARE["dinner"]
    plan = generate_week(_bank(), kcal_target=2600, protein_target=140, seed=7)
    for day in range(7):
        assert 0.8 * share * 2600 <= plan.kcal_of_day(day) <= 1.2 * share * 2600


def test_a_slot_marked_away_gets_no_dish() -> None:
    """« Jeudi soir je ne suis pas là » se pose **avant** la génération.

    Sans ça, le générateur proposerait un plat pour un repas qu'on ne prendra
    pas chez soi, et la liste de courses l'achèterait.
    """
    plan = generate_week(
        _bank(),
        kcal_target=2600,
        protein_target=140,
        seed=1,
        skip=frozenset({(3, "dinner"), (5, "lunch")}),
    )
    slots = {(item.day_index, item.meal) for item in plan.meals}
    assert (3, "dinner") not in slots
    assert (5, "lunch") not in slots
    assert len(plan.meals) == 7 * len(PLANNED_MEALS) - 2


def test_an_away_dinner_does_not_inflate_the_lunch() -> None:
    """Dîner dehors n'est pas une raison de prévoir un déjeuner à 900 kcal.

    La part du créneau sauté est **retirée**, pas reversée sur le repas
    suivant : la cible d'une journée où l'on mange dehors le soir n'est pas la
    cible d'une journée normale.
    """
    normal = generate_week(_bank(), kcal_target=2600, protein_target=140, seed=1)
    away = generate_week(
        _bank(),
        kcal_target=2600,
        protein_target=140,
        seed=1,
        skip=frozenset({(2, "dinner")}),
    )

    lunches = [item for item in away.of_day(2) if item.meal == "lunch"]
    assert len(lunches) == 1

    # Le déjeuner d'un jour où l'on dîne dehors n'est pas plus gros que le plus
    # gros déjeuner d'une semaine normale : il a gardé sa part, il n'a pas
    # hérité de celle du dîner.
    biggest_normal_lunch = max(
        item.kcal for item in normal.meals if item.meal == "lunch"
    )
    assert lunches[0].kcal <= biggest_normal_lunch
    assert away.kcal_of_day(2) < normal.kcal_of_day(2)


def test_the_same_seed_gives_the_same_week() -> None:
    """Un générateur non reproductible est indébogable."""
    first = generate_week(_bank(), kcal_target=2600, protein_target=140, seed=42)
    second = generate_week(_bank(), kcal_target=2600, protein_target=140, seed=42)
    assert [item.recipe.id for item in first.meals] == [
        item.recipe.id for item in second.meals
    ]


def test_variety_avoids_the_same_dish_two_days_running() -> None:
    """Le poisson trois soirs de suite est ce que la contrainte existe pour éviter."""
    plan = generate_week(_bank(), kcal_target=2600, protein_target=140, seed=3)
    dinners = [
        item.recipe.id
        for item in sorted(plan.meals, key=lambda meal: meal.day_index)
        if item.meal == "dinner"
    ]
    assert all(a != b for a, b in zip(dinners, dinners[1:]))


def test_a_bank_without_macros_still_produces_a_week() -> None:
    """Tant que Ciqual n'est pas importé, aucune recette n'a de macros.

    Refuser de générer laisserait l'écran vide, et un écran vide ne se remplit
    jamais.
    """
    bare = [
        Candidate(
            id=index,
            slug=f"b{index}",
            name=f"B{index}",
            meals=(meal,),
            tags=(),
            prep_min=10,
        )
        for index, meal in enumerate(PLANNED_MEALS * 3, start=1)
    ]
    plan = generate_week(bare, kcal_target=2600, protein_target=140, seed=1)
    assert len(plan.meals) == 7 * len(PLANNED_MEALS)


def test_the_covered_share_never_climbs_back_to_a_whole_day() -> None:
    """0,65 en temps normal, moins quand on mange dehors — jamais 1.

    C'est la fonction qui accorde la génération et le remplacement. Si le
    bouton « un autre plat » visait la journée entière alors que la génération
    vise 65 %, chaque tap proposerait plus gros que ce qu'il remplace, et le
    menu dériverait vers le haut à mesure qu'on le corrige.
    """
    assert day_share() == pytest.approx(
        MEAL_SHARE["lunch"] + MEAL_SHARE["dinner"]
    )
    assert day_share(["dinner"]) == pytest.approx(MEAL_SHARE["lunch"])
    assert day_share(["lunch", "dinner"]) == 0.0
    assert day_share() < 1.0


def test_regenerating_a_meal_proposes_something_else() -> None:
    """Sinon le bouton ne sert à rien."""
    bank = _bank()
    plan = generate_week(bank, kcal_target=2600, protein_target=140, seed=5)
    current = next(
        item for item in plan.meals if item.day_index == 2 and item.meal == "dinner"
    )

    chosen = regenerate_meal(
        plan,
        bank,
        day_index=2,
        meal="dinner",
        kcal_target=2600,
        protein_target=140,
    )

    assert chosen is not None
    assert chosen.id != current.recipe.id


# ── La liste de courses ────────────────────────────────────────────────────


def test_the_shopping_list_aggregates_by_ingredient() -> None:
    """Sept fois deux cents grammes de riz font un kilo quatre, pas sept lignes."""
    lines = shopping_list(
        [("Riz blanc cuit", 200, "céréales")] * 7
        + [("Brocoli", 180, "légumes")]
    )

    rice = next(line for line in lines if line.label == "Riz blanc cuit")
    assert rice.quantity_g == pytest.approx(1400)
    assert len(lines) == 2


def test_the_shopping_list_is_case_insensitive() -> None:
    """« Riz » et « riz » sont le même paquet dans le caddie."""
    lines = shopping_list([("Riz", 200, None), ("riz", 100, None)])
    assert len(lines) == 1
    assert lines[0].quantity_g == 300


def test_the_shopping_list_is_ordered_by_aisle() -> None:
    """On fait ses courses dans l'ordre des rayons, pas dans l'ordre alphabétique."""
    lines = shopping_list(
        [
            ("Pomme", 100, "fruits"),
            ("Riz", 100, "céréales"),
            ("Sel", 5, None),
        ]
    )
    assert [line.food_group for line in lines] == ["céréales", "fruits", None]


# ── Les unités d'achat ─────────────────────────────────────────────────────


def test_eggs_are_counted_not_weighed() -> None:
    """Personne n'a jamais demandé 165 g d'œufs à la caisse."""
    quantity = to_shopping_unit("Œufs", 165)
    assert quantity.unit == "piece"
    assert quantity.quantity == 3
    assert quantity.unit_label == "œufs"
    # La grandeur vraie ne bouge pas : la pièce est un affichage.
    assert quantity.quantity_g == 165


def test_a_piece_is_rounded_up_never_down() -> None:
    """Deux virgule sept œufs font trois œufs.

    Arrondir au plus proche ferait manquer un ingrédient une fois sur deux, ce
    qui est la seule façon pour une liste de courses d'être vraiment inutile.
    """
    assert to_shopping_unit("Œufs", 150).quantity == 3
    assert to_shopping_unit("Banane", 80).quantity == 1
    # Jamais zéro : cinq grammes de quelque chose qui se compte, ça s'achète.
    assert to_shopping_unit("Carotte", 5).quantity == 1


def test_a_whole_piece_stays_a_whole_piece() -> None:
    """Deux œufs pile font deux œufs, pas trois. L'arrondi ne doit pas mordre
    sur la valeur exacte à cause d'un flottant."""
    assert to_shopping_unit("Œufs", 110).quantity == 2
    assert to_shopping_unit("Courgette", 400).quantity == 2


def test_the_singular_is_used_for_one() -> None:
    """« 1 bananes » se lit comme un bug, parce que c'en est un."""
    assert to_shopping_unit("Banane", 100).unit_label == "banane"
    assert to_shopping_unit("Banane", 300).unit_label == "bananes"


def test_the_ligature_and_the_plural_find_the_same_entry() -> None:
    """`NFD` ne décompose pas « œ » : sans substitution explicite, l'ingrédient
    le plus fréquent du catalogue ne serait jamais reconnu.

    Et le pluriel se cherche en seconde passe plutôt qu'en normalisant : la
    règle qui fait de « carottes » une « carotte » ferait d'« ananas » un
    « anana », et l'ananas ne serait plus jamais trouvé le jour où on
    l'ajouterait à la table.
    """
    assert unit_key("Œufs") == "oeufs"
    assert to_shopping_unit("Œufs", 110).unit == "piece"
    assert to_shopping_unit("Carottes", 160).quantity == 2
    assert unit_key("Ananas") == "ananas"


def test_milk_is_bought_by_the_litre() -> None:
    """« 1,8 kg de lait » se lit mal. « 1,8 L » se lit tout seul."""
    quantity = to_shopping_unit("Lait demi-écrémé", 1750)
    assert quantity.unit == "ml"
    assert quantity.quantity == 1700


def test_oil_is_not_water() -> None:
    """Soixante grammes d'huile font 65 ml, pas 60. La densité est dans la
    table parce qu'elle ne change rien au caddie mais tout à l'honnêteté."""
    quantity = to_shopping_unit("Huile d'olive", 60)
    assert quantity.unit == "ml"
    assert quantity.quantity == 70


def test_everything_else_stays_in_grams() -> None:
    """Le riz, le poulet et le fromage s'achètent au poids. C'est le défaut, et
    c'est le bon comportement pour les trois quarts des lignes."""
    for label in ("Riz blanc cuit", "Blanc de poulet", "Feta"):
        assert to_shopping_unit(label, 300).unit == "g"


def test_the_aggregation_happens_before_the_rounding() -> None:
    """Deux recettes à un œuf et demi font trois œufs, pas quatre.

    On arrondit **une fois**, à la fin, sur le total. Arrondir chaque recette
    d'abord ajouterait un œuf par recette.
    """
    lines = shopping_list([("Œufs", 82.5, None), ("Œufs", 82.5, None)])
    assert len(lines) == 1
    assert lines[0].quantity == 3
    assert lines[0].unit_label == "œufs"
