"""Routes des spots.

⚠️ **Les routes fixes sont déclarées AVANT les routes paramétrées**
(cf. CLAUDE.md) : `/spots/nearby` doit être défini avant `/spots/{spot_ref}`,
sinon FastAPI tente de lire « nearby » comme un identifiant et renvoie 422.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from typing import Optional, Sequence

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.enums import SpotSource, SpotType
from app.models.forecast import Forecast
from app.models.spot import Spot
from app.models.user import User
from app.schemas.spot import (
    FavoriteRequest,
    ForecastPoint,
    HideRequest,
    PositionUpdate,
    SlotDetail,
    SpotCreate,
    SpotForecastResponse,
    SpotHit,
    SpotNearby,
    SpotPreferenceRead,
    SpotPreferenceUpdate,
    SpotRead,
    SpotUpdate,
    SunDay,
)
from app.services.auth_service import get_current_active_user
from app.services.forecast_ingest import ensure_fresh, last_fetched_at
from app.services.forecast_reads import (
    forecast_delta,
    latest_forecasts_select,
    latest_run_ts,
)
from app.services.geo import (
    bounding_box,
    compass_label,
    haversine_m,
    wave_energy_kj,
)
from app.services.scoring import (
    TideContext,
    build_conditions,
    score_conditions,
)
from app.services.spot_catalog import resolve_spot, unique_slug
from app.services.tide_coefficient import (
    coefficients as tide_coefficients,
    nearest_mark,
)
from app.services.webcams import WebcamUrlError, normalize_webcam_url
from app.services.sun import is_daylight, sun_events
from app.services.spot_tiers import (
    HOME_MAX,
    get_or_create_preferences,
    home_spot_id,
    recompute_tiers,
    record_position,
)

router = APIRouter(prefix="/spots", tags=["spots"])


async def _checked_webcam(url: Optional[str]) -> Optional[str]:
    """Valide une URL de webcam, ou répond 422 avec la raison.

    Le refus est explicite et lisible : « cette webcam n'est servie qu'en
    http » est une information exploitable, là où un cadre vide dans l'app ne
    l'est pas.
    """
    try:
        return await normalize_webcam_url(url)
    except WebcamUrlError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


# ── Routes fixes ───────────────────────────────────────────────────────────


@router.get("/nearby", response_model=list[SpotNearby])
async def spots_nearby(
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
    radius_km: float = Query(default=40.0, gt=0, le=200),
    limit: int = Query(default=50, gt=0, le=200),
    include_hidden: bool = False,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[SpotNearby]:
    """Spots du catalogue autour d'un point, les plus proches d'abord.

    Interroge tout le catalogue, y compris les spots `catalog` sans prévision :
    c'est la vue carte, et un spot sans prévision reste un spot qu'on peut
    mettre en favori.
    """
    preferences = await get_or_create_preferences(db, current_user.id)
    favorites = set(preferences.favorite_spot_ids or [])
    hidden = set(preferences.hidden_spot_ids or [])
    home_id = await home_spot_id(db, current_user.id)

    min_lat, max_lat, min_lon, max_lon = bounding_box(lat, lon, radius_km)
    result = await db.execute(
        select(Spot)
        .where(Spot.lat.between(min_lat, max_lat))
        .where(Spot.lon.between(min_lon, max_lon))
        # Le marégraphe de Brest est un spot en base, pas un lieu de surf : il
        # ne doit apparaître dans aucune liste d'écran.
        .where(Spot.is_reference.is_(False))
    )

    radius_m = radius_km * 1000.0
    nearby: list[SpotNearby] = []
    for spot in result.scalars().all():
        if spot.id in hidden and not include_hidden:
            continue
        distance_m = haversine_m(lat, lon, spot.lat, spot.lon)
        if distance_m > radius_m:
            continue
        nearby.append(
            SpotNearby(
                **SpotRead.model_validate(spot).model_dump(),
                distance_km=round(distance_m / 1000.0, 2),
                is_favorite=spot.id in favorites,
                is_hidden=spot.id in hidden,
                is_home=spot.id == home_id,
            )
        )

    nearby.sort(key=lambda item: item.distance_km)
    return nearby[:limit]


@router.get("/search", response_model=list[SpotHit])
async def search_spots(
    q: str = Query(min_length=2, max_length=80),
    lat: Optional[float] = Query(default=None, ge=-90, le=90),
    lon: Optional[float] = Query(default=None, ge=-180, le=180),
    limit: int = Query(default=25, gt=0, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[SpotHit]:
    """Recherche par nom dans le catalogue mondial — le sélecteur de l'écran Mer.

    **Ne déclenche aucune ingestion.** Chercher « Lafitenia » ne doit pas coûter
    trois appels Open-Meteo ; la prévision se récupère quand on ouvre le spot.

    Les spots sont classés par pertinence grossière : ceux dont le nom
    *commence* par la recherche d'abord, les autres ensuite, puis par distance
    quand la position est connue. Un `LIKE` suffit à cette échelle — le
    catalogue tient dans un index et il n'y a qu'un utilisateur.
    """
    needle = q.strip().lower()
    if not needle:
        return []

    preferences = await get_or_create_preferences(db, current_user.id)
    hidden = set(preferences.hidden_spot_ids or [])
    favorites = set(preferences.favorite_spot_ids or [])
    home_id = await home_spot_id(db, current_user.id)

    result = await db.execute(
        select(Spot)
        .where(func.lower(Spot.name).like(f"%{needle}%"))
        .where(Spot.is_reference.is_(False))
        .limit(limit * 4)
    )

    hits: list[tuple[int, float, SpotHit]] = []
    for spot in result.scalars().all():
        # Un spot masqué reste cherchable : on peut vouloir le rouvrir pour le
        # démasquer. Il passe simplement après les autres.
        distance_km = (
            round(haversine_m(lat, lon, spot.lat, spot.lon) / 1000.0, 1)
            if lat is not None and lon is not None
            else None
        )
        rank = 0 if spot.name.lower().startswith(needle) else 1
        if spot.id in hidden:
            rank += 2
        hits.append(
            (
                rank,
                distance_km if distance_km is not None else 0.0,
                SpotHit(
                    **SpotRead.model_validate(spot).model_dump(),
                    distance_km=distance_km,
                    is_favorite=spot.id in favorites,
                    is_home=spot.id == home_id,
                ),
            )
        )

    hits.sort(key=lambda item: (item[0], item[1], item[2].name))
    return [hit for _, _, hit in hits[:limit]]


@router.get("/favorites", response_model=list[SpotHit])
async def list_favorites(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[SpotHit]:
    """Les spots maison, le favori du profil en tête. Aucune ingestion non plus."""
    preferences = await get_or_create_preferences(db, current_user.id)
    home_id = await home_spot_id(db, current_user.id)

    ids = [int(spot_id) for spot_id in (preferences.favorite_spot_ids or [])]
    if home_id is not None and home_id not in ids:
        ids.insert(0, home_id)
    if not ids:
        return []

    result = await db.execute(
        select(Spot).where(Spot.id.in_(ids)).where(Spot.is_reference.is_(False))
    )
    by_id = {spot.id: spot for spot in result.scalars().all()}

    return [
        SpotHit(
            **SpotRead.model_validate(by_id[spot_id]).model_dump(),
            is_favorite=True,
            is_home=spot_id == home_id,
        )
        for spot_id in ids
        if spot_id in by_id
    ]


@router.get("/preferences", response_model=SpotPreferenceRead)
async def read_preferences(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> SpotPreferenceRead:
    preferences = await get_or_create_preferences(db, current_user.id)
    return SpotPreferenceRead.model_validate(preferences)


@router.put("/preferences", response_model=SpotPreferenceRead)
async def update_preferences(
    data: SpotPreferenceUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> SpotPreferenceRead:
    """Domicile et rayon d'affichage. Recalcule les niveaux d'ingestion."""
    preferences = await get_or_create_preferences(db, current_user.id)

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(preferences, field, value)
    await db.commit()

    await recompute_tiers(db, preferences)
    await db.refresh(preferences)
    return SpotPreferenceRead.model_validate(preferences)


@router.post("/position", response_model=SpotPreferenceRead)
async def update_position(
    data: PositionUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> SpotPreferenceRead:
    """Position courante du téléphone.

    Un déplacement de plus de cinq kilomètres ouvre les spots « potentiels »
    autour de la nouvelle position — c'est ce qui fait marcher le mode trip
    sans rien configurer.
    """
    preferences = await get_or_create_preferences(db, current_user.id)
    await record_position(db, preferences, data.lat, data.lon)
    await db.refresh(preferences)
    return SpotPreferenceRead.model_validate(preferences)


@router.post("", response_model=SpotRead, status_code=status.HTTP_201_CREATED)
async def create_spot(
    data: SpotCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> SpotRead:
    """Ajout manuel depuis la carte.

    `source='user'` : le script d'import mensuel ne touchera jamais à ce spot.
    L'orientation de côte reste nulle — le calcul demande le trait de côte OSM,
    qui n'est interrogé que par le script. La note se fera sans, ce que
    `scoring.py` sait gérer.
    """
    spot_type = data.spot_type or SpotType.UNKNOWN.value
    if spot_type not in {t.value for t in SpotType}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Type de spot inconnu : {spot_type}",
        )

    webcam_url = await _checked_webcam(data.webcam_url)

    spot = Spot(
        slug=await unique_slug(db, data.name, fallback=f"{data.lat:.3f}-{data.lon:.3f}"),
        name=data.name.strip(),
        lat=data.lat,
        lon=data.lon,
        country_code=(data.country_code or "").upper() or None,
        spot_type=spot_type,
        source=SpotSource.USER.value,
        webcam_url=webcam_url,
    )
    db.add(spot)
    await db.commit()
    await db.refresh(spot)

    # Un spot ajouté à la main est presque toujours un spot qu'on veut voir :
    # il tombe dans le rayon, donc en « potentiel », dès le recalcul.
    preferences = await get_or_create_preferences(db, current_user.id)
    await recompute_tiers(db, preferences)
    await db.refresh(spot)

    return SpotRead.model_validate(spot)


# ── Routes paramétrées ─────────────────────────────────────────────────────


async def _get_spot(db: AsyncSession, spot_ref: str) -> Spot:
    spot = await resolve_spot(db, spot_ref)
    if spot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Spot introuvable"
        )
    return spot


@router.get("/{spot_ref}", response_model=SpotRead)
async def read_spot(
    spot_ref: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> SpotRead:
    return SpotRead.model_validate(await _get_spot(db, spot_ref))


@router.patch("/{spot_ref}", response_model=SpotRead)
async def update_spot(
    spot_ref: str,
    data: SpotUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> SpotRead:
    """Retouche d'un spot — surtout l'URL de webcam.

    Le nom d'un spot OSM reste modifiable : la couverture est inégale et le
    rejeu mensuel réécrira le nom d'amont, ce qui est le comportement voulu.
    """
    spot = await _get_spot(db, spot_ref)
    values = data.model_dump(exclude_unset=True)

    # Une URL en clair est refusée, ou réécrite en https si le site le sert :
    # encadrée dans une page en HTTPS, elle serait bloquée comme contenu mixte
    # et ne montrerait qu'un cadre blanc (cf. `services/webcams.py`).
    if "webcam_url" in values:
        spot.webcam_url = await _checked_webcam(values.pop("webcam_url"))

    for field, value in values.items():
        if value is not None:
            setattr(spot, field, value)

    await db.commit()
    await db.refresh(spot)
    return SpotRead.model_validate(spot)


# ── Assemblage d'un créneau ────────────────────────────────────────────────
#
# Trois lecteurs de la même donnée : le tableau horaire, le résumé de l'écran
# Jour et le détail d'un créneau. Ils doivent rendre exactement les mêmes
# chiffres — une note qui change entre la cellule et son détail détruirait la
# confiance dans les deux.


def _utc(value: datetime) -> datetime:
    """SQLite rend des datetimes naïfs ; on recolle l'UTC qui a été écrit."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _label(direction_deg: Optional[float]) -> Optional[str]:
    return None if direction_deg is None else compass_label(direction_deg)


async def _forecast_window(
    db: AsyncSession, spot: Spot, now: datetime, days: int
) -> tuple[list[Forecast], TideContext]:
    """Les prévisions du dernier run sur `days` jours, et la marée qui va avec.

    La marée est construite sur **toutes** les heures chargées, jamais sur les
    seuls créneaux rendus : la pleine et la basse mer sont des extrêmes du
    jour, et une heure sur trois ne suffit pas à les trouver.
    """
    result = await db.execute(
        latest_forecasts_select(
            [spot.id], start=now.replace(minute=0, second=0, microsecond=0)
        )
        .order_by(Forecast.ts)
        .limit(days * 24)
    )
    forecasts = list(result.scalars().all())
    tide = TideContext.from_levels(
        {_utc(row.ts): row.sea_level_m for row in forecasts}
    )
    return forecasts, tide


def _build_point(spot: Spot, forecast: Forecast, tide: TideContext) -> ForecastPoint:
    """Une ligne de `forecasts` devient un créneau noté et prêt à l'écran."""
    ts = _utc(forecast.ts)
    values = {
        "wave_height_m": forecast.wave_height_m,
        "wave_direction_deg": forecast.wave_direction_deg,
        "wave_period_s": forecast.wave_period_s,
        "wave_peak_period_s": forecast.wave_peak_period_s,
        "wind_speed_kt": forecast.wind_speed_kt,
        "wind_gust_kt": forecast.wind_gust_kt,
        "wind_direction_deg": forecast.wind_direction_deg,
        "sea_level_m": forecast.sea_level_m,
        "water_temperature_c": forecast.water_temperature_c,
    }
    conditions = build_conditions(ts, values, tide)
    score = score_conditions(conditions, spot.onshore_dir_deg)

    # Énergie sur la **période moyenne**, la seule que MFWAM serve et la seule
    # sur laquelle la note est calculée (cf. `scoring.build_conditions`).
    energy = (
        wave_energy_kj(forecast.wave_height_m, forecast.wave_period_s)
        if forecast.wave_height_m is not None and forecast.wave_period_s is not None
        else None
    )

    return ForecastPoint(
        ts=ts,
        wave_height_m=forecast.wave_height_m,
        wave_direction_deg=forecast.wave_direction_deg,
        wave_period_s=forecast.wave_period_s,
        wave_peak_period_s=forecast.wave_peak_period_s,
        swell_height_m=forecast.swell_height_m,
        swell_direction_deg=forecast.swell_direction_deg,
        swell_period_s=forecast.swell_period_s,
        secondary_swell_height_m=forecast.secondary_swell_height_m,
        secondary_swell_direction_deg=forecast.secondary_swell_direction_deg,
        secondary_swell_period_s=forecast.secondary_swell_period_s,
        wind_speed_kt=forecast.wind_speed_kt,
        wind_gust_kt=forecast.wind_gust_kt,
        wind_direction_deg=forecast.wind_direction_deg,
        sea_level_m=forecast.sea_level_m,
        water_temperature_c=forecast.water_temperature_c,
        tide_position=conditions.tide_position,
        tide_rising=conditions.rising,
        tide_range_m=conditions.tide_range_m,
        wind_offshore_kt=score.components.get("offshore_kt"),
        wave_energy_kj=None if energy is None else round(energy, 1),
        swell_alignment_deg=score.components.get("alignment_deg"),
        score=score.value,
        score_level=score.level,
        reasons=score.reasons,
        daylight=is_daylight(ts, spot.lat, spot.lon),
    )


def _sun_days(spot: Spot, points: Sequence[ForecastPoint]) -> list[SunDay]:
    """Lever et coucher de chaque journée rendue, dans l'ordre.

    Le tableau horaire grise la nuit d'un seul trait plutôt que d'éteindre
    quarante cellules une par une : il lui faut les deux bornes, pas un
    booléen par heure.
    """
    days: list[SunDay] = []
    seen: set[date] = set()
    for point in points:
        day = point.ts.date()
        if day in seen:
            continue
        seen.add(day)
        sunrise, sunset = sun_events(day, spot.lat, spot.lon)
        days.append(SunDay(day=day, sunrise=sunrise, sunset=sunset))
    return days


@router.get("/{spot_ref}/forecast", response_model=SpotForecastResponse)
async def spot_forecast(
    spot_ref: str,
    days: int = Query(default=5, gt=0, le=7),
    step_hours: int = Query(default=1, ge=1, le=6),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> SpotForecastResponse:
    """Prévision d'un spot, notée créneau par créneau. **Le seul chemin d'ingestion
    à la demande** : on n'interroge que le spot qu'on regarde.

    Déclenche une récupération si le cache a plus de trois heures. Si
    Open-Meteo dépasse cinq secondes, la réponse part avec ce que la base a et
    `refreshing` à `True` : un écran qui met huit secondes ne sera pas rouvert.

    `step_hours=1` sert le **tableau horaire** de l'écran Surf — heure par
    heure sur cinq jours, façon Windguru (décidé le 13/09). `step_hours=3`
    sert le résumé de l'écran Jour, en huit créneaux. Dans les deux cas les
    notes et la marée sont calculées sur **toutes** les heures : la position
    dans la marée se lit sur les extrêmes du jour, et une heure sur trois ne
    suffit pas à les trouver.
    """
    spot = await _get_spot(db, spot_ref)

    refreshing = await ensure_fresh(db, [spot])

    now = datetime.now(UTC)
    forecasts, tide = await _forecast_window(db, spot, now, days)

    points = [
        _build_point(spot, forecast, tide)
        for forecast in forecasts
        if not (step_hours > 1 and _utc(forecast.ts).hour % step_hours)
    ]

    return SpotForecastResponse(
        spot=SpotRead.model_validate(spot),
        refreshing=bool(refreshing),
        fetched_at=await last_fetched_at(db, spot.id),
        run_ts=await latest_run_ts(db, spot.id),
        sun=_sun_days(spot, points),
        points=points,
    )


@router.get("/{spot_ref}/slot", response_model=SlotDetail)
async def spot_slot(
    spot_ref: str,
    ts: datetime = Query(description="Heure du créneau, en UTC"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> SlotDetail:
    """Le détail d'un créneau — le seul écran où les directions sont chiffrées.

    N'ingère rien : le créneau demandé vient d'un tableau déjà affiché, donc
    d'une prévision déjà en base. Rafraîchir ici rendrait un détail qui ne
    correspondrait plus à la cellule qu'on vient de toucher.

    L'écart avec le run de la veille au soir vient de `forecast_reads`, seul
    endroit où est écrite la règle « dernière prévision = `run_ts` max ».
    """
    spot = await _get_spot(db, spot_ref)
    target = ts.astimezone(UTC).replace(minute=0, second=0, microsecond=0)

    # La journée entière, et pas la seule heure demandée : la position dans la
    # marée et le marnage se lisent sur les extrêmes du jour.
    day_start = target.replace(hour=0)
    result = await db.execute(
        latest_forecasts_select(
            [spot.id], start=day_start, end=day_start + timedelta(days=1)
        ).order_by(Forecast.ts)
    )
    forecasts = list(result.scalars().all())

    forecast = next((row for row in forecasts if _utc(row.ts) == target), None)
    if forecast is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pas de prévision pour ce créneau.",
        )

    tide = TideContext.from_levels(
        {_utc(row.ts): row.sea_level_m for row in forecasts}
    )
    point = _build_point(spot, forecast, tide)

    profile = current_user.profile
    timezone = profile.timezone if profile else "Europe/Paris"
    delta = await forecast_delta(db, spot, target, timezone=timezone)

    sunrise, sunset = sun_events(target.date(), spot.lat, spot.lon)

    # Le coefficient de la pleine mer la plus proche. Il est calculé à Brest et
    # vaut pour toute la côte : c'est sa définition, pas un raccourci.
    mark = nearest_mark(
        await tide_coefficients(db, target.date(), 1), target
    )

    return SlotDetail(
        point=point,
        spot=SpotRead.model_validate(spot),
        wave_direction_label=_label(forecast.wave_direction_deg),
        wind_direction_label=_label(forecast.wind_direction_deg),
        secondary_swell_direction_label=_label(
            forecast.secondary_swell_direction_deg
        ),
        onshore_direction_label=_label(spot.onshore_dir_deg),
        sunrise=sunrise,
        sunset=sunset,
        run_ts=delta.run_ts or _utc(forecast.run_ts),
        previous_run_ts=delta.previous_run_ts,
        delta=delta.changes,
        tide_coefficient=None if mark is None else mark.value,
        tide_coefficient_approximate=bool(mark and mark.approximate),
    )


@router.post("/{spot_ref}/favorite", response_model=SpotPreferenceRead)
async def toggle_favorite(
    spot_ref: str,
    data: FavoriteRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> SpotPreferenceRead:
    """Met un spot en favori — c'est-à-dire en ingestion planifiée.

    Vingt au maximum : au-delà, ce n'est plus une liste de spots maison, c'est
    une région entière, et le job de trois heures n'a plus de sens.
    """
    spot = await _get_spot(db, spot_ref)
    preferences = await get_or_create_preferences(db, current_user.id)

    favorites = [int(spot_id) for spot_id in (preferences.favorite_spot_ids or [])]

    if data.favorite:
        if spot.id not in favorites:
            if len(favorites) >= HOME_MAX:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"{HOME_MAX} spots maison au maximum. Retire-en un d'abord.",
                )
            favorites.append(spot.id)
        # Mettre un spot masqué en favori le démasque : garder les deux serait
        # une contradiction sans issue à l'écran.
        preferences.hidden_spot_ids = [
            int(spot_id)
            for spot_id in (preferences.hidden_spot_ids or [])
            if int(spot_id) != spot.id
        ]
    else:
        favorites = [spot_id for spot_id in favorites if spot_id != spot.id]

    preferences.favorite_spot_ids = favorites
    await db.commit()

    await recompute_tiers(db, preferences)
    await db.refresh(preferences)
    return SpotPreferenceRead.model_validate(preferences)


@router.post("/{spot_ref}/hide", response_model=SpotPreferenceRead)
async def toggle_hidden(
    spot_ref: str,
    data: HideRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> SpotPreferenceRead:
    """Masque un spot : il sort des listes et cesse d'être ingéré."""
    spot = await _get_spot(db, spot_ref)
    preferences = await get_or_create_preferences(db, current_user.id)

    hidden = [int(spot_id) for spot_id in (preferences.hidden_spot_ids or [])]

    if data.hidden:
        if spot.id not in hidden:
            hidden.append(spot.id)
        preferences.favorite_spot_ids = [
            int(spot_id)
            for spot_id in (preferences.favorite_spot_ids or [])
            if int(spot_id) != spot.id
        ]
    else:
        hidden = [spot_id for spot_id in hidden if spot_id != spot.id]

    preferences.hidden_spot_ids = hidden
    await db.commit()

    await recompute_tiers(db, preferences)
    await db.refresh(preferences)
    return SpotPreferenceRead.model_validate(preferences)
