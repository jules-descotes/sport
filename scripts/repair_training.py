"""Rendre le catalogue d'entraînement utilisable : images, français, formules.

À lancer **après** `python -m scripts.import_exercises`, et à relancer après
chaque import. Trois passes, dans cet ordre, parce que chacune dépend de la
précédente :

1. **Semis** du catalogue maison — il pose la taxonomie écrite à la main et les
   noms français des trente exercices rédigés ici.
2. **Emprunt d'images** pour les exercices maison qui n'en ont pas. Sans image,
   un exercice n'est jamais proposé : le rapprochement fait la différence entre
   une formule utilisable et une formule vide.
3. **Réparation des formules** : toute ligne qui pointe sur un exercice sans
   nom français ou sans image est remplacée par un équivalent — et la liste de
   ce qui a été remplacé est imprimée. Elle compte autant que le remplacement.

`--dry-run` montre tout et n'écrit rien. C'est le mode par défaut de la
prudence : on regarde ce qui va bouger dans les quinze formules avant de le
laisser bouger.
"""
from __future__ import annotations

import argparse
import asyncio
import logging

from app.db.database import async_session
from app.services.exercise_images import borrow_missing_images
from app.services.formula_repair import repair_formulas
from app.services.training import ensure_training_seeded

logging.basicConfig(
    level=logging.INFO, format="%(levelname)s %(name)s - %(message)s"
)
logger = logging.getLogger("repair_training")


async def run(dry_run: bool) -> None:
    async with async_session() as db:
        await ensure_training_seeded(db)

        print("\n── Images empruntées ───────────────────────────────────────")
        borrowed = await borrow_missing_images(db, dry_run=dry_run)
        if not borrowed:
            print("  Tous les exercices maison ont déjà une image.")
        for item in sorted(borrowed, key=lambda row: (not row.found, row.slug)):
            if item.found:
                print(
                    f"  ✓ {item.name[:34]:<34} ← {(item.donor_name or '')[:34]:<34}"
                    f" [{item.how}]"
                )
            else:
                print(f"  ✗ {item.name[:34]:<34} aucune correspondance")

        missing = [item for item in borrowed if not item.found]
        if missing:
            print(
                f"\n  {len(missing)} exercice(s) restent sans image. Ils ne "
                "seront jamais proposés — c'est voulu : coller l'image d'un "
                "mouvement voisin ferait faire le mauvais exercice."
            )

        print("\n── Formules recomposées ────────────────────────────────────")
        replacements = await repair_formulas(db, dry_run=dry_run)
        if not replacements:
            print("  Toutes les formules sont composées d'exercices éligibles.")
        for item in replacements:
            if item.resolved:
                print(
                    f"  {item.formula_name[:18]:<18} #{item.position} : "
                    f"{item.removed_name[:28]:<28} → "
                    f"{(item.replaced_by_name or '')[:28]:<28}"
                    f" ({item.reason}, {item.how})"
                )
            else:
                print(
                    f"  {item.formula_name[:18]:<18} #{item.position} : "
                    f"{item.removed_name[:28]:<28} → GARDÉ TEL QUEL "
                    f"({item.reason} — aucun remplaçant)"
                )

        if dry_run:
            print("\nRien n'a été écrit (--dry-run).\n")
        else:
            print("\nÉcrit.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Montre ce qui changerait, sans rien écrire.",
    )
    asyncio.run(run(parser.parse_args().dry_run))


if __name__ == "__main__":
    main()
