"""Le plafond d'appels journalier, et le seul endroit qui l'applique.

Une règle, et elle ne souffre pas d'exception : **tout appel réseau à un
fournisseur à quota passe par `reserve()`**, le backfill historique comme le
job horaire. Un chemin qui contournerait le compteur le rendrait faux, et un
compteur faux est pire que pas de compteur — il donne l'illusion d'être
protégé.

`reserve()` réserve **avant** l'appel, pas après. Un appel compté après coup
n'est pas compté du tout quand il lève, et c'est précisément la requête qui
finit en 429 qu'on voudrait voir passée au compteur.
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_quota import ApiQuota

logger = logging.getLogger(__name__)


class QuotaExhausted(RuntimeError):
    """Le plafond du jour est atteint. L'appel n'est pas parti sur le réseau."""


def utc_day(moment: datetime | None = None) -> date:
    """Le jour courant en UTC, jamais en heure locale.

    Le conteneur Railway est en UTC, une machine de développement ne l'est pas,
    et un compteur qui change de jour à 2 h du matin selon la machine serait
    intenable à relire.
    """
    moment = moment or datetime.now(UTC)
    return moment.astimezone(UTC).date()


async def used_today(
    db: AsyncSession, provider: str, day: date | None = None
) -> int:
    day = day or utc_day()
    result = await db.execute(
        select(ApiQuota.count).where(
            ApiQuota.provider == provider, ApiQuota.day == day
        )
    )
    return result.scalar_one_or_none() or 0


async def reserve(
    db: AsyncSession,
    provider: str,
    cap: int,
    count: int = 1,
    day: date | None = None,
) -> int:
    """Réserve `count` appels, ou lève sans rien réserver.

    Renvoie le total consommé après réservation. Le `flush` est immédiat :
    deux passes concurrentes dans la même transaction doivent se voir.
    """
    day = day or utc_day()

    result = await db.execute(
        select(ApiQuota).where(ApiQuota.provider == provider, ApiQuota.day == day)
    )
    row = result.scalar_one_or_none()

    if row is None:
        row = ApiQuota(provider=provider, day=day, count=0)
        db.add(row)
        await db.flush()

    if row.count + count > cap:
        # Refus **avant** le réseau : c'est tout l'objet du compteur. Le log
        # dit le chiffre, parce qu'un refus silencieux se confondrait avec une
        # journée sans données.
        logger.warning(
            "quota %s atteint pour le %s : %d/%d utilisés, %d refusé(s)",
            provider,
            day.isoformat(),
            row.count,
            cap,
            count,
        )
        raise QuotaExhausted(
            f"plafond {provider} atteint pour le {day.isoformat()} : "
            f"{row.count}/{cap} appels déjà consommés"
        )

    row.count += count
    await db.flush()
    return row.count


async def remaining(
    db: AsyncSession, provider: str, cap: int, day: date | None = None
) -> int:
    return max(0, cap - await used_today(db, provider, day))
