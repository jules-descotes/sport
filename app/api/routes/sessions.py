"""Sessions de surf — enregistrement, chemin rapide, notation, historique.

⚠️ **Les routes fixes sont déclarées AVANT les routes paramétrées**
(cf. CLAUDE.md) : `/sessions/quick` et `/sessions/today` doivent précéder
`/sessions/{session_id}`, sinon FastAPI tente de lire « quick » comme un
identifiant et renvoie 422 — sur l'endpoint dont dépend tout le lot.

Ce qui compte ici n'est pas la richesse des champs, c'est le **temps de
saisie**. Le risque du projet est la friction, pas la rareté des données : à
240 sessions par an, tout écran qui dépasse quinze secondes tue le jeu de
données (cf. PROJET.md §7.2). D'où deux chemins distincts et complémentaires :

- `POST /sessions/quick` — sortie de l'eau, une position et rien d'autre. La
  session existe, elle est « à noter », les conditions sont figées ;
- `PATCH /sessions/{id}` — la notation, plus tard, au sec, en boutons.
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.database import get_db
from app.models.enums import SessionStatus
from app.models.gear import Gear
from app.models.spot import Spot
from app.models.surf_session import SurfSession
from app.models.user import User
from app.schemas.session import (
    QuickSessionResponse,
    SessionJournal,
    SurfSessionCreate,
    SurfSessionQuick,
    SurfSessionRead,
    SurfSessionUpdate,
)
from app.services.auth_service import get_current_active_user
from app.services.backfill import build_conditions_snapshot
from app.services.sessions import (
    QUICK_DEFAULT_DURATION_MIN,
    archive_snapshot,
    create_quick_session,
    find_duplicate,
    needs_refill,
    purge_deadline,
    quick_start_time,
    resolve_quick_spot,
)
from app.services.storage import StorageError, store_session_photo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _user_timezone(user: User) -> ZoneInfo:
    """Le fuseau d'affichage du profil, avec repli sur Paris.

    Les heures sont en UTC en base ; « aujourd'hui » est une notion locale, et
    à 1 h du matin heure de Paris, UTC est encore la veille.
    """
    name = user.profile.timezone if user.profile else "Europe/Paris"
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Europe/Paris")


def _local_day_bounds(day: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    """Les bornes UTC d'une journée locale."""
    start = datetime.combine(day, time.min, tzinfo=zone)
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


async def _get_session(
    db: AsyncSession,
    user_id: int,
    session_id: int,
    *,
    include_trashed: bool = False,
) -> SurfSession:
    """La session de cet utilisateur, corbeille exclue sauf demande explicite.

    Une session en corbeille n'existe plus du point de vue de l'app : elle ne
    se lit pas, ne se note pas, ne se modifie pas. Seule la restauration va la
    chercher.
    """
    query = (
        select(SurfSession)
        .where(SurfSession.id == session_id)
        .where(SurfSession.user_id == user_id)
    )
    if not include_trashed:
        query = query.where(SurfSession.deleted_at.is_(None))

    session = (await db.execute(query)).scalar_one_or_none()
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session introuvable"
        )
    return session


async def _get_spot(db: AsyncSession, spot_id: int) -> Spot:
    spot = (
        await db.execute(select(Spot).where(Spot.id == spot_id))
    ).scalar_one_or_none()
    if spot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Spot introuvable"
        )
    return spot


async def _check_gear(db: AsyncSession, user_id: int, gear_id: int) -> None:
    """Le matos d'un autre utilisateur n'existe pas pour celui-ci."""
    result = await db.execute(
        select(Gear.id).where(Gear.id == gear_id).where(Gear.user_id == user_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Matos introuvable"
        )


def _apply_status(session: SurfSession) -> None:
    """Le statut est **déduit**, jamais posé par le client.

    Une session à moitié notée resterait sinon marquée notée et sortirait de
    l'écran Jour sans être exploitable — or c'est précisément le mélange des
    deux notes que la double note existe pour éviter (cf. CLAUDE.md, règle 6).
    """
    session.status = (
        SessionStatus.RATED.value if session.is_rated else SessionStatus.TO_RATE.value
    )


# ── Routes fixes ───────────────────────────────────────────────────────────


@router.post(
    "/quick", response_model=QuickSessionResponse, status_code=status.HTTP_201_CREATED
)
async def quick_session(
    data: SurfSessionQuick,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> QuickSessionResponse:
    """Sortie de l'eau — une position, et c'est tout.

    Authentifié par en-tête `Authorization: Bearer` : le raccourci iOS
    « Obtenir le contenu de l'URL » n'a pas de magasin de cookies, et le cookie
    `Secure` de la session ne lui parviendrait de toute façon pas. Le jeton se
    fabrique depuis le profil et se révoque depuis le profil.

    Le serveur déduit tout le reste : le spot le plus proche à moins de 2 km
    (sinon le favori du profil), un début à fin − 90 min, et il fige les
    conditions dans la foulée. La session part « à noter » et le lien profond
    renvoyé ouvre l'écran de notation.

    **Idempotent sur dix minutes** : deux déclenchements rapprochés du
    raccourci donnent une seule session, et la réponse le dit (`created`).
    """
    ended_at = (data.ended_at or datetime.now(UTC)).astimezone(UTC)
    duration_min = data.duration_min or QUICK_DEFAULT_DURATION_MIN
    started_at = quick_start_time(ended_at, duration_min)

    existing = await find_duplicate(
        db, current_user.id, started_at, client_uuid=data.client_uuid
    )
    if existing is not None:
        return _quick_response(
            existing,
            created=False,
            spot_source="existing",
            spot_distance_km=None,
        )

    spot, spot_source, distance_km = await resolve_quick_spot(
        db, current_user.id, data.lat, data.lon
    )
    if spot is None:
        # Ni spot proche, ni favori : il n'y a rien à quoi rattacher la
        # session, et en inventer un salirait le catalogue. On dit quoi faire.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Aucun spot à moins de 2 km et aucun spot favori dans le profil. "
                "Choisis un spot favori, ou ajoute ce spot depuis la carte."
            ),
        )

    session = await create_quick_session(
        db,
        user_id=current_user.id,
        spot=spot,
        started_at=started_at,
        duration_min=duration_min,
        discipline=data.discipline.value,
        lat=data.lat,
        lon=data.lon,
        client_uuid=data.client_uuid,
    )

    return _quick_response(
        session, created=True, spot_source=spot_source, spot_distance_km=distance_km
    )


def _quick_response(
    session: SurfSession,
    created: bool,
    spot_source: str,
    spot_distance_km: Optional[float],
) -> QuickSessionResponse:
    path = f"/sessions/{session.id}/noter"
    return QuickSessionResponse(
        session=SurfSessionRead.model_validate(session),
        created=created,
        spot_source=spot_source,
        spot_distance_km=spot_distance_km,
        rate_path=path,
        # Absolu : c'est le raccourci iOS qui l'ouvre, et il ne connaît pas
        # l'hôte du front. Un seul hôte, déclaré partout (cf. CLAUDE.md).
        rate_url=f"{settings.site_url.rstrip('/')}{path}",
    )


@router.get("/today", response_model=SessionJournal)
async def today_sessions(
    day: Optional[date] = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> SessionJournal:
    """Ce dont l'écran Jour a besoin, en un seul aller-retour.

    `to_rate` remonte **toutes** les sessions non notées, pas seulement celles
    du jour : une session enregistrée samedi et oubliée doit continuer de se
    rappeler au bon souvenir lundi, sinon elle ne sera jamais notée — et une
    session non notée ne vaut rien pour le modèle.
    """
    zone = _user_timezone(current_user)
    target = day or datetime.now(zone).date()
    start, end = _local_day_bounds(target, zone)

    pending = await db.execute(
        select(SurfSession)
        .where(SurfSession.user_id == current_user.id)
        .where(SurfSession.deleted_at.is_(None))
        .where(SurfSession.status == SessionStatus.TO_RATE.value)
        .order_by(SurfSession.started_at.desc())
        .limit(5)
    )
    of_the_day = await db.execute(
        select(SurfSession)
        .where(SurfSession.user_id == current_user.id)
        .where(SurfSession.deleted_at.is_(None))
        .where(SurfSession.started_at >= start)
        .where(SurfSession.started_at < end)
        .order_by(SurfSession.started_at)
    )

    return SessionJournal(
        to_rate=[
            SurfSessionRead.model_validate(item) for item in pending.scalars().all()
        ],
        today=[
            SurfSessionRead.model_validate(item) for item in of_the_day.scalars().all()
        ],
    )


@router.get("/trash", response_model=list[SurfSessionRead])
async def list_trashed_sessions(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[SurfSessionRead]:
    """Ce qui est en corbeille, et pour combien de temps encore.

    Route **fixe déclarée avant** `/sessions/{session_id}` (cf. CLAUDE.md) :
    sans cet ordre, FastAPI lirait « trash » comme un identifiant et renverrait
    un 422.
    """
    # Bornée à la fenêtre de rétention : entre deux passes du job de purge,
    # une session peut avoir dépassé ses trente jours sans être encore
    # détruite. La proposer à la restauration serait une promesse qu'on ne
    # tiendra pas au prochain cycle.
    result = await db.execute(
        select(SurfSession)
        .where(SurfSession.user_id == current_user.id)
        .where(SurfSession.deleted_at.is_not(None))
        .where(SurfSession.deleted_at >= purge_deadline())
        .order_by(SurfSession.deleted_at.desc())
        .limit(100)
    )
    return [
        SurfSessionRead.model_validate(session) for session in result.scalars().all()
    ]


@router.post("", response_model=SurfSessionRead, status_code=status.HTTP_201_CREATED)
async def create_session(
    data: SurfSessionCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> SurfSessionRead:
    """Enregistre une session complète et fige ses conditions.

    Sert la saisie manuelle et la file hors ligne. Fonctionne aussi pour une
    session rétroactive : l'archive Open-Meteo remonte la fenêtre T−2 h → T0
    pour n'importe quelle date et n'importe quel spot du monde, ingéré ou non.

    Un échec de backfill n'empêche jamais l'enregistrement — le snapshot part
    avec un volet `observed` vide et une raison.
    """
    spot = await _get_spot(db, data.spot_id)
    if data.gear_id is not None:
        await _check_gear(db, current_user.id, data.gear_id)

    if data.client_uuid:
        # La file hors ligne rejoue ses envois au retour du réseau : trois
        # tentatives doivent donner une seule session, et la même réponse.
        existing = await find_duplicate(
            db, current_user.id, data.started_at, client_uuid=data.client_uuid
        )
        if existing is not None and existing.client_uuid == data.client_uuid:
            return SurfSessionRead.model_validate(existing)

    session = SurfSession(
        user_id=current_user.id,
        spot_id=spot.id,
        started_at=data.started_at,
        duration_min=data.duration_min,
        discipline=data.discipline.value,
        rating_conditions=data.rating_conditions,
        rating_personal=data.rating_personal,
        gear_id=data.gear_id,
        wave_count=data.wave_count,
        crowd=data.crowd,
        notes=data.notes,
        lat=data.lat,
        lon=data.lon,
        client_uuid=data.client_uuid,
    )
    _apply_status(session)
    session.conditions_snapshot = await build_conditions_snapshot(
        db, spot, data.started_at
    )

    db.add(session)
    await db.commit()
    await db.refresh(session)
    return SurfSessionRead.model_validate(session)


@router.get("", response_model=list[SurfSessionRead])
async def list_sessions(
    session_status: Optional[SessionStatus] = Query(default=None, alias="status"),
    since: Optional[date] = Query(default=None),
    until: Optional[date] = Query(default=None),
    spot_id: Optional[int] = Query(default=None),
    min_rating: Optional[int] = Query(default=None, ge=1, le=5),
    limit: int = Query(default=50, gt=0, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[SurfSessionRead]:
    """L'historique, du plus récent au plus ancien. Corbeille exclue.

    `spot_id` et `min_rating` servent les filtres de l'écran Surf ; `since` et
    `until` le filtre par mois. Tout est optionnel : sans filtre, c'est la
    liste complète, et c'est le cas courant.
    """
    zone = _user_timezone(current_user)
    query = (
        select(SurfSession)
        .where(SurfSession.user_id == current_user.id)
        .where(SurfSession.deleted_at.is_(None))
    )

    if spot_id is not None:
        query = query.where(SurfSession.spot_id == spot_id)
    if min_rating is not None:
        # Le filtre porte sur la **note de conditions** : c'est celle qu'on
        # cherche quand on refait l'historique d'un spot. Le ressenti perso se
        # lit sur la ligne, il ne sert pas de crible.
        query = query.where(SurfSession.rating_conditions >= min_rating)
    if session_status is not None:
        query = query.where(SurfSession.status == session_status.value)
    if since is not None:
        query = query.where(SurfSession.started_at >= _local_day_bounds(since, zone)[0])
    if until is not None:
        query = query.where(SurfSession.started_at < _local_day_bounds(until, zone)[1])

    result = await db.execute(
        query.order_by(SurfSession.started_at.desc()).limit(limit).offset(offset)
    )
    return [
        SurfSessionRead.model_validate(session) for session in result.scalars().all()
    ]


# ── Routes paramétrées ─────────────────────────────────────────────────────


@router.get("/{session_id}", response_model=SurfSessionRead)
async def read_session(
    session_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> SurfSessionRead:
    session = await _get_session(db, current_user.id, session_id)
    return SurfSessionRead.model_validate(session)


@router.patch("/{session_id}", response_model=SurfSessionRead)
async def update_session(
    session_id: int,
    data: SurfSessionUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> SurfSessionRead:
    """La notation — et tout ce qui se corrige au passage.

    Deux gestes que le client ne pourrait pas faire, et qui justifient que
    cette route ne soit pas un simple `setattr` en boucle :

    - **le snapshot est refait** si le spot change, ou si le début change
      d'heure. Le chemin rapide devine le spot et estime le début : corriger
      l'un sans refaire l'autre laisserait la session étiquetée avec les
      conditions d'une autre plage ou d'un autre moment, et c'est cette ligne
      exacte qui servira à entraîner le modèle ;
    - **le volet `observed` est rattrapé** s'il est vide. Une session
      enregistrée sur un parking sans réseau part sans lui ; la notation se
      fait au sec, c'est le moment de le compléter.
    """
    session = await _get_session(db, current_user.id, session_id)
    values = data.model_dump(exclude_unset=True)

    if values.get("gear_id") is not None:
        await _check_gear(db, current_user.id, values["gear_id"])

    spot = session.spot
    # Le spot et le début **d'avant** la correction : c'est pour eux que le
    # snapshot courant a été figé, et c'est sous ces valeurs-là qu'il doit
    # entrer dans l'historique.
    previous_spot_id = session.spot_id
    spot_changed = "spot_id" in values and values["spot_id"] != session.spot_id
    if spot_changed:
        spot = await _get_spot(db, values["spot_id"])

    previous_start = session.started_at
    if previous_start.tzinfo is None:
        previous_start = previous_start.replace(tzinfo=UTC)

    for field, value in values.items():
        if field == "discipline" and value is not None:
            session.discipline = value.value if hasattr(value, "value") else value
            continue
        setattr(session, field, value)

    new_start = session.started_at
    if new_start.tzinfo is None:
        new_start = new_start.replace(tzinfo=UTC)

    # La fenêtre du snapshot est calée sur l'heure pleine : un déplacement de
    # quinze minutes aux molettes ne change rien, un déplacement d'une heure si.
    start_changed = new_start.replace(
        minute=0, second=0, microsecond=0
    ) != previous_start.replace(minute=0, second=0, microsecond=0)

    if "started_at" in values:
        # Le début n'est plus une estimation du serveur dès qu'on y a touché.
        session.start_estimated = False

    refill = needs_refill(session)
    if spot_changed or start_changed or refill:
        # L'ancien snapshot est empilé, jamais écrasé : c'est la seule donnée
        # du projet qu'on ne peut pas reconstituer après coup, et une
        # correction faite de bonne foi ne doit pas pouvoir en détruire une
        # version (cf. `services/sessions.archive_snapshot`).
        #
        # Un rattrapage de volet `observed` vide ne compte pas : il n'y avait
        # rien à conserver, et empiler un snapshot creux à chaque notation
        # remplirait l'historique de bruit.
        if spot_changed or start_changed:
            reasons = []
            if spot_changed:
                reasons.append("spot modifié")
            if start_changed:
                reasons.append("début modifié")
            archive_snapshot(
                session,
                ", ".join(reasons),
                spot_id=previous_spot_id,
                started_at=previous_start,
            )

        session.conditions_snapshot = await build_conditions_snapshot(
            db, spot, new_start
        )

    _apply_status(session)

    await db.commit()
    await db.refresh(session)
    return SurfSessionRead.model_validate(session)


@router.post("/{session_id}/photo", response_model=SurfSessionRead)
async def upload_session_photo(
    session_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> SurfSessionRead:
    """Une photo de session. Optionnelle, et elle le reste.

    Elle n'est jamais sur le chemin des quinze secondes : l'écran de notation
    la propose repliée, en bas, et l'envoi exige le réseau — une photo ne se
    met pas dans la file hors ligne, qui est faite pour des notes de quelques
    octets, pas pour trois mégaoctets par session.
    """
    session = await _get_session(db, current_user.id, session_id)
    payload = await file.read()

    try:
        url = await store_session_photo(
            current_user.id, session.id, payload, file.content_type
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)
        ) from exc
    except StorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc

    session.photo_url = url
    await db.commit()
    await db.refresh(session)
    return SurfSessionRead.model_validate(session)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Met une session à la corbeille — trente jours, puis purge.

    Une suppression doit exister : un déclenchement de raccourci dans la poche
    laisse sinon l'écran Jour porter pour toujours un bloc « à noter » qu'on ne
    peut pas noter, et on finit par ne plus le lire du tout.

    Mais elle n'est pas immédiate. Un doigt mouillé supprime aussi bien qu'il
    déclenche le raccourci, et une session notée est une ligne d'apprentissage
    — on ne la détruit pas sur un tap. La purge est faite par le job planifié,
    au-delà de trente jours.
    """
    session = await _get_session(db, current_user.id, session_id)
    session.deleted_at = datetime.now(UTC)
    await db.commit()


@router.post("/{session_id}/restore", response_model=SurfSessionRead)
async def restore_session(
    session_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> SurfSessionRead:
    """Sort une session de la corbeille, telle qu'elle y est entrée.

    Rien n'est recalculé : ni le statut, ni le snapshot. Une session restaurée
    doit être **exactement** celle qui a été supprimée, sinon la corbeille ne
    répare pas l'erreur, elle en fabrique une autre.
    """
    session = await _get_session(
        db, current_user.id, session_id, include_trashed=True
    )
    session.deleted_at = None
    await db.commit()
    await db.refresh(session)
    return SurfSessionRead.model_validate(session)
