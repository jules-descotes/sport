"""13/09 (retours n° 3) — type de vagues sur la session et sur ses segments

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-13

Trois axes optionnels : taille, longueur, forme.

**Ce ne sont pas des étiquettes de confort, ce sont des descripteurs des
conditions observées** — la même nature que le `conditions_snapshot`, à ceci
près qu'aucune API ne les mesure et que seul quelqu'un dans l'eau peut les
dire. Un modèle de vagues donne un Hm0 au large ; il ne dit pas si ça a
déferlé creux ou mou, et c'est souvent la différence entre une bonne et une
mauvaise session.

Conséquence pour le lot 3 : ils sont exploitables comme **cibles auxiliaires**
(prédire « creuse » depuis période, cambrure et vent), et **jamais** comme
entrées du modèle moyen terme — ils n'existent pas au moment de la prédiction
(cf. CLAUDE.md, règle 11).

Ils sont posés sur les **deux** tables. Sur `session_segments`, une valeur
renseignée prime sur celle de la session pour son heure : c'est exactement la
raison d'être des segments — la houle monte, la marée tourne, et des vagues
molles à 8 h peuvent être creuses à 10 h.

Colonnes de texte plutôt que type ENUM PostgreSQL : une quatrième valeur se
pose alors dans le code et pas dans une migration, et trois axes saisis à la
main sont exactement ce qu'on affine après une saison.

Tout est nullable, sans valeur par défaut : **une absence de réponse n'est pas
« moyenne »**. Semer « medium » sur les 240 sessions déjà notées fabriquerait
240 observations que personne n'a faites.

Une migration = une transaction (cf. CLAUDE.md).
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0013"
down_revision: Union[str, Sequence[str], None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AXES = ("wave_size", "wave_length", "wave_shape")
TABLES = ("surf_sessions", "session_segments")


def upgrade() -> None:
    for table in TABLES:
        for axis in AXES:
            op.add_column(
                table, sa.Column(axis, sa.String(length=16), nullable=True)
            )


def downgrade() -> None:
    for table in reversed(TABLES):
        for axis in reversed(AXES):
            op.drop_column(table, axis)
