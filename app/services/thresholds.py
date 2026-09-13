"""Lecture des seuils de qualité — un seul chemin, pour tout le monde.

Ce module existe pour que la rampe de couleur du tableau horaire et le score de
démarrage lisent **les mêmes huit nombres**. Une cellule teintée « bonne » sous
une note de 2 est le genre d'incohérence qu'on met des mois à débusquer, et qui
ne se corrige jamais complètement une fois que deux endroits du code ont chacun
leur copie des seuils.

La ligne est créée à la première lecture, avec les défauts du schéma. Pas de
semis en migration : les valeurs par défaut vivent là où elles se corrigent.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.thresholds import UserThresholds
from app.schemas.thresholds import DEFAULTS
from app.services.scoring import Thresholds


async def get_row(
    db: AsyncSession, user_id: int
) -> Optional[UserThresholds]:
    """La ligne de cet utilisateur, ou `None` s'il n'en a pas encore."""
    result = await db.execute(
        select(UserThresholds).where(UserThresholds.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_or_create(db: AsyncSession, user_id: int) -> UserThresholds:
    """La ligne, créée aux défauts si elle manque.

    Créer plutôt que rendre un objet volatil : l'écran de réglage a besoin d'une
    ligne à modifier, et la créer au premier `PUT` seulement obligerait cet
    écran à distinguer deux cas pour rien.
    """
    row = await get_row(db, user_id)
    if row is not None:
        return row

    row = UserThresholds(user_id=user_id, **DEFAULTS)
    db.add(row)
    await db.flush()
    return row


async def load(db: AsyncSession, user_id: int) -> Thresholds:
    """Les seuils pour le calcul — **sans jamais écrire**.

    C'est la version qu'utilisent la reco, le tableau horaire et les annonces.
    Une lecture qui écrit est une surprise, et celle-ci se produirait à chaque
    ouverture de l'app : on retombe simplement sur les défauts tant que Jules
    n'a rien réglé.
    """
    return Thresholds.from_row(await get_row(db, user_id))
