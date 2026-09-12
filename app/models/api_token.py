from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class ApiToken(Base):
    """Jeton Bearer longue durée — le raccourci iPhone, et rien d'autre.

    Pourquoi une table alors que le JWT est déjà auto-porteur : **un JWT ne se
    révoque pas**. Le jeton du raccourci vit un an dans les Raccourcis iOS,
    en clair, sur un téléphone qui se perd. Sans registre, le seul moyen de le
    couper serait de changer `SECRET_KEY`, donc de déconnecter aussi le
    navigateur et de perdre la session de l'app.

    Le jeton reste donc un JWT signé — même vérification de signature et
    d'expiration que la session de navigateur — mais il porte un `jti` qui est
    cherché ici à chaque appel. Révoquer, c'est poser `revoked_at` : effet
    immédiat, sur ce jeton seul.

    La valeur du jeton n'est **jamais** stockée : elle est affichée une fois à
    la création, et perdue ensuite. On en refait un, on révoque l'ancien.
    """

    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Identifiant du jeton, porté par le claim `jti`. Unique : c'est la clé de
    # révocation.
    jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    # « iPhone — raccourci sortie de l'eau ». Sert à savoir lequel révoquer.
    name: Mapped[str] = mapped_column(String(60), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Mis à jour à chaque appel : c'est ce qui permet de repérer un jeton qui
    # ne sert plus, et de le révoquer sans se demander s'il est encore utile.
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def is_usable(self, now: Optional[datetime] = None) -> bool:
        """Ni révoqué, ni expiré.

        L'expiration est aussi dans le JWT, et elle y sera vérifiée de toute
        façon. La retester ici garde le registre lisible tout seul : la liste
        affichée dans le profil dit la vérité sans décoder quoi que ce soit.
        """
        now = now or datetime.now(UTC)
        if self.revoked_at is not None:
            return False
        # SQLite rend des datetimes naïfs : on les recolle en UTC, ce qui a été
        # écrit.
        expires = (
            self.expires_at
            if self.expires_at.tzinfo
            else self.expires_at.replace(tzinfo=UTC)
        )
        return expires > now
