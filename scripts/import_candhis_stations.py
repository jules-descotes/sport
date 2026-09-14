"""Import du catalogue des houlographes CANDHIS.

Rejouable, idempotent sur `code`, et **économe** : c'est un import qui coûte du
quota, contrairement à celui d'OSM. Un appel pour la liste de chaque type, puis
**un appel par campagne** pour ses coordonnées. Avec 129 campagnes, l'import
complet dépasserait le plafond quotidien de 140 — d'où trois garde-fous :

1. `--zone` restreint aux campagnes d'une zone (`Z07` = golfe de Gascogne).
   C'est le mode normal : on n'a pas besoin de La Réunion pour surfer à Anglet.
2. L'import est **reprenable**. Une campagne déjà en base avec des coordonnées
   n'est pas réinterrogée, sauf `--refresh`. Épuiser le quota un jour et
   relancer le lendemain finit le travail.
3. `--dry-run` montre ce qui serait écrit **sans rien écrire**, et sans
   dépenser le quota des fiches — la leçon de `sport=surfing`, appliquée : on
   relit avant d'écrire.

La liste (`getCampListe.php`) est la **seule** source de `Actif` — c'est elle
qui dit quelle bouée est vivante, et pas une table écrite à la main.

Usage :
    python -m scripts.import_candhis_stations --zone Z07 --dry-run
    python -m scripts.import_candhis_stations --zone Z07
    python -m scripts.import_candhis_stations --refresh --limit 20
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import Optional, Sequence

from sqlalchemy import select

from app.core.config import settings
from app.db.database import async_session
from app.models.observation_station import ObservationStation
from app.services.candhis import (
    HOULOGRAPHE_TYPES,
    CandhisClient,
    CandhisDisabled,
    CandhisError,
    clean_number,
    iter_codes,
    normalize_label,
)
from app.services.observations import link_spots_to_stations
from app.services.quota import QuotaExhausted, remaining

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s"
)
logger = logging.getLogger("import_candhis_stations")

PROVIDER = "candhis"


def _pick(row: dict, *candidates: str) -> Optional[str]:
    """Lit une colonne par son libellé normalisé.

    Les en-têtes de CANDHIS sont des intitulés humains : on ne les compare
    jamais au caractère près (cf. `services/candhis.normalize_label`).
    """
    wanted = {normalize_label(c) for c in candidates}
    for label, value in row.items():
        if normalize_label(label) in wanted:
            if value is None:
                return None
            text = str(value).strip()
            return text or None
    return None


async def fetch_catalogue(
    client: CandhisClient, zone: Optional[str]
) -> dict[str, dict]:
    """Les campagnes, par code : nom, actif, type de houlographe.

    Un appel par type (trois), plus un pour la zone. Le `type` n'est pas une
    étiquette décorative : il décide de la forme de l'en-tête des mesures, donc
    de ce qu'on saura lire ensuite.
    """
    catalogue: dict[str, dict] = {}

    for houlographe_type in HOULOGRAPHE_TYPES:
        try:
            envelope = await client.campaign_list(houlographe_type)
        except CandhisError as exc:
            # « Aucune donnée » pour un type est une réponse, pas une panne.
            logger.warning("Liste de type %s indisponible : %s", houlographe_type, exc)
            continue

        for row in envelope.rows():
            code = _pick(row, "Code campagne", "N° campagne", "Campagne")
            if not code:
                continue
            catalogue[code] = {
                "code": code,
                "name": _pick(row, "Nom") or code,
                "is_active": (_pick(row, "Actif") or "0") not in {"0", "", "non"},
                "houlographe_type": houlographe_type,
                "data_type": _pick(row, "Type données TR", "Type donnees TR"),
                "is_directional": houlographe_type in {"1", "2"},
            }

    if zone:
        try:
            zone_codes = set(iter_codes(await client.campaign_zone(zone)))
        except CandhisError as exc:
            logger.error("Zone %s indisponible : %s — import interrompu", zone, exc)
            return {}
        before = len(catalogue)
        catalogue = {c: v for c, v in catalogue.items() if c in zone_codes}
        logger.info(
            "Zone %s : %d campagne(s) retenue(s) sur %d", zone, len(catalogue), before
        )

    return catalogue


async def run(
    zone: Optional[str] = None,
    dry_run: bool = False,
    refresh: bool = False,
    limit: Optional[int] = None,
) -> int:
    if not settings.candhis_enabled:
        logger.error(
            "CANDHIS_API_KEY absente : rien à importer. La clé se pose en "
            "variable Railway, jamais dans le dépôt."
        )
        return 1

    async with async_session() as db:
        left = await remaining(db, PROVIDER, settings.candhis_daily_call_cap)
        logger.info("Quota restant aujourd'hui : %d appel(s)", left)

        async with CandhisClient(db) as client:
            try:
                catalogue = await fetch_catalogue(client, zone)
            except QuotaExhausted as exc:
                logger.error("%s — relancer demain, l'import est reprenable", exc)
                return 1
            except CandhisDisabled:
                logger.error("CANDHIS désactivé en cours de route")
                return 1

            if not catalogue:
                logger.error("Aucune campagne trouvée — rien à faire")
                return 1

            existing = {
                station.code: station
                for station in (
                    await db.execute(select(ObservationStation))
                ).scalars()
            }

            # Les fiches coûtent un appel chacune : on ne redemande que ce
            # qu'on n'a pas, sauf --refresh.
            todo = [
                code
                for code in sorted(catalogue)
                if refresh or code not in existing or existing[code].lat is None
            ]
            if limit is not None:
                todo = todo[:limit]

            logger.info(
                "%d campagne(s) au catalogue, %d fiche(s) à récupérer "
                "(1 appel chacune)",
                len(catalogue),
                len(todo),
            )

            if dry_run:
                for code in sorted(catalogue):
                    entry = catalogue[code]
                    logger.info(
                        "  %s %-32s actif=%s type=%s (%s)",
                        code,
                        entry["name"][:32],
                        entry["is_active"],
                        entry["houlographe_type"],
                        entry["data_type"] or "—",
                    )
                logger.info(
                    "--dry-run : rien écrit, aucune fiche demandée. "
                    "Relire la liste ci-dessus avant de relancer sans --dry-run."
                )
                return 0

            fetched = 0
            for code in todo:
                try:
                    envelope = await client.campaign_infos(code)
                except QuotaExhausted as exc:
                    logger.warning(
                        "%s — %d fiche(s) récupérée(s), le reste au prochain "
                        "passage (l'import est reprenable)",
                        exc,
                        fetched,
                    )
                    break
                except CandhisError as exc:
                    logger.warning("Fiche %s indisponible : %s", code, exc)
                    continue

                rows = envelope.rows()
                if not rows:
                    continue
                row = rows[0]
                lat = clean_number(_pick(row, "Latitude"))
                lon = clean_number(_pick(row, "Longitude"))
                if lat is None or lon is None:
                    logger.warning("Fiche %s sans coordonnées — ignorée", code)
                    continue

                catalogue[code].update(
                    {
                        "lat": lat,
                        "lon": lon,
                        "depth_m": clean_number(_pick(row, "Profondeur")),
                        "sensor": _pick(row, "Capteur"),
                        "name": _pick(row, "Nom") or catalogue[code]["name"],
                    }
                )
                fetched += 1

            written, updated = 0, 0
            for code, entry in sorted(catalogue.items()):
                station = existing.get(code)

                if station is None:
                    if entry.get("lat") is None:
                        # Sans position, une station ne sert à rien : elle ne
                        # peut être ni rattachée ni classée par distance. On la
                        # laisse pour le prochain passage.
                        continue
                    station = ObservationStation(code=code, source=PROVIDER)
                    db.add(station)
                    written += 1
                else:
                    updated += 1

                station.name = entry["name"]
                station.is_active = entry["is_active"]
                station.is_directional = entry["is_directional"]
                station.houlographe_type = entry["houlographe_type"]
                station.data_type = entry["data_type"]
                if entry.get("lat") is not None:
                    station.lat = entry["lat"]
                    station.lon = entry["lon"]
                    station.depth_m = entry.get("depth_m")
                    station.sensor = entry.get("sensor")

            await db.commit()
            logger.info(
                "Stations : %d créée(s), %d mise(s) à jour, %d fiche(s) "
                "récupérée(s) cette fois",
                written,
                updated,
                fetched,
            )

        changed = await link_spots_to_stations(db)
        logger.info("Rattachement des spots : %d modifié(s)", changed)

        left = await remaining(db, PROVIDER, settings.candhis_daily_call_cap)
        logger.info("Quota restant après import : %d appel(s)", left)

    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--zone",
        help=(
            "Restreint à une zone CANDHIS : Z07 = golfe de Gascogne, "
            "Z02 = nord Atlantique / Manche ouest. Sans elle, tout le réseau — "
            "et le quota n'y suffira pas en une fois."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Liste les campagnes sans rien écrire ni demander de fiche",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Redemande les fiches déjà connues (coûte un appel chacune)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Nombre maximum de fiches à récupérer sur ce passage",
    )
    args = parser.parse_args(argv)

    return asyncio.run(
        run(
            zone=args.zone,
            dry_run=args.dry_run,
            refresh=args.refresh,
            limit=args.limit,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
