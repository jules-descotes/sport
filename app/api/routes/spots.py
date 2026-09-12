"""Routes des spots.

⚠️ **Les routes fixes sont déclarées AVANT les routes paramétrées**
(cf. CLAUDE.md) : `/spots/nearby` doit être défini avant `/spots/{spot_ref}`,
sinon FastAPI tente de lire « nearby » comme un identifiant et renvoie 422.
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
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
    SpotCreate,
    SpotForecastResponse,
    SpotNearby,
    SpotPreferenceRead,
    SpotPreferenceUpdate,
    SpotRead,
    SpotUpdate,
)
from app.services.auth_service import get_current_active_user
from app.services.forecast_ingest import ensure_fresh, last_fetched_at
from app.services.forecast_reads import latest_forecasts_select, latest_run_ts
from app.services.geo import bounding_box, haversine_m
from app.services.scoring import (
    TideContext,
    build_conditions,
    score_conditions,
)
from app.services.spot_catalog import resolve_spot, unique_slug
from app.services.spot_tiers import (
    HOME_MAX,
    get_or_create_preferences,
    recompute_tiers,
    record_position,
)

router = APIRouter(prefix="/spots", tags=["spots"])


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

    min_lat, max_lat, min_lon, max_lon = bounding_box(lat, lon, radius_km)
    result = await db.execute(
        select(Spot)
        .where(Spot.lat.between(min_lat, max_lat))
        .where(Spot.lon.between(min_lon, max_lon))
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
            )
        )

    nearby.sort(key=lambda item: item.distance_km)
    return nearby[:limit]


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

    spot = Spot(
        slug=await unique_slug(db, data.name, fallback=f"{data.lat:.3f}-{data.lon:.3f}"),
        name=data.name.strip(),
        lat=data.lat,
        lon=data.lon,
        country_code=(data.country_code or "").upper() or None,
        spot_type=spot_type,
        source=SpotSource.USER.value,
        webcam_url=data.webcam_url,
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
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(spot, field, value)
    await db.commit()
    await db.refresh(spot)
    return SpotRead.model_validate(spot)


@router.get("/{spot_ref}/forecast", response_model=SpotForecastResponse)
async def spot_forecast(
    spot_ref: str,
    days: int = Query(default=5, gt=0, le=7),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> SpotForecastResponse:
    """Prévision d'un spot, notée créneau par créneau.

    Déclenche une récupération si le cache a plus de trois heures. Si
    Open-Meteo dépasse cinq secondes, la réponse part avec ce que la base a et
    `refreshing` à `True` : un écran qui met huit secondes ne sera pas rouvert.
    """
    spot = await _get_spot(db, spot_ref)

    refreshing = await ensure_fresh(db, [spot])

    now = datetime.now(UTC)
    # Dernier run seulement : depuis que `run_ts` est dans la clé, une heure
    # porte autant de lignes que de passes d'ingestion.
    result = await db.execute(
        latest_forecasts_select(
            [spot.id],
            start=now.replace(minute=0, second=0, microsecond=0),
        )
        .order_by(Forecast.ts)
        .limit(days * 24)
    )
    forecasts = list(result.scalars().all())

    rows = [
        (
            forecast.ts if forecast.ts.tzinfo else forecast.ts.replace(tzinfo=UTC),
            {
                "wave_height_m": forecast.wave_height_m,
                "wave_direction_deg": forecast.wave_direction_deg,
                "wave_period_s": forecast.wave_period_s,
                "wave_peak_period_s": forecast.wave_peak_period_s,
                "wind_speed_kt": forecast.wind_speed_kt,
                "wind_gust_kt": forecast.wind_gust_kt,
                "wind_direction_deg": forecast.wind_direction_deg,
                "sea_level_m": forecast.sea_level_m,
                "water_temperature_c": forecast.water_temperature_c,
            },
        )
        for forecast in forecasts
    ]
    tide = TideContext.from_levels(
        {ts: values.get("sea_level_m") for ts, values in rows}
    )

    points: list[ForecastPoint] = []
    for (ts, values), forecast in zip(rows, forecasts):
        score = score_conditions(
            build_conditions(ts, values, tide), spot.onshore_dir_deg
        )
        points.append(
            ForecastPoint(
                ts=ts,
                wave_height_m=forecast.wave_height_m,
                wave_direction_deg=forecast.wave_direction_deg,
                wave_period_s=forecast.wave_period_s,
                wave_peak_period_s=forecast.wave_peak_period_s,
                swell_height_m=forecast.swell_height_m,
                swell_direction_deg=forecast.swell_direction_deg,
                swell_period_s=forecast.swell_period_s,
                wind_speed_kt=forecast.wind_speed_kt,
                wind_gust_kt=forecast.wind_gust_kt,
                wind_direction_deg=forecast.wind_direction_deg,
                sea_level_m=forecast.sea_level_m,
                water_temperature_c=forecast.water_temperature_c,
                score=score.value,
                score_level=score.level,
            )
        )

    return SpotForecastResponse(
        spot=SpotRead.model_validate(spot),
        refreshing=bool(refreshing),
        fetched_at=await last_fetched_at(db, spot.id),
        run_ts=await latest_run_ts(db, spot.id),
        points=points,
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
