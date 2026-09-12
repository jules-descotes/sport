from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.types import OptionalUtcDatetime, UtcDatetime


class ApiTokenCreate(BaseModel):
    name: str = Field(default="Raccourci iPhone", min_length=1, max_length=60)


class ApiTokenRead(BaseModel):
    """Ce qu'on affiche dans le profil. **Jamais le jeton.**"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: UtcDatetime
    expires_at: UtcDatetime
    last_used_at: OptionalUtcDatetime = None
    revoked_at: OptionalUtcDatetime = None


class ApiTokenCreated(ApiTokenRead):
    """La seule réponse qui porte le jeton en clair, et elle ne revient pas.

    La valeur n'est pas stockée : on ne garde que le `jti` qui permettra de la
    révoquer. Ne pas la recopier tout de suite oblige à en refaire un — ce qui
    est le comportement voulu, et ce que dit l'écran.
    """

    token: str
