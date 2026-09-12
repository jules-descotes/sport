"""Stockage des photos de session — disque en local, Cloudflare R2 en production.

Trois choses s'y jouent, et une seule est du stockage.

1. **Ré-encodage systématique.** Une photo d'iPhone fait 4 Mo et 4 032 px de
   large. On la ramène à 1 600 px et à du JPEG qualité 82 : c'est largement
   assez pour se rappeler l'état de la mer, et c'est ce qui évite de payer de
   la bande passante R2 pour une image qu'on regardera sur 390 px.
2. **Effacement des métadonnées.** Pillow ré-encode sans recopier l'EXIF :
   les coordonnées GPS du cliché disparaissent au passage. La position de la
   session est déjà en base, dans une colonne, là où on sait ce qu'elle fait ;
   elle n'a rien à faire en plus dans un fichier servi par une URL publique.
3. **Rotation appliquée.** L'orientation EXIF est appliquée aux pixels avant
   d'être jetée, sans quoi toutes les photos prises en paysage arriveraient
   couchées.

Pillow et boto3 sont synchrones : les deux passent par `asyncio.to_thread`,
sinon un envoi de photo bloquerait la boucle d'événements pour tout le monde —
y compris pour le `POST /sessions/quick` de la sortie suivante.
"""
from __future__ import annotations

import asyncio
import io
import logging
import uuid
from pathlib import Path
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# Ce que le navigateur envoie vraiment depuis un `<input accept="image/*">` sur
# iOS : du JPEG. Le HEIC est converti par le système avant l'envoi, et Pillow
# ne le lit pas sans greffon — le refuser franchement vaut mieux que de stocker
# un fichier qu'on ne saura pas relire.
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}

# Plafond à l'entrée, avant tout décodage : une image de 40 Mo ne doit pas
# arriver jusqu'à Pillow, où elle coûterait bien plus que sa taille en mémoire.
MAX_UPLOAD_BYTES = 12 * 1024 * 1024

MAX_EDGE_PX = 1600
JPEG_QUALITY = 82


class StorageError(RuntimeError):
    """Échec d'écriture. Remonté en 502 : ce n'est pas la faute de l'appelant."""


def _encode(data: bytes) -> bytes:
    """Redimensionne, réoriente, ré-encode en JPEG. Synchrone, appelé en thread."""
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(data)) as image:
        # `exif_transpose` applique la rotation aux pixels ; le reste de l'EXIF
        # part avec le ré-encodage, GPS compris.
        image = ImageOps.exif_transpose(image)
        image.thumbnail((MAX_EDGE_PX, MAX_EDGE_PX))
        # Le JPEG ne connaît ni transparence ni palette.
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        return buffer.getvalue()


def _put_r2(key: str, payload: bytes) -> str:
    """Écrit sur R2 et renvoie l'URL publique. Synchrone, appelé en thread."""
    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )
    client.put_object(
        Bucket=settings.r2_bucket_name,
        Key=key,
        Body=payload,
        ContentType="image/jpeg",
        # Les photos de session ne changent jamais : le nom porte un UUID, donc
        # une URL désigne un contenu pour toujours.
        CacheControl="public, max-age=31536000, immutable",
    )
    return f"{settings.r2_public_url.rstrip('/')}/{key}"


def _put_local(key: str, payload: bytes) -> str:
    """Écrit sous `media_dir`. Sert le développement, et lui seul."""
    destination = Path(settings.media_dir) / key
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return f"/media/{key}"


async def store_session_photo(
    user_id: int, session_id: int, data: bytes, content_type: Optional[str]
) -> str:
    """Range la photo d'une session et renvoie son URL.

    Lève `ValueError` si le fichier n'est pas une image acceptée — c'est une
    faute de l'appelant, traduite en 415 par la route — et `StorageError` si
    l'écriture échoue.
    """
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ValueError(f"Format d'image non accepté : {content_type or 'inconnu'}")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("Image trop lourde")

    try:
        payload = await asyncio.to_thread(_encode, data)
    except Exception as exc:  # image tronquée, format menteur, fichier corrompu
        raise ValueError("Image illisible") from exc

    key = f"sessions/{user_id}/{session_id}-{uuid.uuid4().hex}.jpg"

    try:
        if settings.storage_backend == "r2":
            return await asyncio.to_thread(_put_r2, key, payload)
        return await asyncio.to_thread(_put_local, key, payload)
    except Exception as exc:
        logger.error("Photo de session non stockée (%s) : %s", key, exc)
        raise StorageError("Stockage indisponible") from exc
