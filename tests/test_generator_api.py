"""Composer une séance depuis l'app — les routes, l'éligibilité, les formules.

Ce qui est protégé ici :

- **la règle E.2 du 13/09**, dans les deux sens : un exercice sans nom français
  ou sans image n'est jamais proposé, et il reste consultable ;
- le **niveau corrigé à la main** est persisté et gagne sur la déduction ;
- les formules sont **recomposées** avec des exercices éligibles, et ce qui a
  été remplacé est dit.
"""
from __future__ import annotations

from typing import Optional

import pytest

from app.models.exercise import Exercise
from app.models.formula import Formula, FormulaItem


async def _exercise(
    db_session,
    slug: str,
    *,
    group: str = "abdos",
    pattern: str = "gainage-statique",
    equipment: str = "aucun",
    difficulty: int = 3,
    effort: str = "temps",
    french: Optional[str] = "Exercice",
    image: Optional[str] = "https://example.test/img.png",
    source: str = "free-exercise-db",
) -> Exercise:
    exercise = Exercise(
        slug=slug,
        name=slug.replace("-", " ").title(),
        name_normalized=slug.replace("-", " "),
        name_fr=french,
        category="core",
        muscle_group="ceinture abdominale",
        image_url=image,
        source=source,
        license="Public Domain (Unlicense)",
        group_key=group,
        pattern=pattern,
        equipment=equipment,
        difficulty=difficulty,
        effort_kind=effort,
    )
    db_session.add(exercise)
    await db_session.commit()
    await db_session.refresh(exercise)
    return exercise


async def _library(db_session) -> None:
    """De quoi composer : quatre patterns, tous éligibles."""
    await _exercise(db_session, "gainage-a", pattern="gainage-statique")
    await _exercise(db_session, "anti-a", pattern="anti-rotation", effort="reps")
    await _exercise(db_session, "flexion-a", pattern="flexion", effort="reps")
    await _exercise(db_session, "extension-a", pattern="extension", effort="reps")
    await _exercise(db_session, "mobilite-a", pattern="mobilite")


# ── Le niveau ──────────────────────────────────────────────────────────────


async def test_levels_list_every_group_even_the_untouched_ones(auth_client) -> None:
    """Le cacher donnerait l'impression qu'il n'existe pas — alors que c'est
    celui par lequel commencer."""
    response = await auth_client.get("/api/v1/training/levels")

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 8
    assert {row["group"] for row in body} >= {"abdos", "dos", "jambes"}
    assert all(row["level"] == 2 and row["origin"] == "defaut" for row in body)
    # Le libellé français voyage avec : l'écran ne porte pas une seconde copie
    # du dictionnaire (règle E.3).
    assert {"Abdos", "Épaules", "Corps entier"} <= {
        row["group_label"] for row in body
    }


async def test_a_manual_level_is_persisted_and_wins(auth_client) -> None:
    saved = await auth_client.put(
        "/api/v1/training/levels", json={"group": "abdos", "level": 5}
    )

    assert saved.status_code == 200, saved.text
    abdos = next(row for row in saved.json() if row["group"] == "abdos")
    assert abdos["level"] == 5
    assert abdos["origin"] == "manuel"

    again = await auth_client.get("/api/v1/training/levels")
    assert next(
        row for row in again.json() if row["group"] == "abdos"
    )["origin"] == "manuel"


async def test_a_null_level_hands_the_deduction_back(auth_client) -> None:
    """« En fait non, reprends ce que tu vois ».

    Sans ce geste, une correction posée un dimanche resterait vraie pour
    toujours.
    """
    await auth_client.put(
        "/api/v1/training/levels", json={"group": "abdos", "level": 5}
    )

    cleared = await auth_client.put(
        "/api/v1/training/levels", json={"group": "abdos", "level": None}
    )

    abdos = next(row for row in cleared.json() if row["group"] == "abdos")
    assert abdos["origin"] == "defaut"
    assert abdos["level"] == 2


async def test_an_unknown_group_is_refused(auth_client) -> None:
    response = await auth_client.put(
        "/api/v1/training/levels", json={"group": "cerveau", "level": 3}
    )

    assert response.status_code == 422


# ── Composer ───────────────────────────────────────────────────────────────


async def test_compose_returns_three_distinct_sessions(
    auth_client, db_session
) -> None:
    await _library(db_session)

    response = await auth_client.post(
        "/api/v1/training/compose",
        json={"groups": ["abdos"], "duration_min": 15, "equipment": []},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["workouts"]) == 3
    signatures = {
        tuple(item["exercise"]["id"] for item in workout["items"])
        for workout in body["workouts"]
    }
    assert len(signatures) == 3
    # Chaque séance dit **pourquoi** elle est celle-là. Une proposition qu'on ne
    # comprend pas se remplace au hasard, et on finit par ne plus la lire.
    assert all(workout["principle"] for workout in body["workouts"])


async def test_every_visible_string_is_french(auth_client, db_session) -> None:
    """Règle E.3 : tout ce qui est visible dans Training est en français."""
    await _library(db_session)

    body = (
        await auth_client.post(
            "/api/v1/training/compose",
            json={"groups": ["abdos"], "duration_min": 15},
        )
    ).json()

    for workout in body["workouts"]:
        for item in workout["items"]:
            exercise = item["exercise"]
            assert exercise["name_fr"]
            assert exercise["group_label"] == "Abdos"
            assert exercise["pattern_label"] != exercise["pattern"]
            assert exercise["equipment_label"] == "Aucun"


async def test_an_exercise_without_a_french_name_never_shows_up(
    auth_client, db_session
) -> None:
    await _library(db_session)
    await _exercise(
        db_session, "sans-francais", pattern="flexion", french=None, effort="reps"
    )

    body = (
        await auth_client.post(
            "/api/v1/training/compose",
            json={"groups": ["abdos"], "duration_min": 25},
        )
    ).json()

    slugs = {
        item["exercise"]["slug"]
        for workout in body["workouts"]
        for item in workout["items"]
    }
    assert "sans-francais" not in slugs


async def test_an_exercise_without_an_image_never_shows_up(
    auth_client, db_session
) -> None:
    await _library(db_session)
    await _exercise(
        db_session, "sans-image", pattern="flexion", image=None, effort="reps"
    )

    body = (
        await auth_client.post(
            "/api/v1/training/compose",
            json={"groups": ["abdos"], "duration_min": 25},
        )
    ).json()

    slugs = {
        item["exercise"]["slug"]
        for workout in body["workouts"]
        for item in workout["items"]
    }
    assert "sans-image" not in slugs


async def test_but_it_stays_in_the_library(auth_client, db_session) -> None:
    """Non éligible **n'est pas** caché : il est simplement jamais proposé."""
    await _exercise(db_session, "sans-image", image=None)

    body = (await auth_client.get("/api/v1/training/exercises")).json()

    row = next(item for item in body if item["slug"] == "sans-image")
    assert row["eligible"] is False


async def test_an_empty_pool_says_why(auth_client, db_session) -> None:
    """Un écran blanc n'apprend rien.

    « Douze exercices d'abdos, mais aucun avec un nom français » dit exactement
    quoi faire — relancer l'import.
    """
    await _exercise(db_session, "muet-1", french=None)
    await _exercise(db_session, "muet-2", french=None, pattern="flexion")

    body = (
        await auth_client.post(
            "/api/v1/training/compose",
            json={"groups": ["abdos"], "duration_min": 15},
        )
    ).json()

    assert body["workouts"] == []
    assert body["reasons"]
    assert any("nom français" in reason for reason in body["reasons"])


async def test_no_equipment_is_the_default_and_it_is_respected(
    auth_client, db_session
) -> None:
    """Le cas du parking de plage."""
    await _library(db_session)
    await _exercise(
        db_session, "avec-barre", pattern="charniere", equipment="halteres",
        effort="reps",
    )

    body = (
        await auth_client.post(
            "/api/v1/training/compose",
            json={"groups": ["abdos"], "duration_min": 25},
        )
    ).json()

    for workout in body["workouts"]:
        for item in workout["items"]:
            assert item["exercise"]["equipment"] == "aucun"


async def test_an_unknown_intent_is_refused(auth_client, db_session) -> None:
    await _library(db_session)

    response = await auth_client.post(
        "/api/v1/training/compose",
        json={"groups": ["abdos"], "duration_min": 15, "intent": "sculpter"},
    )

    assert response.status_code == 422


async def test_a_generated_session_can_be_saved_as_a_formula(
    auth_client, db_session
) -> None:
    await _library(db_session)

    proposed = (
        await auth_client.post(
            "/api/v1/training/compose",
            json={"groups": ["abdos"], "duration_min": 15},
        )
    ).json()
    key = proposed["workouts"][0]["key"]

    saved = await auth_client.post(
        "/api/v1/training/compose/save",
        json={
            "key": key,
            "name": "Abdos du matin",
            "groups": ["abdos"],
            "duration_min": 15,
        },
    )

    assert saved.status_code == 201, saved.text
    body = saved.json()
    assert body["name"] == "Abdos du matin"
    assert body["items"]
    # Une formule composée est sa propre famille : la rattacher à une famille
    # existante fausserait son compte hebdomadaire.
    assert body["variant_of"] is None


async def test_saving_regenerates_rather_than_trusting_the_client(
    auth_client, db_session
) -> None:
    """Une formule est de la donnée d'apprentissage : elle ne vient pas du
    client. Le générateur étant déterministe, ça ne coûte rien."""
    await _library(db_session)

    response = await auth_client.post(
        "/api/v1/training/compose/save",
        json={"key": "inconnu", "name": "Truc", "groups": ["abdos"]},
    )

    assert response.status_code == 404


async def test_composing_needs_a_session(client) -> None:
    assert (
        await client.post("/api/v1/training/compose", json={"groups": ["abdos"]})
    ).status_code == 401


# ── Les formules recomposées ───────────────────────────────────────────────


async def test_a_formula_line_without_an_image_is_replaced(
    db_session, user
) -> None:
    from app.services.formula_repair import repair_formulas

    blind = await _exercise(
        db_session, "sans-photo", pattern="gainage-statique", image=None,
        source="builtin",
    )
    replacement = await _exercise(
        db_session, "avec-photo", pattern="gainage-statique"
    )

    formula = Formula(
        slug="test-formule",
        name="Formule de test",
        duration_min=10,
        weekly_target=2,
        principle="Pour le test.",
    )
    formula.items.append(
        FormulaItem(position=1, exercise_id=blind.id, sets=3, duration_s=40)
    )
    db_session.add(formula)
    await db_session.commit()

    changes = await repair_formulas(db_session)

    assert len(changes) == 1
    assert changes[0].removed_slug == "sans-photo"
    assert changes[0].replaced_by_slug == "avec-photo"
    assert "pas d'image" in changes[0].reason
    await db_session.refresh(formula)
    assert formula.items[0].exercise_id == replacement.id


async def test_a_line_with_no_replacement_is_kept(db_session, user) -> None:
    """Une formule amputée est moins bonne qu'une ligne sans image.

    La séance se fait quand même, et on sait quoi corriger. Supprimer en
    silence laisserait trois minutes là où il y en avait douze.
    """
    from app.services.formula_repair import repair_formulas

    orphan = await _exercise(
        db_session, "orphelin", pattern="portage", image=None, source="builtin"
    )
    formula = Formula(
        slug="test-orphelin",
        name="Orpheline",
        duration_min=10,
        weekly_target=1,
        principle="Pour le test.",
    )
    formula.items.append(
        FormulaItem(position=1, exercise_id=orphan.id, sets=2, reps=10)
    )
    db_session.add(formula)
    await db_session.commit()

    changes = await repair_formulas(db_session)

    assert len(changes) == 1
    assert changes[0].resolved is False
    await db_session.refresh(formula)
    assert formula.items[0].exercise_id == orphan.id


async def test_repairing_twice_changes_nothing_more(db_session, user) -> None:
    from app.services.formula_repair import repair_formulas

    blind = await _exercise(
        db_session, "sans-photo-2", pattern="flexion", image=None,
        source="builtin", effort="reps",
    )
    await _exercise(db_session, "avec-photo-2", pattern="flexion", effort="reps")

    formula = Formula(
        slug="test-idempotent",
        name="Idempotente",
        duration_min=10,
        weekly_target=1,
        principle="Pour le test.",
    )
    formula.items.append(
        FormulaItem(position=1, exercise_id=blind.id, sets=3, reps=12)
    )
    db_session.add(formula)
    await db_session.commit()

    first = await repair_formulas(db_session)
    second = await repair_formulas(db_session)

    assert len(first) == 1
    assert second == []


# ── Les images empruntées ──────────────────────────────────────────────────


async def test_a_builtin_without_an_image_borrows_one(db_session) -> None:
    from app.services.exercise_images import borrow_missing_images

    await _exercise(
        db_session, "maison", pattern="gainage-statique", image=None,
        source="builtin",
    )
    await _exercise(db_session, "importe", pattern="gainage-statique")

    borrowed = await borrow_missing_images(db_session)

    assert len(borrowed) == 1
    assert borrowed[0].found
    assert borrowed[0].donor_slug == "importe"
    # La licence suit l'image, toujours.
    assert "Public Domain" in (borrowed[0].license or "")


async def test_what_has_no_match_keeps_its_absence(db_session) -> None:
    """Coller l'image d'un mouvement voisin ferait faire le mauvais exercice.

    C'est pire que pas d'image du tout, et c'est pour ça qu'on s'abstient.
    """
    from app.services.exercise_images import borrow_missing_images

    lonely = await _exercise(
        db_session, "seul-au-monde", pattern="portage", image=None,
        source="builtin",
    )

    borrowed = await borrow_missing_images(db_session)

    assert borrowed[0].found is False
    assert borrowed[0].how == "aucune"
    await db_session.refresh(lonely)
    assert lonely.image_url is None


async def test_an_imported_exercise_never_borrows(db_session) -> None:
    """Un exercice importé sans photo n'en aura jamais : lui en coller une
    venue d'ailleurs serait une invention pure."""
    from app.services.exercise_images import borrow_missing_images

    await _exercise(db_session, "importe-aveugle", image=None)
    await _exercise(db_session, "importe-voyant")

    borrowed = await borrow_missing_images(db_session)

    assert borrowed == []
