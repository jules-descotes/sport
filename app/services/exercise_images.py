"""Donner une image aux exercices maison qui n'en ont pas.

Décidé le 13/09 (retours n° 3). Dix-huit des trente exercices rédigés ici
n'ont pas d'image : leurs `aliases` anglais n'ont rencontré aucun nom des bases
ouvertes, souvent parce que le mouvement y porte un autre nom (« low lunge »
contre « kneeling hip flexor stretch ») ou n'y existe pas (le pop-up à sec).

Et une image n'est pas une décoration : sans elle, l'exercice **n'entre ni dans
le générateur ni dans une formule** (cf. `Exercise.is_eligible`). Un mouvement
qu'on ne reconnaît pas d'un coup d'œil, les mains au sol, est un mouvement
qu'on saute.

Le rapprochement se fait en deux passes, et **il s'arrête à la première qui
trouve** :

1. **Alias exact.** Un nom anglais qu'on a écrit nous-mêmes. C'est le
   rapprochement de l'import, rejoué ici pour les lignes qu'il a manquées.
2. **Groupe + pattern + matériel.** Même travail, même mouvement, même
   matériel : l'image montre le bon geste même si le nom diffère.

Un troisième tier « groupe + pattern » a été essayé le 13/09 et lancé en
production : il a prêté la photo d'un pont fessier à la barre au soulevé de
terre à une jambe. Même pattern, même groupe, et une image qui montre autre
chose — c'est-à-dire exactement ce que ce module existe pour éviter.

**Ce qu'aucune passe ne couvre garde son absence d'image**, et la fonction le
dit. Coller l'image d'un mouvement voisin « pour faire joli » est exactement ce
qui ferait faire le mauvais exercice — c'est pire que pas d'image du tout.

La licence suit l'image, toujours : une photo CC BY-SA empruntée reste CC BY-SA
et s'affiche avec son attribution.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import Exercise
from app.services.exercise_taxonomy import UNCLASSIFIED
from app.services.training_catalog import normalize_name

logger = logging.getLogger(__name__)


@dataclass
class Borrowed:
    """Un emprunt, ou une absence d'emprunt. Les deux comptent."""

    slug: str
    name: str
    # `alias` · `groupe+pattern+materiel` · `aucune`
    how: str
    donor_slug: Optional[str] = None
    donor_name: Optional[str] = None
    image_url: Optional[str] = None
    license: Optional[str] = None

    @property
    def found(self) -> bool:
        return self.image_url is not None


def _donor_pool(rows: list[Exercise]) -> list[Exercise]:
    return [
        row
        for row in rows
        if row.source != "builtin" and row.image_url and row.is_active
    ]


def _by_alias(
    target: Exercise, donors: list[Exercise]
) -> Optional[Exercise]:
    wanted = {normalize_name(alias) for alias in (target.aliases or [])}
    wanted.add(target.name_normalized)
    if not wanted:
        return None
    for donor in donors:
        names = {donor.name_normalized}
        names.update(normalize_name(alias) for alias in (donor.aliases or []))
        if wanted & names:
            return donor
    return None


def _by_taxonomy(
    target: Exercise, donors: list[Exercise], *, with_equipment: bool
) -> Optional[Exercise]:
    if target.group_key == UNCLASSIFIED or target.pattern == UNCLASSIFIED:
        return None

    matches = [
        donor
        for donor in donors
        if donor.group_key == target.group_key
        and donor.pattern == target.pattern
        and (not with_equipment or donor.equipment == target.equipment)
    ]
    if not matches:
        return None
    # Le plus proche en difficulté, puis par slug pour être déterministe :
    # relancer le rapprochement ne doit pas changer l'image sous les doigts.
    matches.sort(
        key=lambda donor: (abs(donor.difficulty - target.difficulty), donor.slug)
    )
    return matches[0]


async def borrow_missing_images(
    db: AsyncSession, *, dry_run: bool = False
) -> list[Borrowed]:
    """Complète les exercices maison sans image. Rend le détail, emprunts et
    échecs.

    Ne touche **que** les lignes `builtin` sans image : un exercice importé qui
    n'a pas de photo n'en aura jamais, et lui en coller une venue d'ailleurs
    serait une invention pure.
    """
    rows = list((await db.execute(select(Exercise))).scalars().all())
    donors = _donor_pool(rows)
    targets = [
        row for row in rows if row.source == "builtin" and not row.image_url
    ]

    results: list[Borrowed] = []
    for target in targets:
        donor = _by_alias(target, donors)
        how = "alias"
        if donor is None:
            donor = _by_taxonomy(target, donors, with_equipment=True)
            how = "groupe+pattern+materiel"
        if donor is None:
            results.append(
                Borrowed(slug=target.slug, name=target.name, how="aucune")
            )
            continue

        results.append(
            Borrowed(
                slug=target.slug,
                name=target.name,
                how=how,
                donor_slug=donor.slug,
                donor_name=donor.name,
                image_url=donor.image_url,
                license=donor.license,
            )
        )

        if not dry_run:
            target.image_url = donor.image_url
            target.images = list(donor.images or [donor.image_url])
            # La licence suit l'image. Le texte reste le nôtre.
            target.license = f"CC0-1.0 (texte) · {donor.license} (image)"
            target.source_url = donor.source_url

    if not dry_run and any(result.found for result in results):
        await db.commit()

    found = sum(1 for result in results if result.found)
    logger.info(
        "Images empruntées : %d sur %d exercices maison sans image",
        found,
        len(results),
    )
    return results
