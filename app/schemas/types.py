"""Types Pydantic partagés.

`UtcDatetime` existe pour une raison qui ne se voit qu'en développement, et
qui mordrait très fort si elle passait en production.

Les heures sont stockées en UTC (cf. CLAUDE.md) et converties en heure locale
**côté front**. Encore faut-il que le front sache qu'il lit de l'UTC : sans
décalage explicite, `new Date("2026-09-12T08:30:00")` est interprété par
JavaScript comme une heure **locale**, et une session de 10 h 30 heure de
Paris s'affiche à 8 h 30 — une session du matin qui se range dans la nuit.

Or asyncpg rend des datetimes conscients du fuseau, mais SQLite — le
développement local et tous les tests — rend des datetimes naïfs. Le bug ne
serait donc jamais visible en production, où il n'existe pas, et permanent en
local, où on aurait fini par s'habituer à des heures fausses. Ce type recolle
UTC à la sérialisation : ce qui a été écrit, et ce que le front attend.

Les routes de prévision faisaient déjà ce recollage à la main, ligne par
ligne. Ceci est la même règle, écrite une fois.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Optional

from pydantic import AfterValidator


def _attach_utc(value: datetime) -> datetime:
    """Un datetime naïf vient de SQLite : il porte de l'UTC sans le dire."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _attach_utc_optional(value: Optional[datetime]) -> Optional[datetime]:
    return None if value is None else _attach_utc(value)


# `AfterValidator` et non `BeforeValidator` : il s'exécute une fois la valeur
# convertie en `datetime`, qu'elle soit arrivée en objet (lecture ORM) ou en
# chaîne (corps JSON). Un `BeforeValidator` devrait gérer les deux formes.
UtcDatetime = Annotated[datetime, AfterValidator(_attach_utc)]
OptionalUtcDatetime = Annotated[
    Optional[datetime], AfterValidator(_attach_utc_optional)
]
