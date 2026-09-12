from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Optional

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

ALGORITHM = "HS256"

# Deux natures de jeton, et il faut pouvoir les distinguer :
#   `access` — la session du navigateur, portée par un cookie httpOnly ;
#   `api`    — le jeton long du raccourci iPhone, révocable par son `jti`.
# Sans ce marquage, un jeton révoqué resterait accepté par la voie cookie.
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_API = "api"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(days=settings.access_token_expire_days)
    )
    to_encode.update({"exp": expire, "type": TOKEN_TYPE_ACCESS})
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def new_jti() -> str:
    """Identifiant de jeton d'API. Aléatoire, jamais dérivé de l'utilisateur."""
    return secrets.token_urlsafe(24)


def create_api_token(email: str, jti: str, expires_days: int) -> tuple[str, datetime]:
    """Jeton Bearer longue durée pour le raccourci iPhone.

    Renvoie le jeton **et** sa date d'expiration : c'est l'appelant qui écrit
    la ligne d'`api_tokens`, et les deux doivent dire la même chose.

    Le `jti` n'est pas de la décoration : c'est la seule prise qu'on ait sur un
    JWT déjà émis. Sans lui, révoquer le jeton d'un téléphone perdu voudrait
    dire changer `SECRET_KEY`, donc déconnecter aussi le navigateur.
    """
    expire = datetime.now(UTC) + timedelta(days=expires_days)
    payload = {"sub": email, "jti": jti, "exp": expire, "type": TOKEN_TYPE_API}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM), expire


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None
