"""Les images des six exercices maison — et ce qu'elles doivent au droit.

Six exercices rédigés à la main n'avaient aucune image, et un exercice sans
image n'entre **ni dans une formule ni dans le générateur**
(`Exercise.is_eligible`). Ils étaient donc écrits, corrects, et jamais
proposés.

Trois sont maintenant illustrés par des photos de Wikimedia Commons, trois par
des pictogrammes dessinés dans l'application. Ce fichier tient les quatre
choses qui, en silence, redéfairaient ce travail :

1. **Un slug qui ne correspond à rien.** `HOUSE_IMAGES` est indexé par slug ;
   une faute de frappe n'échoue nulle part, elle laisse simplement l'exercice
   sans image — donc invisible dans les séances, exactement comme avant. C'est
   arrivé pendant l'écriture : « passage-de-baton » au lieu de
   « dislocation-batons ».
2. **Un fichier absent du dépôt.** Même effet, en pire : l'exercice est
   *éligible* et affiche une image cassée au milieu d'une séance.
3. **Une attribution manquante.** CC BY et CC BY-SA demandent de nommer
   l'auteur. Ce n'est pas une politesse : c'est la condition du droit
   d'afficher la photo. Une ligne sans auteur est une infraction, et elle ne
   se voit pas.
4. **Un semis qui écrase.** Le semis a pour règle de ne jamais toucher à ce
   qu'un import a trouvé. L'exception posée ici doit rester une exception.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.exercise import Exercise
from app.services.training import seed_exercises
from app.services.training_catalog import EXERCISES, HOUSE_IMAGES

REPO = Path(__file__).resolve().parent.parent
PUBLIC = REPO / "frontend" / "public"

# Les licences qui **exigent** de nommer l'auteur. Le domaine public et les
# licences maison n'ont personne à créditer.
ATTRIBUTION_REQUIRED = ("CC BY",)

PICTOGRAM_PREFIX = "pictogram:"


# ── Ce que le catalogue déclare ──────────────────────────────────────────


def test_every_house_image_points_at_a_real_exercise() -> None:
    """Un slug inventé ne casse rien : il laisse l'exercice sans image.

    C'est-à-dire qu'il annule silencieusement tout l'intérêt de l'opération —
    le pire mode de défaillance qui soit, parce qu'il ressemble à un succès.
    """
    known = {entry["slug"] for entry in EXERCISES}
    unknown = sorted(set(HOUSE_IMAGES) - known)
    assert not unknown, (
        f"Slug(s) inconnu(s) dans HOUSE_IMAGES : {unknown}. "
        "L'exercice visé resterait sans image, et donc jamais proposé."
    )


def test_every_local_image_file_is_in_the_repository() -> None:
    """Une image référencée mais absente est pire qu'une image manquante.

    Sans fichier, l'exercice est déclaré éligible et affiche un cadre cassé au
    milieu d'une séance — les mains au sol, c'est le moment où l'on referme
    l'application.
    """
    missing = []
    for slug, house in sorted(HOUSE_IMAGES.items()):
        url = house["image_url"]
        assert url, f"{slug} n'a pas d'image_url"
        if url.startswith(PICTOGRAM_PREFIX):
            continue
        assert url.startswith("/"), (
            f"{slug} : « {url} » n'est ni un pictogramme ni un chemin local. "
            "Une image servie depuis un autre domaine disparaîtrait le jour "
            "où le fichier y est renommé."
        )
        if not (PUBLIC / url.lstrip("/")).is_file():
            missing.append(f"{slug} → {url}")

    assert not missing, "Fichier(s) absent(s) de frontend/public :\n  " + "\n  ".join(
        missing
    )


def test_local_images_stay_small_enough_to_load_on_a_car_park() -> None:
    """200 Ko, et la raison est le réseau du parking, pas le disque.

    Le mode séance s'ouvre souvent sur une connexion qui ne vaut rien. Une
    photo de deux mégaoctets met dix secondes à venir, et pendant ces dix
    secondes on ne sait pas quel mouvement faire.
    """
    heavy = []
    for slug, house in sorted(HOUSE_IMAGES.items()):
        url = house["image_url"]
        if url.startswith(PICTOGRAM_PREFIX):
            continue
        size_ko = (PUBLIC / url.lstrip("/")).stat().st_size / 1024
        if size_ko > 200:
            heavy.append(f"{slug} : {size_ko:.0f} Ko")

    assert not heavy, "Image(s) trop lourde(s) :\n  " + "\n  ".join(heavy)


def test_every_cc_by_image_names_its_author() -> None:
    """La condition du droit d'afficher la photo, tenue par un test.

    CC BY et CC BY-SA demandent d'attribuer l'œuvre à son auteur. Un lien vers
    la page du fichier ne le fait pas : il faut cliquer pour savoir, et
    personne ne clique.
    """
    unattributed = [
        f"{slug} ({house['license']})"
        for slug, house in sorted(HOUSE_IMAGES.items())
        if house["license"]
        and house["license"].startswith(ATTRIBUTION_REQUIRED)
        and not house["image_author"]
    ]
    assert not unattributed, (
        "Image(s) sous licence à attribution, sans auteur :\n  "
        + "\n  ".join(unattributed)
        + "\n\nNommer l'auteur n'est pas une politesse, c'est la condition."
    )


def test_every_borrowed_image_says_where_it_comes_from() -> None:
    """Retrouver l'origine d'une image après coup est impossible."""
    for slug, house in sorted(HOUSE_IMAGES.items()):
        if house["image_url"].startswith(PICTOGRAM_PREFIX):
            # Un dessin fait ici : ni page d'origine ni auteur tiers.
            assert house["source"] == "sport", slug
            assert house["license"] == "personnelle", slug
            continue
        assert house["source_url"], f"{slug} n'a pas de page d'origine"
        assert house["license"], f"{slug} n'a pas de licence"


# ── Ce que le semis en fait ──────────────────────────────────────────────


@pytest.fixture
async def seeded(db_session):
    await seed_exercises(db_session)
    rows = (await db_session.execute(select(Exercise))).scalars().all()
    return {row.slug: row for row in rows}


async def test_the_six_become_eligible(seeded) -> None:
    """Le but de toute l'opération, en une assertion.

    Éligible veut dire : proposable par le générateur, et gardé dans une
    formule au lieu d'être remplacé.
    """
    not_eligible = [
        slug for slug in HOUSE_IMAGES if not seeded[slug].is_eligible
    ]
    assert not not_eligible, f"Toujours pas éligible(s) : {not_eligible}"


async def test_the_seed_carries_licence_and_author(seeded) -> None:
    """Ce qui est écrit dans le catalogue arrive bien jusqu'à la ligne."""
    cobra = seeded["cobra"]
    assert cobra.image_url == "/exercises/cobra.jpg"
    assert cobra.image_author == "Kennguru"
    assert cobra.license == "CC BY 3.0"
    assert cobra.source == "wikimedia-commons"
    assert cobra.source_url.startswith("https://commons.wikimedia.org/")


async def test_a_pictogram_carries_no_borrowed_licence(seeded) -> None:
    """Un dessin fait ici n'est ni CC BY ni domaine public."""
    pop_up = seeded["pop-up"]
    assert pop_up.image_url == "pictogram:pop-up"
    assert pop_up.source == "sport"
    assert pop_up.license == "personnelle"
    assert pop_up.image_author is None


async def test_the_seed_leaves_an_imported_image_alone(db_session) -> None:
    """La règle d'origine tient : un semis n'efface pas ce qu'un import a mis.

    Le jour où une base ouverte publie enfin une vraie photo de pop-up à sec,
    elle vaut mieux que notre dessin — et elle doit rester.
    """
    await seed_exercises(db_session)

    pop_up = (
        await db_session.execute(select(Exercise).where(Exercise.slug == "pop-up"))
    ).scalar_one()
    pop_up.image_url = "https://wger.de/media/vrai-pop-up.png"
    pop_up.source = "wger"
    pop_up.license = "CC BY-SA 4.0"
    await db_session.commit()

    await seed_exercises(db_session)

    await db_session.refresh(pop_up)
    assert pop_up.image_url == "https://wger.de/media/vrai-pop-up.png"
    assert pop_up.source == "wger"


async def test_the_seed_refreshes_our_own_image(db_session) -> None:
    """Corriger un pictogramme ici doit se propager sans migration.

    C'est l'autre moitié de la règle : on ne touche pas à ce qui vient
    d'ailleurs, mais on garde la main sur ce qui vient d'ici.
    """
    await seed_exercises(db_session)

    pop_up = (
        await db_session.execute(select(Exercise).where(Exercise.slug == "pop-up"))
    ).scalar_one()
    pop_up.image_url = "pictogram:ancien-dessin"
    await db_session.commit()

    await seed_exercises(db_session)

    await db_session.refresh(pop_up)
    assert pop_up.image_url == "pictogram:pop-up"


async def test_the_six_are_no_longer_replaced_in_formulas(db_session) -> None:
    """**Ce que toute l'étape sert à obtenir.**

    Le 13/09, sept lignes de formule ont été remplacées parce que leur
    exercice n'avait pas d'image : le Cobra est sorti de trois formules, le
    passage de bâton de deux, le chien tête en bas d'une — tous au profit du
    chat-vache ou des cercles d'épaules. C'était le bon arbitrage à l'époque :
    « une formule amputée est moins bonne qu'une ligne sans photo, et une
    ligne fausse est pire que les deux. »

    Maintenant qu'ils ont une image, ces lignes doivent **rester**. Une
    formule post-surf sans cobra a trois fois le même mouvement d'ouverture du
    dos, et c'est précisément ce que la recomposition avait dû accepter.
    """
    from app.services.formula_repair import repair_formulas
    from app.services.training import seed_formulas

    await seed_exercises(db_session)
    await seed_formulas(db_session)

    replacements = await repair_formulas(db_session, dry_run=True)

    touched = sorted(
        f"{item.formula_name} #{item.position} : {item.removed_name}"
        for item in replacements
        if item.removed_slug in HOUSE_IMAGES
    )
    assert not touched, (
        "Ces lignes pointent sur un exercice maison désormais illustré, et "
        "seraient pourtant encore remplacées :\n  " + "\n  ".join(touched)
    )


async def test_a_single_image_never_lands_in_the_alternating_list(seeded) -> None:
    """`images` fait clignoter deux photos l'une après l'autre.

    Une image unique qui s'y trouverait clignoterait contre elle-même : un
    mouvement perçu là où il n'y en a aucun, sur l'écran précisément fait pour
    montrer le mouvement.
    """
    for slug in HOUSE_IMAGES:
        assert not seeded[slug].images, slug
