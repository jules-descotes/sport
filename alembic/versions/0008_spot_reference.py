"""lot 5 (13/09) — le spot de référence du coefficient de marée

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-13

Le coefficient de marée est national par définition : le SHOM le calcule au
port de référence de **Brest**, et il vaut pour toute la côte. Il nous faut
donc le niveau marin à Brest, et pour l'obtenir il nous faut un spot — un spot
technique, qui n'est le lieu de surf de personne.

`is_reference` est ce qui le distingue :

- `spot_tiers.recompute_tiers` le maintient en `home` quoi que Jules mette en
  favori. Sans cette colonne, le premier recalcul des niveaux — c'est-à-dire
  la première connexion — le renverrait au catalogue, l'ingestion s'arrêterait
  et le coefficient disparaîtrait de l'app sans que rien ne le dise ;
- les listes d'écran (recherche, autour de moi, favoris) l'excluent. Un
  marégraphe dans les résultats de recherche est un bug, pas une donnée.

Une migration = une transaction (cf. CLAUDE.md) : ce fichier ne fait que ce
qu'annonce son titre. La **ligne** de Brest, elle, est semée par l'application
au premier passage du job d'ingestion, pas ici : ses coordonnées et son nom
peuvent bouger, et on n'écrit pas une migration pour corriger un libellé.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("spots") as batch:
        batch.add_column(
            sa.Column(
                "is_reference",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("spots") as batch:
        batch.drop_column("is_reference")
