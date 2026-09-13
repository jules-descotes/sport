"""13/09 (retours n° 4) — un objectif d'habitude peut être un plafond

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-13

Jusqu'ici un objectif d'habitude était forcément un minimum : « cinq mobilités
par semaine », « deux litres par jour ». Certaines habitudes se suivent dans
l'autre sens — on ne cherche pas à en faire plus, on cherche à en faire moins.

`target_direction` vaut `min` (défaut, le comportement d'avant) ou `max`.

**L'affichage ne change pas entre les deux**, et c'est la seule chose qui
compte ici : un compteur, l'objectif, la tendance à 7 et 30 jours. Pas de
rouge, pas de message, pas de série perdue. Une habitude qu'on cherche à
réduire est déjà assez difficile à tenir sans qu'une application s'en mêle —
et le ton neutre du lot F n'a pas d'exception (cf. CLAUDE.md, étape F : « ton
strictement neutre : jamais de rouge, jamais de série perdue »).

Non nullable avec un défaut : toutes les habitudes existantes sont des minima,
et c'est exactement ce qu'elles étaient.

Une migration = une transaction (cf. CLAUDE.md).
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0017"
down_revision: Union[str, Sequence[str], None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "habits",
        sa.Column(
            "target_direction",
            sa.String(length=8),
            nullable=False,
            server_default="min",
        ),
    )


def downgrade() -> None:
    op.drop_column("habits", "target_direction")
