from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.db.types import JSONVariant


class Exercise(Base):
    """Un exercice — **avec sa source et sa licence, sur la ligne**.

    Deux origines, et elles ne se mélangent pas :

    - `builtin` — les consignes sont écrites ici, en français, pour ce projet.
      Elles nous appartiennent, et c'est ce qui permet de composer des formules
      sans copier de programme.
    - `wger` / `free-exercise-db` — bases **ouvertes** (`scripts/import_exercises.py`).
      Elles apportent surtout les images et les groupes musculaires. La licence
      est portée par la ligne : une image CC BY-SA ne s'affiche pas comme une
      image du domaine public, et un projet perso d'aujourd'hui peut devenir
      autre chose demain.

    **Jamais de scraping d'un site commercial de programmes** (décidé le
    13/09). C'est contraire aux CGU, ça casse au premier changement de page, et
    c'est la même leçon que `sport=surfing` : on vérifie la donnée avant de s'y
    fier, on ne la ramasse pas parce qu'elle est là.

    `aliases` porte les noms anglais sous lesquels l'exercice est connu dans
    les bases ouvertes. C'est la clé de rapprochement de l'import : il enrichit
    une ligne existante au lieu d'en créer une deuxième sous un autre nom.
    """

    __tablename__ = "exercises"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_exercises_slug"),
        # L'import dédoublonne sur le nom normalisé : sans index, c'est un
        # balayage de la table par exercice importé.
        Index("ix_exercises_normalized", "name_normalized"),
        Index("ix_exercises_category", "category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Minuscules, sans accent ni ponctuation. Sert le dédoublonnage, et lui
    # seul : l'affichage prend toujours `name`.
    name_normalized: Mapped[str] = mapped_column(String(120), nullable=False)

    # `mobility` · `strength` · `core` — les trois catégories du document
    # design. Volontairement peu nombreuses : une taxonomie fine se vérifie
    # mal, et l'import en apporterait une fausse.
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    # Groupe principal, en français : « épaules », « hanches », « dos »…
    muscle_group: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Toujours renseignés, jamais devinés.
    source: Mapped[str] = mapped_column(
        String(30), nullable=False, default="builtin", server_default="builtin"
    )
    license: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)

    # Noms anglais connus dans les bases ouvertes — la clé de rapprochement.
    aliases: Mapped[Optional[list]] = mapped_column(JSONVariant, nullable=True)

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=func.true()
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
