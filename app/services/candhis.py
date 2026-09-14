"""Client CANDHIS — bouées du Cerema. Un seul endroit parle à l'extérieur.

Tout ce qui suit vient de `docs/CANDHIS.md`, lu dans la documentation du Cerema
avant d'écrire une ligne. Quatre traits de cette API commandent ce fichier, et
aucun n'était devinable :

1. **`success` se lit toujours.** Un échec métier — pas de données, valeur de
   paramètre non reconnue — répond **HTTP 200** avec `success: False`. Un
   client qui se contenterait de `raise_for_status()` prendrait « aucune
   donnée » pour un succès et écrirait une passe vide sans un mot.
2. **`999.9999` est la valeur manquante**, et elle apparaît sur `Hmax` et sur
   la température dans les exemples de la documentation elle-même.
3. **`entete` change selon le type de houlographe.** Trois formes existent, et
   elles ne portent même pas la même période. Un index de colonne codé en dur
   ne peut pas marcher : on apparie sur le **libellé normalisé**.
4. **Les dates sont des jours, pas des instants.** Aucune fenêtre de trois
   heures ne se demande à cette API ; elle se découpe côté client.

Et une règle de tenue : **tout appel passe par le compteur de quota**, backfill
compris. Le compteur est dans `services/quota.py`, il est persisté, et il
refuse *avant* le réseau.
"""
from __future__ import annotations

import calendar
import logging
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Iterable, Optional, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.quota import reserve

logger = logging.getLogger(__name__)

PROVIDER = "candhis"

# Au-delà, c'est un code d'absence et pas une mesure (cf. docs/CANDHIS.md §4.6).
# Le seuil est bas exprès : aucune grandeur mesurée ici — hauteur en mètres,
# période en secondes, direction en degrés, température en °C — ne s'approche
# de 999.
MISSING_SENTINEL = 999.0

# Types de houlographe, tels que les numérote `getCampListe.php`.
TYPE_NON_DIRECTIONNEL_H13 = "0"
TYPE_DIRECTIONNEL_HM0 = "1"
TYPE_DIRECTIONNEL_H13 = "2"
HOULOGRAPHE_TYPES = (
    TYPE_NON_DIRECTIONNEL_H13,
    TYPE_DIRECTIONNEL_HM0,
    TYPE_DIRECTIONNEL_H13,
)

# L'intervalle maximum d'une requête de données, imposé par l'API.
MAX_RANGE_MONTHS = 12

ONE_DAY = timedelta(days=1)


class CandhisDisabled(RuntimeError):
    """Pas de clé : la fonctionnalité est éteinte, ce n'est pas une panne."""


class CandhisError(RuntimeError):
    """L'API a répondu, et elle a dit non. `message` porte sa raison à elle."""


def normalize_label(label: str) -> str:
    """Réduit un libellé de colonne à sa forme comparable.

    Les en-têtes de CANDHIS sont des **intitulés humains** — accents, unités,
    points, espaces : `"Dir. au pic (°)"`, `"Temp. mer (°C)"`. On ne peut pas
    en jurer au caractère près, et ils n'ont aucune raison d'être stables d'une
    version de l'API à l'autre. On les compare donc sans accent, sans casse et
    sans ponctuation : `"Dir. au pic (°)"` et `"Dir au pic(deg)"` tombent tous
    les deux sur `diraupic`, et la colonne est reconnue dans les deux cas.
    """
    folded = unicodedata.normalize("NFD", label or "")
    folded = "".join(c for c in folded if unicodedata.category(c) != "Mn")
    return "".join(c for c in folded.lower() if c.isalnum())


# Libellé normalisé -> colonne d'`observations`.
#
# `H1/3` et `Hm0` tombent dans la **même** colonne, et c'est assumé : ce sont
# deux estimateurs très proches de la hauteur significative, la littérature les
# échange couramment, et `raw` garde le libellé d'origine pour le jour où
# l'écart comptera. `T02` en revanche est une période **moyenne** et ne partage
# sa colonne avec personne.
COLUMN_BY_LABEL: dict[str, str] = {
    "hm0m": "hm0_m",
    "h13m": "hm0_m",
    "hmaxm": "wave_height_max_m",
    "t02s": "mean_period_s",
    "th13s": "peak_period_s",
    "taupics": "peak_period_s",
    "diraupic": "wave_direction_deg",
    "etalaupic": "directional_spread_deg",
    "tempmerc": "water_temperature_c",
}

# Quand deux libellés visent la même colonne, le plus fort gagne — et il gagne
# même s'il arrive après dans l'en-tête.
#
# Le cas n'est pas théorique : le houlographe **non directionnel** publie
# `TH1/3` *et* `T. au pic` dans la même ligne (11,0 s et 16,7 s dans l'exemple
# du Cerema). Ce sont deux grandeurs différentes — l'une est la période moyenne
# du tiers supérieur des vagues, l'autre le pic du spectre — et prendre la
# première venue retiendrait 11 s là où la période de pic vaut 16,7 s. Cinq
# secondes d'écart sur la grandeur qui décide si une houle est exploitable.
#
# `TH1/3` reste le repli, et c'est volontaire : les houlographes H13
# directionnels — dont ceux de la côte basque — ne publient **que** lui. Sans
# ce repli, la bouée maison n'aurait aucune période, et la calibration des
# périodes n'aurait jamais rien à comparer.
LABEL_PRIORITY: dict[str, int] = {
    "hm0m": 2,
    "h13m": 1,
    "taupics": 2,
    "th13s": 1,
}
DEFAULT_PRIORITY = 1

# Repli par préfixe, pour les mêmes libellés écrits autrement (`(deg)` au lieu
# de `(°)`, une unité omise). Ordonné : le premier qui correspond gagne.
PREFIX_FALLBACKS: tuple[tuple[str, str], ...] = (
    ("hm0", "hm0_m"),
    ("h13", "hm0_m"),
    ("hmax", "wave_height_max_m"),
    ("t02", "mean_period_s"),
    ("th13", "peak_period_s"),
    ("taupic", "peak_period_s"),
    ("diraupic", "wave_direction_deg"),
    ("etal", "directional_spread_deg"),
    ("tempmer", "water_temperature_c"),
)

DATE_LABELS = {"date", "dateheure"}
STATION_LABELS = {"campagne"}


def column_for(label: str) -> Optional[str]:
    key = normalize_label(label)
    if key in COLUMN_BY_LABEL:
        return COLUMN_BY_LABEL[key]
    for prefix, column in PREFIX_FALLBACKS:
        if key.startswith(prefix):
            return column
    return None


def priority_for(label: str) -> int:
    key = normalize_label(label)
    if key in LABEL_PRIORITY:
        return LABEL_PRIORITY[key]
    for prefix, rank in (("taupic", 2), ("hm0", 2), ("th13", 1), ("h13", 1)):
        if key.startswith(prefix):
            return rank
    return DEFAULT_PRIORITY


def clean_number(value: Any) -> Optional[float]:
    """Un nombre, ou `None` — jamais 999.9999 pris au premier degré."""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", ".")
        if not value:
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if abs(number) >= MISSING_SENTINEL:
        return None
    return number


def _tzinfo() -> ZoneInfo:
    """Le fuseau des horodatages CANDHIS, qui n'est **pas** documenté.

    Cf. docs/CANDHIS.md §5. UTC par défaut ; la variable existe pour corriger
    sans redéployer. Un nom de fuseau invalide retombe sur UTC en le disant
    plutôt que d'empêcher le service de démarrer.
    """
    name = (settings.candhis_tz or "UTC").strip() or "UTC"
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        logger.error("CANDHIS_TZ=%r inconnu — UTC retenu à la place", name)
        return ZoneInfo("UTC")


def parse_timestamp(raw: Any) -> Optional[datetime]:
    """`2022-03-26 00:00` ou `2022-01-01 00:00:00`, rendus en UTC."""
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        logger.warning("horodatage CANDHIS illisible : %r — ligne ignorée", raw)
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=_tzinfo())
    return moment.astimezone(UTC)


@dataclass
class Measurement:
    """Une ligne de mesure, déjà traduite en colonnes d'`observations`."""

    ts: datetime
    values: dict[str, Optional[float]]
    raw: dict[str, Any]
    station_code: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        """Une ligne dont **toutes** les valeurs sont absentes n'apprend rien.

        Ça arrive : la bouée émet son horodatage et des 999.9999 partout
        pendant une avarie. L'écrire remplirait la table de lignes vides que la
        calibration devrait ensuite apprendre à ignorer.
        """
        return not any(v is not None for v in self.values.values())


@dataclass
class Envelope:
    """La réponse CANDHIS, déjà vérifiée : `success`, `entete`, `results`."""

    success: bool
    message: str
    entete: list[str] = field(default_factory=list)
    results: list[Any] = field(default_factory=list)
    api_version: str = ""

    def rows(self) -> list[dict[str, Any]]:
        """Apparie chaque ligne à son en-tête.

        `getCampZone.php` est l'exception qui oblige à regarder : son `results`
        est une liste **plate de chaînes** et non une liste de lignes. Les
        dérouler comme des tableaux lirait les caractères un par un.
        """
        if not self.entete:
            return []
        if len(self.entete) == 1:
            label = self.entete[0]
            return [
                {label: row[0] if isinstance(row, (list, tuple)) and row else row}
                for row in self.results
                if not isinstance(row, dict)
            ]

        paired: list[dict[str, Any]] = []
        for row in self.results:
            if not isinstance(row, (list, tuple)):
                logger.warning(
                    "ligne CANDHIS inattendue (%s) — ignorée", type(row).__name__
                )
                continue
            if len(row) != len(self.entete):
                # On apparie quand même sur la partie commune : une colonne
                # ajoutée en fin de tableau ne doit pas faire perdre la houle.
                logger.warning(
                    "ligne CANDHIS de %d valeurs pour %d colonnes — "
                    "appariement sur la partie commune",
                    len(row),
                    len(self.entete),
                )
            paired.append(dict(zip(self.entete, row)))
        return paired

    def measurements(self) -> list[Measurement]:
        """Les lignes lisibles, en colonnes d'`observations`.

        Une ligne qu'on ne sait pas lire est **journalisée et sautée**, jamais
        levée : une avarie de bouée ne doit pas faire tomber la passe entière.
        """
        out: list[Measurement] = []
        for row in self.rows():
            ts: Optional[datetime] = None
            station: Optional[str] = None
            values: dict[str, Optional[float]] = {}
            # Quel libellé a rempli chaque colonne, pour arbitrer un doublon.
            filled_by: dict[str, int] = {}

            for label, value in row.items():
                key = normalize_label(label)
                if key in DATE_LABELS:
                    ts = parse_timestamp(value)
                    continue
                if key in STATION_LABELS:
                    station = str(value).strip() if value is not None else None
                    continue
                column = column_for(label)
                if column is None:
                    continue

                number = clean_number(value)
                rank = priority_for(label)

                if column not in values:
                    values[column] = number
                    filled_by[column] = rank
                    continue

                # La colonne est déjà prise. On ne la remplace que si le
                # nouveau libellé est **meilleur** et porte vraiment une
                # valeur : un `T. au pic` à 999.9999 ne doit pas effacer un
                # `TH1/3` mesuré, et un `TH1/3` ne doit jamais écraser un
                # `T. au pic` qui, lui, est la vraie période de pic.
                if number is None:
                    continue
                if values[column] is None or rank > filled_by.get(column, 0):
                    values[column] = number
                    filled_by[column] = rank

            if ts is None:
                logger.warning("ligne CANDHIS sans date exploitable — ignorée")
                continue

            out.append(
                Measurement(ts=ts, values=values, raw=row, station_code=station)
            )
        return out


def parse_envelope(payload: Any) -> Envelope:
    """Vérifie l'enveloppe. Lève `CandhisError` quand l'API dit non."""
    if not isinstance(payload, dict):
        raise CandhisError(
            f"réponse CANDHIS inattendue : {type(payload).__name__} au lieu d'un objet"
        )

    raw_success = payload.get("success")
    # L'API écrit tantôt `True`, tantôt `"True"`, tantôt `true` — les trois
    # apparaissent dans sa propre documentation.
    success = raw_success is True or (
        isinstance(raw_success, str) and raw_success.strip().lower() == "true"
    )
    message = str(payload.get("message") or "")

    if not success:
        raise CandhisError(message or "CANDHIS a répondu success=False sans message")

    entete = payload.get("entete")
    results = payload.get("results")
    if not isinstance(entete, list) or not isinstance(results, list):
        raise CandhisError(
            f"CANDHIS a répondu success=True sans tableau exploitable ({message!r})"
        )

    return Envelope(
        success=True,
        message=message,
        entete=[str(label) for label in entete],
        results=results,
        api_version=str(payload.get("apiVer") or ""),
    )


class CandhisClient:
    """Enveloppe httpx : clé, quota persisté, vérification de l'enveloppe.

    Le client prend la session de base de données parce que le compteur de
    quota est en base, et que le compteur n'a de valeur que s'il est le seul
    chemin. Pas de session, pas d'appel.
    """

    def __init__(
        self,
        db: AsyncSession,
        client: Optional[httpx.AsyncClient] = None,
        api_key: Optional[str] = None,
        cap: Optional[int] = None,
    ) -> None:
        self._db = db
        self._client = client
        self._owns_client = client is None
        self._api_key = (api_key if api_key is not None else settings.candhis_api_key)
        self._cap = cap if cap is not None else settings.candhis_daily_call_cap

    @property
    def enabled(self) -> bool:
        return bool((self._api_key or "").strip())

    async def __aenter__(self) -> "CandhisClient":
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get(self, path: str, params: dict[str, Any]) -> Envelope:
        if not self.enabled:
            raise CandhisDisabled("CANDHIS_API_KEY absente : fonctionnalité éteinte")
        if self._client is None:  # pragma: no cover - usage hors contexte
            raise RuntimeError("CandhisClient doit être utilisé comme contexte async")

        # Avant le réseau. Lève `QuotaExhausted` sans rien consommer.
        await reserve(self._db, PROVIDER, self._cap)

        url = f"{settings.candhis_url.rstrip('/')}/{path}"
        # Le jeton est nu, sans `Bearer` : c'est ce que montre l'exemple curl
        # de la documentation du Cerema.
        headers = {"Authorization": self._api_key.strip()}
        response = await self._client.get(url, params=params, headers=headers)

        if response.status_code == 429:
            raise CandhisError(
                "CANDHIS a renvoyé 429 : quota quotidien atteint de leur côté"
            )
        if response.status_code == 423:
            raise CandhisError(
                "CANDHIS a renvoyé 423 : ressource verrouillée (IP bannie)"
            )
        if response.status_code == 401:
            raise CandhisError("CANDHIS a renvoyé 401 : jeton refusé")
        response.raise_for_status()

        try:
            payload = response.json()
        except ValueError as exc:
            raise CandhisError(f"réponse CANDHIS illisible : {exc}") from exc

        return parse_envelope(payload)

    # -- Catalogue ---------------------------------------------------------

    async def campaign_list(self, houlographe_type: Optional[str] = None) -> Envelope:
        """`getCampListe.php` — code, nom, **actif**, type de données TR.

        C'est le seul endpoint qui dit `Actif`. C'est donc lui qui décide
        quelle bouée est vivante, et pas une liste écrite à la main.
        """
        params: dict[str, Any] = {}
        if houlographe_type is not None:
            params["type"] = houlographe_type
        return await self._get("getCampListe.php", params)

    async def campaign_infos(self, code: str) -> Envelope:
        """`getCampInfos.php` — nom, lat, lon, profondeur, capteur."""
        return await self._get("getCampInfos.php", {"camp": code})

    async def campaign_zone(self, zone: str) -> Envelope:
        """`getCampZone.php` — les codes d'une zone (`Z07` = golfe de Gascogne)."""
        return await self._get("getCampZone.php", {"zone": zone})

    # -- Mesures -----------------------------------------------------------

    async def real_time(
        self, code: str, start: date, end: Optional[date] = None
    ) -> list[Measurement]:
        """`getCampTR.php` — les mesures d'une campagne, par **journées**.

        `dateFin` est toujours envoyé, même quand il vaut `dateDeb` : sans lui
        l'API le met à `dateDeb + 12 mois`, et un job horaire qui l'oublierait
        demanderait une année entière à chaque passe.
        """
        params = {
            "camp": code,
            "dateDeb": start.isoformat(),
            "dateFin": (end or start).isoformat(),
        }
        envelope = await self._get("getCampTR.php", params)
        return envelope.measurements()

    async def latest_for(
        self, codes: Sequence[str], houlographe_type: str
    ) -> list[Measurement]:
        """`getCampListeTR.php` — la dernière mesure de plusieurs campagnes.

        Un appel pour N bouées, mais **un seul point** : il ne rattrape aucun
        trou. Gardé pour le jour où on suivra plusieurs bouées.
        """
        params: dict[str, Any] = {"type": houlographe_type}
        if codes:
            params["camp"] = ",".join(codes)
        envelope = await self._get("getCampListeTR.php", params)
        return envelope.measurements()


def day_chunks(start: date, end: date, months: int = MAX_RANGE_MONTHS) -> list[
    tuple[date, date]
]:
    """Découpe un intervalle en tranches que l'API accepte.

    L'API plafonne à 12 mois et **corrige la date de fin d'office** en le
    disant dans `message`. On préfère découper nous-mêmes : une tranche tronquée
    en silence laisserait un trou qu'aucun rejeu ne viendrait combler, puisque
    la passe suivante repartirait d'après.
    """
    if end < start:
        return []

    chunks: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        year = cursor.year + (cursor.month - 1 + months) // 12
        month = (cursor.month - 1 + months) % 12 + 1
        day = min(cursor.day, _days_in_month(year, month))
        # Une tranche s'arrête la veille du même jour N mois plus tard : deux
        # tranches consécutives ne doivent pas se chevaucher d'une journée.
        stop = min(end, date(year, month, day) - ONE_DAY)
        chunks.append((cursor, stop))
        cursor = stop + ONE_DAY
    return chunks


def _days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def iter_codes(envelope: Envelope) -> Iterable[str]:
    """Les codes de campagne d'une réponse `getCampZone.php`."""
    for row in envelope.rows():
        for value in row.values():
            if value:
                yield str(value).strip()
