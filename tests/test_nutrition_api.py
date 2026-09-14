"""Nutrition par l'API : journal, cible, menu, pesée, import Ciqual."""
from __future__ import annotations

import io
from datetime import UTC, date, datetime, timedelta

import pytest

from app.models.nutrition import Food
from scripts.import_ciqual import (
    build_food,
    map_columns,
    normalize,
    parse_number,
    read_rows,
)

TODAY = date(2026, 9, 13)


@pytest.fixture
def make_food(db_session):
    async def _make(
        name: str = "Riz blanc cuit",
        code: str = "9999",
        kcal: float = 130.0,
        protein: float = 2.7,
        carb: float = 28.0,
        fat: float = 0.3,
        fiber: float = 0.4,
        group: str = "céréales",
        barcode: str | None = None,
    ) -> Food:
        food = Food(
            source="ciqual",
            source_version="ciqual-2025",
            external_id=code,
            name=name,
            name_normalized=normalize(name),
            food_group=group,
            barcode=barcode,
            kcal_100g=kcal,
            protein_100g=protein,
            carb_100g=carb,
            fat_100g=fat,
            fiber_100g=fiber,
        )
        db_session.add(food)
        await db_session.commit()
        await db_session.refresh(food)
        return food

    return _make


# ── Le journal ─────────────────────────────────────────────────────────────


async def test_a_log_entry_freezes_its_values(auth_client, make_food, db_session):
    """Le cœur du modèle : un bilan de la semaine dernière ne doit pas changer
    parce qu'une base a été mise à jour."""
    food = await make_food()

    created = await auth_client.post(
        "/api/v1/nutrition/log",
        json={"food_id": food.id, "quantity_g": 250, "meal": "lunch", "day": TODAY.isoformat()},
    )

    assert created.status_code == 201
    body = created.json()
    assert body["kcal"] == pytest.approx(325.0, abs=0.5)
    assert body["protein_g"] == pytest.approx(6.8, abs=0.2)

    # La fiche change…
    food.kcal_100g = 400.0
    await db_session.commit()

    # …et la ligne déjà écrite ne bouge pas.
    day = await auth_client.get(f"/api/v1/nutrition/day?day={TODAY.isoformat()}")
    assert day.json()["entries"][0]["kcal"] == pytest.approx(325.0, abs=0.5)


async def test_an_unknown_nutrient_stays_unknown(auth_client, make_food):
    """Un zéro se lirait « cet aliment n'a pas de fibres ». Ce n'est pas pareil."""
    food = await make_food(fiber=None)

    created = await auth_client.post(
        "/api/v1/nutrition/log",
        json={"food_id": food.id, "quantity_g": 100},
    )

    assert created.json()["fiber_g"] is None


async def test_a_log_entry_needs_a_food_or_a_recipe(auth_client):
    response = await auth_client.post("/api/v1/nutrition/log", json={"quantity_g": 100})
    assert response.status_code == 422


async def test_the_day_totals_add_up(auth_client, make_food):
    food = await make_food()
    for quantity in (100, 150):
        await auth_client.post(
            "/api/v1/nutrition/log",
            json={"food_id": food.id, "quantity_g": quantity, "day": TODAY.isoformat()},
        )

    body = (
        await auth_client.get(f"/api/v1/nutrition/day?day={TODAY.isoformat()}")
    ).json()

    assert body["totals"]["kcal"] == pytest.approx(325.0, abs=0.5)
    assert len(body["entries"]) == 2


async def test_a_log_entry_can_be_removed(auth_client, make_food):
    food = await make_food()
    created = await auth_client.post(
        "/api/v1/nutrition/log",
        json={"food_id": food.id, "quantity_g": 100, "day": TODAY.isoformat()},
    )

    removed = await auth_client.delete(
        f"/api/v1/nutrition/log/{created.json()['id']}"
    )
    assert removed.status_code == 204

    body = (
        await auth_client.get(f"/api/v1/nutrition/day?day={TODAY.isoformat()}")
    ).json()
    assert body["entries"] == []


# ── La recherche ───────────────────────────────────────────────────────────


async def test_the_most_frequent_foods_come_first(auth_client, make_food):
    """C'est ce qui fait tenir un repas en vingt secondes."""
    rare = await make_food(name="Riz sauvage cuit", code="1")
    common = await make_food(name="Riz blanc cuit", code="2")

    for _ in range(3):
        await auth_client.post(
            "/api/v1/nutrition/log",
            json={"food_id": common.id, "quantity_g": 100, "day": TODAY.isoformat()},
        )

    hits = (await auth_client.get("/api/v1/nutrition/foods?q=riz")).json()
    assert [hit["id"] for hit in hits][0] == common.id
    assert rare.id in [hit["id"] for hit in hits]


async def test_an_empty_search_gives_the_usual_suspects(auth_client, make_food):
    """L'écran s'ouvre sur ce qu'on mange, pas sur une liste vide."""
    food = await make_food()
    await auth_client.post(
        "/api/v1/nutrition/log",
        json={"food_id": food.id, "quantity_g": 100, "day": TODAY.isoformat()},
    )

    hits = (await auth_client.get("/api/v1/nutrition/foods")).json()
    assert [hit["id"] for hit in hits] == [food.id]
    assert hits[0]["recent_count"] == 1


async def test_the_search_ignores_accents(auth_client, make_food):
    await make_food(name="Céréales complètes")
    hits = (await auth_client.get("/api/v1/nutrition/foods?q=cereales")).json()
    assert hits


# ── La cible ───────────────────────────────────────────────────────────────


async def test_the_target_says_when_it_is_estimated(auth_client):
    """Un profil vide donne une cible dégradée — et elle le dit.

    Une cible refusée faute de taille laisserait l'écran vide, et un écran vide
    ne se remplit jamais.
    """
    body = (await auth_client.get("/api/v1/nutrition/day")).json()
    assert body["target"]["estimated"] is True
    assert body["target"]["reasons"]
    assert body["target"]["kcal"] > 1200


async def test_a_surf_session_raises_the_target(
    auth_client, make_spot, fake_archive
):
    """« Calories suivant entraînement » : c'est là qu'on le voit."""
    fake_archive()
    await auth_client.put(
        "/api/v1/nutrition/profile",
        json={"birth_date": "1990-05-01", "sex": "male", "height_m": 1.78},
    )
    await auth_client.post(
        "/api/v1/nutrition/weight", json={"weight_kg": 75.0, "day": TODAY.isoformat()}
    )

    before = (
        await auth_client.get(f"/api/v1/nutrition/day?day={TODAY.isoformat()}")
    ).json()["target"]

    spot = await make_spot()
    start = datetime.combine(TODAY, datetime.min.time(), tzinfo=UTC) + timedelta(hours=9)
    await auth_client.post(
        "/api/v1/sessions",
        json={
            "spot_id": spot.id,
            "started_at": start.isoformat(),
            "duration_min": 120,
        },
    )

    after = (
        await auth_client.get(f"/api/v1/nutrition/day?day={TODAY.isoformat()}")
    ).json()["target"]

    assert after["expenditure"]["surf_min"] == 120
    assert after["kcal"] > before["kcal"]
    # Une session de deux heures, pas un marathon.
    assert 300 < after["kcal"] - before["kcal"] < 900


async def test_the_goal_moves_the_target(auth_client):
    maintain = (await auth_client.get("/api/v1/nutrition/day")).json()["target"]["kcal"]

    await auth_client.put("/api/v1/nutrition/profile", json={"goal": "cut"})
    cut = (await auth_client.get("/api/v1/nutrition/day")).json()["target"]["kcal"]

    assert cut < maintain


async def test_an_unknown_goal_is_refused(auth_client):
    response = await auth_client.put(
        "/api/v1/nutrition/profile", json={"goal": "jeune-intermittent"}
    )
    assert response.status_code == 422


# ── La pesée et la calibration ─────────────────────────────────────────────


async def test_a_weigh_in_replaces_the_one_of_the_day(auth_client):
    """Se repeser le même jour remplace, comme une mesure d'objectif."""
    await auth_client.post(
        "/api/v1/nutrition/weight", json={"weight_kg": 76.0, "day": TODAY.isoformat()}
    )
    await auth_client.post(
        "/api/v1/nutrition/weight", json={"weight_kg": 75.4, "day": TODAY.isoformat()}
    )

    history = (await auth_client.get("/api/v1/nutrition/weight")).json()
    assert len(history) == 1
    assert history[0]["weight_kg"] == 75.4


async def test_a_single_weigh_in_calibrates_nothing(auth_client):
    response = await auth_client.post(
        "/api/v1/nutrition/weight", json={"weight_kg": 75.0}
    )
    assert response.json()["calibration"]["applied"] is False


async def test_the_latest_weigh_in_drives_the_target(auth_client):
    """Le profil porte un poids saisi une fois ; la balance en porte un tous les
    dimanches. Prendre le profil calculerait la cible sur le poids d'il y a six
    mois."""
    await auth_client.put(
        "/api/v1/nutrition/profile",
        json={"birth_date": "1990-05-01", "sex": "male", "height_m": 1.78},
    )
    await auth_client.post(
        "/api/v1/nutrition/weight", json={"weight_kg": 70.0, "day": TODAY.isoformat()}
    )
    light = (
        await auth_client.get(f"/api/v1/nutrition/day?day={TODAY.isoformat()}")
    ).json()["target"]

    await auth_client.post(
        "/api/v1/nutrition/weight", json={"weight_kg": 90.0, "day": TODAY.isoformat()}
    )
    heavy = (
        await auth_client.get(f"/api/v1/nutrition/day?day={TODAY.isoformat()}")
    ).json()["target"]

    assert heavy["kcal"] > light["kcal"]
    assert heavy["protein_g"] > light["protein_g"]


# ── Recettes et menu ───────────────────────────────────────────────────────


async def test_the_recipes_are_seeded_on_first_read(auth_client):
    """Comme le catalogue d'exercices : semé par l'application, pas par une
    migration — il évoluera."""
    recipes = (await auth_client.get("/api/v1/nutrition/recipes")).json()
    assert len(recipes) >= 35
    assert all(recipe["prep_min"] <= 25 for recipe in recipes)


async def test_seeding_twice_does_not_duplicate(auth_client):
    first = (await auth_client.get("/api/v1/nutrition/recipes")).json()
    second = (await auth_client.get("/api/v1/nutrition/recipes")).json()
    assert len(first) == len(second)


async def test_recipes_pick_up_their_macros_after_a_ciqual_import(
    auth_client, make_food
):
    """Les recettes existent avant l'import, sans macros, et se complètent
    toutes seules le jour où la table arrive."""
    bare = (await auth_client.get("/api/v1/nutrition/recipes")).json()
    assert all(recipe["kcal"] is None for recipe in bare)

    await make_food(name="Riz blanc cuit", code="1", kcal=130)
    await make_food(name="Poulet blanc", code="2", kcal=121, protein=23)
    await make_food(name="Brocoli", code="3", kcal=35, protein=3)

    filled = (await auth_client.get("/api/v1/nutrition/recipes")).json()
    riz = next(item for item in filled if item["slug"] == "riz-poulet-brocoli")
    assert riz["kcal"] is not None
    assert riz["protein_g"] > 0


def _slot(plan, day_index, meal):
    return next(
        item
        for item in plan["items"]
        if item["day_index"] == day_index and item["meal"] == meal
    )


async def test_a_week_can_be_generated_and_regenerated(auth_client):
    plan = (await auth_client.post("/api/v1/nutrition/plan?seed=1")).json()

    # Quatorze créneaux : sept déjeuners, sept dîners. Le petit déjeuner et
    # l'en-cas se journalisent, ils ne se prévoient plus.
    assert len(plan["items"]) == 14
    assert {item["meal"] for item in plan["items"]} == {"lunch", "dinner"}
    assert plan["shopping"]

    target = _slot(plan, 2, "dinner")
    regenerated = (
        await auth_client.post(
            "/api/v1/nutrition/plan/regenerate",
            json={"day_index": 2, "meal": "dinner"},
        )
    ).json()

    assert _slot(regenerated, 2, "dinner")["recipe"]["id"] != target["recipe"]["id"]
    # Le reste de la semaine n'a pas bougé : c'est tout l'intérêt du geste.
    assert len(regenerated["items"]) == 14


async def test_a_breakfast_cannot_be_planned(auth_client):
    """Le menu ne prévoit que le déjeuner et le dîner, et il le dit."""
    await auth_client.post("/api/v1/nutrition/plan?seed=1")
    response = await auth_client.post(
        "/api/v1/nutrition/plan/regenerate",
        json={"day_index": 0, "meal": "breakfast"},
    )
    assert response.status_code == 422


async def test_the_shopping_list_aggregates_the_week(auth_client):
    plan = (await auth_client.post("/api/v1/nutrition/plan?seed=2")).json()
    labels = [line["label"] for line in plan["shopping"]]
    assert len(labels) == len(set(labels)), "un ingrédient apparaît deux fois"


async def test_the_shopping_list_counts_what_is_counted(auth_client):
    """Des œufs se comptent, du riz se pèse, du lait se verse.

    C'est la liste qu'on lit dans le rayon : personne ne demande 165 g d'œufs.
    """
    plan = (await auth_client.post("/api/v1/nutrition/plan?seed=2")).json()
    by_label = {line["label"].lower(): line for line in plan["shopping"]}

    eggs = by_label.get("œufs")
    if eggs is not None:
        assert eggs["unit"] == "piece"
        assert eggs["quantity"] == int(eggs["quantity"])
        assert eggs["unit_label"] in {"œuf", "œufs"}

    rice = by_label.get("riz blanc cuit")
    if rice is not None:
        assert rice["unit"] == "g"

    # Quoi qu'il arrive, la grandeur vraie est toujours là.
    assert all(line["quantity_g"] > 0 for line in plan["shopping"])


async def test_the_day_screen_shows_the_planned_meals(auth_client):
    await auth_client.post("/api/v1/nutrition/plan?seed=3")
    body = (await auth_client.get("/api/v1/nutrition/day")).json()
    assert len(body["planned"]) == 2
    assert {item["meal"] for item in body["planned"]} == {"lunch", "dinner"}


async def test_regenerating_without_a_plan_is_a_404(auth_client):
    response = await auth_client.post(
        "/api/v1/nutrition/plan/regenerate",
        json={"day_index": 0, "meal": "dinner"},
        params={"week": "2030-01-07"},
    )
    assert response.status_code == 404


# ── « Je ne suis pas chez moi » ────────────────────────────────────────────


async def test_a_meal_away_leaves_its_ingredients_at_the_shop(auth_client, make_food):
    """Le seul effet qui compte : on n'achète pas le dîner qu'on prendra
    ailleurs."""
    await make_food(name="Riz blanc cuit", code="1", kcal=130)
    plan = (await auth_client.post("/api/v1/nutrition/plan?seed=4")).json()

    dinner = _slot(plan, 3, "dinner")
    ingredients = {item["label"] for item in dinner["recipe"]["items"]}
    # Ce qui n'est demandé que par ce dîner-là, et par rien d'autre.
    others = {
        item["label"]
        for slot in plan["items"]
        if slot is not dinner and slot["recipe"]
        for item in slot["recipe"]["items"]
    }
    exclusive = ingredients - others

    after = (
        await auth_client.post(
            "/api/v1/nutrition/plan/away",
            json={"day_index": 3, "meal": "dinner", "away": True},
        )
    ).json()

    assert _slot(after, 3, "dinner")["status"] == "away"
    labels = {line["label"] for line in after["shopping"]}
    assert not (exclusive & labels)


async def test_coming_home_puts_a_dish_back(auth_client):
    """Rentrer plus tôt que prévu ne doit pas laisser un trou."""
    await auth_client.post("/api/v1/nutrition/plan?seed=5")
    await auth_client.post(
        "/api/v1/nutrition/plan/away",
        json={"day_index": 1, "meal": "lunch", "away": True},
    )
    back = (
        await auth_client.post(
            "/api/v1/nutrition/plan/away",
            json={"day_index": 1, "meal": "lunch", "away": False},
        )
    ).json()

    slot = _slot(back, 1, "lunch")
    assert slot["status"] == "planned"
    assert slot["recipe"] is not None


async def test_away_survives_a_full_regeneration(auth_client):
    """« Tout régénérer » ne doit pas effacer le fait qu'on dîne dehors jeudi.

    C'est une contrainte de la semaine, pas une proposition de l'algorithme.
    La redéclarer à chaque régénération suffirait à ce qu'on cesse de la
    déclarer.
    """
    await auth_client.post("/api/v1/nutrition/plan?seed=6")
    await auth_client.post(
        "/api/v1/nutrition/plan/away",
        json={"day_index": 4, "meal": "dinner", "away": True},
    )

    again = (await auth_client.post("/api/v1/nutrition/plan?seed=7")).json()
    slot = _slot(again, 4, "dinner")
    assert slot["status"] == "away"
    assert slot["recipe"] is None
    assert len(again["items"]) == 14


async def test_being_away_can_be_declared_before_the_week_exists(auth_client):
    """C'est même le bon ordre : le générateur lira la contrainte au lieu de
    proposer un plat pour rien."""
    plan = (
        await auth_client.post(
            "/api/v1/nutrition/plan/away",
            json={"day_index": 2, "meal": "dinner", "away": True},
        )
    ).json()
    assert _slot(plan, 2, "dinner")["status"] == "away"

    generated = (await auth_client.post("/api/v1/nutrition/plan?seed=8")).json()
    assert _slot(generated, 2, "dinner")["recipe"] is None
    assert len(generated["items"]) == 14


# ── Interchanger ──────────────────────────────────────────────────────────


async def test_two_meals_can_be_swapped(auth_client):
    """Le plat du mercredi soir passe au vendredi. On l'avait choisi : le
    déplacer vaut mieux que le régénérer."""
    plan = (await auth_client.post("/api/v1/nutrition/plan?seed=9")).json()
    wednesday = _slot(plan, 2, "dinner")["recipe"]["id"]
    friday = _slot(plan, 4, "dinner")["recipe"]["id"]

    swapped = (
        await auth_client.post(
            "/api/v1/nutrition/plan/swap",
            json={
                "a": {"day_index": 2, "meal": "dinner"},
                "b": {"day_index": 4, "meal": "dinner"},
            },
        )
    ).json()

    assert _slot(swapped, 2, "dinner")["recipe"]["id"] == friday
    assert _slot(swapped, 4, "dinner")["recipe"]["id"] == wednesday


async def test_swapping_carries_the_away_mark(auth_client):
    """Échanger un dîner prévu avec un soir où l'on n'est pas là, c'est bien
    intervertir les deux soirées."""
    await auth_client.post("/api/v1/nutrition/plan?seed=10")
    await auth_client.post(
        "/api/v1/nutrition/plan/away",
        json={"day_index": 0, "meal": "dinner", "away": True},
    )

    swapped = (
        await auth_client.post(
            "/api/v1/nutrition/plan/swap",
            json={
                "a": {"day_index": 0, "meal": "dinner"},
                "b": {"day_index": 6, "meal": "dinner"},
            },
        )
    ).json()

    assert _slot(swapped, 0, "dinner")["status"] == "planned"
    assert _slot(swapped, 6, "dinner")["status"] == "away"


async def test_swapping_a_slot_with_itself_is_refused(auth_client):
    await auth_client.post("/api/v1/nutrition/plan?seed=11")
    response = await auth_client.post(
        "/api/v1/nutrition/plan/swap",
        json={
            "a": {"day_index": 0, "meal": "dinner"},
            "b": {"day_index": 0, "meal": "dinner"},
        },
    )
    assert response.status_code == 422


async def test_a_chosen_recipe_wins_over_the_draw(auth_client):
    """Le tirage propose, on dispose — y compris une recette étiquetée pour un
    autre repas. Les étiquettes servent au générateur, pas à arbitrer ce que
    quelqu'un a décidé de manger."""
    recipes = (await auth_client.get("/api/v1/nutrition/recipes")).json()
    breakfast = next(item for item in recipes if "breakfast" in item["meals"])
    await auth_client.post("/api/v1/nutrition/plan?seed=12")

    plan = (
        await auth_client.post(
            "/api/v1/nutrition/plan/set",
            json={
                "day_index": 5,
                "meal": "dinner",
                "recipe_id": breakfast["id"],
            },
        )
    ).json()

    assert _slot(plan, 5, "dinner")["recipe"]["id"] == breakfast["id"]


# ── La fiche recette : favori, note, version perso ────────────────────────


async def test_a_recipe_can_be_favourited_and_annotated(auth_client):
    recipes = (await auth_client.get("/api/v1/nutrition/recipes")).json()
    first = recipes[0]

    updated = (
        await auth_client.put(
            f"/api/v1/nutrition/recipes/{first['id']}/note",
            json={"favorite": True, "note": "Sans le piment c'est meilleur."},
        )
    ).json()
    assert updated["favorite"] is True
    assert updated["note"] == "Sans le piment c'est meilleur."

    # Et la note se relit, y compris depuis la liste.
    listed = (await auth_client.get("/api/v1/nutrition/recipes")).json()
    assert listed[0]["id"] == first["id"], "les favorites passent en tête"
    assert listed[0]["favorite"] is True

    only = (
        await auth_client.get("/api/v1/nutrition/recipes?favorite=true")
    ).json()
    assert [item["id"] for item in only] == [first["id"]]


async def test_an_emptied_note_is_a_removed_note(auth_client):
    recipes = (await auth_client.get("/api/v1/nutrition/recipes")).json()
    recipe_id = recipes[0]["id"]
    await auth_client.put(
        f"/api/v1/nutrition/recipes/{recipe_id}/note", json={"note": "à revoir"}
    )
    cleared = (
        await auth_client.put(
            f"/api/v1/nutrition/recipes/{recipe_id}/note", json={"note": "   "}
        )
    ).json()
    assert cleared["note"] is None


async def test_editing_a_catalog_recipe_forks_it(auth_client, make_food):
    """**Le point délicat du lot.**

    Le semis remplace les ingrédients en bloc sur les recettes du catalogue, et
    il rejoue après chaque import Ciqual : une modification écrite directement
    sur une ligne semée disparaîtrait sans un mot, des semaines plus tard. Donc
    on copie.
    """
    await make_food(name="Riz blanc cuit", code="1", kcal=130)
    recipes = (await auth_client.get("/api/v1/nutrition/recipes")).json()
    original = next(item for item in recipes if item["slug"] == "riz-poulet-brocoli")

    forked = (
        await auth_client.patch(
            f"/api/v1/nutrition/recipes/{original['id']}",
            json={
                "name": "Riz poulet brocoli (ma version)",
                "items": [
                    {"label": "Riz blanc cuit", "quantity_g": 300},
                    {"label": "Brocoli", "quantity_g": 200},
                ],
            },
        )
    ).json()

    assert forked["id"] != original["id"]
    assert forked["source"] == "user"
    assert forked["based_on_id"] == original["id"]
    assert forked["name"] == "Riz poulet brocoli (ma version)"

    # L'original est intact : le catalogue est commun.
    again = (
        await auth_client.get(f"/api/v1/nutrition/recipes/{original['id']}")
    ).json()
    assert again["name"] == original["name"]
    assert len(again["items"]) == len(original["items"])


async def test_a_forked_recipe_replaces_the_original_in_this_week(auth_client):
    """Le menu de la semaine suit la version perso : c'est le plat qu'on va
    cuisiner."""
    plan = (await auth_client.post("/api/v1/nutrition/plan?seed=13")).json()
    slot = _slot(plan, 0, "dinner")
    original_id = slot["recipe"]["id"]

    forked = (
        await auth_client.patch(
            f"/api/v1/nutrition/recipes/{original_id}",
            json={"prep_min": 12},
        )
    ).json()

    after = (await auth_client.get("/api/v1/nutrition/plan")).json()
    assert _slot(after, 0, "dinner")["recipe"]["id"] == forked["id"]


async def test_a_note_follows_its_recipe_when_it_is_forked(auth_client):
    """Une note restée sur l'original se lirait comme une note perdue."""
    recipes = (await auth_client.get("/api/v1/nutrition/recipes")).json()
    original = recipes[0]
    await auth_client.put(
        f"/api/v1/nutrition/recipes/{original['id']}/note",
        json={"favorite": True, "note": "cuire le riz 2 min de plus"},
    )

    forked = (
        await auth_client.patch(
            f"/api/v1/nutrition/recipes/{original['id']}", json={"prep_min": 9}
        )
    ).json()

    assert forked["note"] == "cuire le riz 2 min de plus"
    assert forked["favorite"] is True


async def test_a_recipe_can_be_written_from_scratch(auth_client, make_food):
    await make_food(name="Riz blanc cuit", code="1", kcal=130, protein=2.7)

    created = (
        await auth_client.post(
            "/api/v1/nutrition/recipes",
            json={
                "name": "Riz du dimanche",
                "meals": ["dinner"],
                "prep_min": 12,
                "steps": "Rien de compliqué.",
                "items": [{"label": "Riz blanc cuit", "quantity_g": 200}],
            },
        )
    ).json()

    assert created["source"] == "user"
    # Préfixé : une recette perso ne peut pas occuper le slug d'une recette
    # que le catalogue ajoutera demain.
    assert created["slug"] == "perso-riz-du-dimanche"
    # Les macros ne sont jamais saisies : elles se déduisent des ingrédients.
    assert created["kcal"] == pytest.approx(260, abs=1)


async def test_a_recipe_without_ingredients_is_refused(auth_client):
    """Sans ingrédients, pas de macros ; sans macros, pas de menu."""
    response = await auth_client.post(
        "/api/v1/nutrition/recipes", json={"name": "Rien"}
    )
    assert response.status_code == 422


async def test_the_catalog_cannot_be_deleted(auth_client):
    """Il est commun. On le met de côté en ne le mettant jamais au menu."""
    recipes = (await auth_client.get("/api/v1/nutrition/recipes")).json()
    response = await auth_client.delete(
        f"/api/v1/nutrition/recipes/{recipes[0]['id']}"
    )
    assert response.status_code == 409


async def test_a_personal_recipe_does_not_stop_the_catalog_from_being_seeded(
    auth_client,
):
    """Le semis compte le **catalogue**, pas la table entière.

    Sinon une recette écrite avant le premier accès à l'écran suffirait à le
    convaincre qu'il a déjà tourné : la banque tiendrait en un plat, et le menu
    de la semaine proposerait sept fois le même.
    """
    await auth_client.post(
        "/api/v1/nutrition/recipes",
        json={
            "name": "Tout premier plat",
            "meals": ["dinner"],
            "items": [{"label": "Riz blanc cuit", "quantity_g": 150}],
        },
    )
    recipes = (await auth_client.get("/api/v1/nutrition/recipes")).json()
    assert len(recipes) >= 35


async def test_deleting_a_recipe_empties_its_slots_instead_of_hiding_them(
    auth_client,
):
    """Un menu avec un dîner « à choisir » se corrige ; un menu où le jeudi a
    silencieusement perdu sa ligne se relit trois fois."""
    # Le catalogue est semé d'abord : c'est le menu complet qu'on veut voir
    # survivre à la suppression, pas une semaine à un seul plat.
    await auth_client.get("/api/v1/nutrition/recipes")
    created = (
        await auth_client.post(
            "/api/v1/nutrition/recipes",
            json={
                "name": "Plat de passage",
                "meals": ["dinner"],
                "items": [{"label": "Riz blanc cuit", "quantity_g": 150}],
            },
        )
    ).json()

    await auth_client.post("/api/v1/nutrition/plan?seed=14")
    await auth_client.post(
        "/api/v1/nutrition/plan/set",
        json={"day_index": 6, "meal": "dinner", "recipe_id": created["id"]},
    )

    assert (
        await auth_client.delete(f"/api/v1/nutrition/recipes/{created['id']}")
    ).status_code == 204

    plan = (await auth_client.get("/api/v1/nutrition/plan")).json()
    slot = _slot(plan, 6, "dinner")
    assert slot["recipe"] is None
    assert slot["status"] == "planned"
    assert len(plan["items"]) == 14


async def test_a_logged_recipe_counts_as_cooked(auth_client):
    recipes = (await auth_client.get("/api/v1/nutrition/recipes")).json()
    recipe_id = recipes[0]["id"]

    await auth_client.post(
        "/api/v1/nutrition/log",
        json={"recipe_id": recipe_id, "meal": "dinner", "servings": 1},
    )
    detail = (
        await auth_client.get(f"/api/v1/nutrition/recipes/{recipe_id}")
    ).json()
    assert detail["cooked_count"] == 1


async def test_a_recipe_says_how_its_ingredients_are_bought(auth_client):
    """Deux œufs, pas 110 g. Les grammes restent à côté : la conversion est une
    moyenne, et une moyenne présentée seule passerait pour une mesure."""
    recipes = (await auth_client.get("/api/v1/nutrition/recipes")).json()
    with_eggs = next(
        (
            recipe
            for recipe in recipes
            if any(item["label"] == "Œufs" for item in recipe["items"])
        ),
        None,
    )
    assert with_eggs is not None
    eggs = next(item for item in with_eggs["items"] if item["label"] == "Œufs")
    assert eggs["unit"] == "piece"
    assert eggs["quantity"] >= 1
    assert eggs["quantity_g"] > 0


# ── L'import Ciqual ────────────────────────────────────────────────────────

CIQUAL_EXTRACT = (
    "alim_code;alim_nom_fr;alim_grp_nom_fr;"
    "Energie, Règlement UE N° 1169/2011 (kcal/100 g);"
    "Protéines, N x facteur de Jones (g/100 g);"
    "Glucides (g/100 g);Lipides (g/100 g);Fibres alimentaires (g/100 g)\n"
    "9000;Riz blanc cuit;céréales;130;2,7;28,0;0,3;0,4\n"
    "9001;Huile d'olive;matières grasses;899;traces;0;99,9;-\n"
    "9002;Eau du robinet;boissons;0;0;0;0;0\n"
    "9003;;;;;;;\n"
)


def _extract_rows():
    return list(read_rows(_write_extract()))


def _write_extract():
    from pathlib import Path
    import tempfile

    path = Path(tempfile.mkdtemp()) / "ciqual.csv"
    path.write_text(CIQUAL_EXTRACT, encoding="utf-8")
    return path


def test_ciqual_columns_are_found_by_fragments():
    """Ciqual change sa ponctuation entre deux millésimes : chercher un
    intitulé exact casserait au premier."""
    rows = _extract_rows()
    mapping = map_columns(list(rows[0].keys()))

    assert "kcal" in mapping["kcal_100g"].lower()
    assert mapping["external_id"] == "alim_code"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("130", 130.0),
        ("2,7", 2.7),
        # Négligeable, donc zéro.
        ("traces", 0.0),
        ("< 0,1", 0.0),
        # Non mesuré, donc inconnu — jamais zéro : un zéro affirmerait que
        # l'aliment n'en contient pas.
        ("-", None),
        ("", None),
        (None, None),
    ],
)
def test_ciqual_values_are_read_for_what_they_are(raw, expected):
    assert parse_number(raw) == expected


def test_a_ciqual_row_becomes_a_food():
    rows = _extract_rows()
    mapping = map_columns(list(rows[0].keys()))

    food = build_food(rows[0], mapping, "ciqual-2025")
    assert food["name"] == "Riz blanc cuit"
    assert food["name_normalized"] == "riz blanc cuit"
    assert food["kcal_100g"] == 130.0
    assert food["fiber_100g"] == 0.4

    olive = build_food(rows[1], mapping, "ciqual-2025")
    assert olive["protein_100g"] == 0.0
    assert olive["fiber_100g"] is None


def test_a_row_without_a_name_is_skipped():
    """Une ligne sans nom n'est pas un aliment, même avec un code."""
    rows = _extract_rows()
    mapping = map_columns(list(rows[0].keys()))
    assert build_food(rows[3], mapping, "ciqual-2025") is None
