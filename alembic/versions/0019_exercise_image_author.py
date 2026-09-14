"""14/09 — l'auteur d'une image, à côté de sa licence

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-14

Six exercices maison n'avaient pas d'image, et n'étaient donc proposés ni par
le générateur ni par les formules (`Exercise.is_eligible`). Trois d'entre eux
sont des postures connues, et Wikimedia Commons en a des photos libres :
Cobra, Chien tête en bas, Torsion allongée.

Elles sont en **CC BY 3.0** et **CC BY-SA 3.0**, et ces licences demandent de
**nommer l'auteur**. Jusqu'ici la ligne portait `source`, `license` et
`source_url` — de quoi dire d'où vient l'image et ce qu'on a le droit d'en
faire, mais pas à qui on la doit. Un lien vers la page du fichier ne suffit
pas : il faut cliquer pour savoir, et personne ne clique.

D'où une colonne, et une seule. Elle reste nulle pour wger et
free-exercise-db, qui publient au nom du projet et non d'une personne, et pour
les pictogrammes dessinés dans l'application.

Une migration = une transaction (cf. CLAUDE.md).
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0019"
down_revision: Union[str, Sequence[str], None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("exercises") as batch:
        batch.add_column(sa.Column("image_author", sa.String(length=120), nullable=True))


def downgrade() -> None:
    # Redescendre perd les noms d'auteurs, et c'est la seule lecture honnête :
    # l'ancien schéma n'a nulle part où les écrire. Le semis les repose au
    # premier démarrage — ils vivent dans le code, pas seulement en base.
    with op.batch_alter_table("exercises") as batch:
        batch.drop_column("image_author")
