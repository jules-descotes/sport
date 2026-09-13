"""URL de webcam — refus du clair, et tentative de bascule en HTTPS.

L'app est servie en HTTPS. Une webcam en `http:` encadrée dans une page en
`https:` est du **contenu mixte actif** : tous les navigateurs la bloquent,
sans message, depuis des années. Le résultat visible n'est pas « une webcam en
clair », c'est un cadre blanc — et on passe une soirée à chercher le bug côté
prévision.

La règle, décidée le 13/09 :

1. `https:` — accepté tel quel ;
2. `http:` — **jamais stocké en l'état**. On demande la même URL en `https:` ;
   si le site la sert, c'est elle qu'on enregistre. Sinon l'URL est refusée,
   avec la raison ;
3. tout autre schéma (`ftp:`, `javascript:`, `data:`) — refusé sans discussion.

La vérification sort sur le réseau. Elle est donc **courte, et son échec est un
refus, pas une exception** : l'ajout d'une webcam n'est pas un geste urgent, et
enregistrer une URL qu'on n'a pas pu joindre reviendrait à la déclarer bonne.

Depuis le 13/09 (retours n° 4), on vérifie aussi que **l'adresse répond et
qu'elle accepte d'être encadrée** : un 404 et un `X-Frame-Options: DENY`
donnent tous les deux un cadre blanc, et un cadre blanc ment sur l'existence de
l'image. Ces deux refus-là sont des **avertissements**, pas des rejets : le
site peut répondre autrement au navigateur de Jules qu'à une requête venue de
Railway, et refuser une URL correcte serait pire que l'accepter avec une
réserve. L'URL est enregistrée, et la fiche dit ce qu'on a vu.
"""
from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

import httpx

logger = logging.getLogger(__name__)

# Au-delà, on ne fait pas attendre : le site est de toute façon inutilisable
# comme webcam en direct.
PROBE_TIMEOUT_S = 4.0


class WebcamUrlError(ValueError):
    """L'URL ne peut pas être servie depuis une page en HTTPS."""


# Les en-têtes qui interdisent l'encadrement. `frame-ancestors` dans la CSP est
# la version moderne ; `X-Frame-Options` la vieille, encore très répandue.
def _refuses_embedding(headers: "httpx.Headers") -> Optional[str]:
    """La raison pour laquelle ce site refuse d'être encadré, ou `None`."""
    xfo = (headers.get("x-frame-options") or "").strip().lower()
    if xfo in ("deny", "sameorigin") or xfo.startswith("allow-from"):
        return f"le site renvoie X-Frame-Options: {xfo}"

    csp = (headers.get("content-security-policy") or "").lower()
    for directive in csp.split(";"):
        directive = directive.strip()
        if not directive.startswith("frame-ancestors"):
            continue
        sources = directive.split()[1:]
        if not sources or sources == ["'none'"] or sources == ["'self'"]:
            return "le site interdit l'encadrement (frame-ancestors)"
    return None


async def check_embeddable(
    url: str, client: Optional[httpx.AsyncClient] = None
) -> Optional[str]:
    """Un avertissement à afficher, ou `None` quand tout va bien.

    **Jamais un refus.** Le site peut répondre autrement au navigateur de
    Jules qu'à une requête partie d'un conteneur Railway — géoblocage,
    filtrage d'agent, cache. Refuser une URL correcte serait plus coûteux que
    l'accepter en le disant.
    """

    async def _probe(http: httpx.AsyncClient) -> Optional[str]:
        try:
            response = await http.get(url)
        except httpx.HTTPError as exc:
            logger.info("Webcam : %s injoignable (%s)", url, exc)
            return "adresse injoignable depuis le serveur"

        if response.status_code >= 400:
            return f"le site répond {response.status_code}"
        return _refuses_embedding(response.headers)

    if client is not None:
        return await _probe(client)
    async with httpx.AsyncClient(
        timeout=PROBE_TIMEOUT_S, follow_redirects=True
    ) as http:
        return await _probe(http)


def _to_https(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(("https", parts.netloc, parts.path, parts.query, parts.fragment))


async def _serves_https(url: str, client: Optional[httpx.AsyncClient] = None) -> bool:
    """Le site répond-il en HTTPS sur cette URL ?

    `GET` et pas `HEAD` : beaucoup de serveurs de webcam répondent 405 à un
    HEAD tout en servant parfaitement la page. On ne lit pas le corps — les
    en-têtes suffisent, et `stream` évite de télécharger une image de deux
    mégaoctets pour une question de schéma.
    """

    async def _probe(http: httpx.AsyncClient) -> bool:
        try:
            async with http.stream("GET", url) as response:
                return response.status_code < 400
        except Exception as exc:
            logger.info("Webcam : %s injoignable en HTTPS (%s)", url, exc)
            return False

    if client is not None:
        return await _probe(client)
    async with httpx.AsyncClient(
        timeout=PROBE_TIMEOUT_S, follow_redirects=True
    ) as http:
        return await _probe(http)


async def normalize_webcam_url(
    url: Optional[str], client: Optional[httpx.AsyncClient] = None
) -> Optional[str]:
    """Valide et normalise une URL de webcam. Lève `WebcamUrlError` si elle ne va pas.

    Rend `None` pour une entrée vide — c'est le geste « retirer la webcam »,
    et il doit rester possible.
    """
    if url is None:
        return None

    candidate = url.strip()
    if not candidate:
        return None

    parts = urlsplit(candidate)
    if not parts.netloc:
        raise WebcamUrlError(
            "URL de webcam incomplète : il faut l'adresse entière, "
            "https://… comprise."
        )

    scheme = parts.scheme.lower()
    if scheme == "https":
        return candidate

    if scheme != "http":
        raise WebcamUrlError(
            f"Schéma « {parts.scheme} » refusé : seul https est accepté."
        )

    # http : on tente la même adresse en https avant de refuser.
    upgraded = _to_https(candidate)
    if await _serves_https(upgraded, client):
        logger.info("Webcam : %s réécrite en %s", candidate, upgraded)
        return upgraded

    raise WebcamUrlError(
        "Cette webcam n'est servie qu'en http : elle serait bloquée comme "
        "contenu mixte dans l'app. Cherche son adresse https, ou garde-la "
        "comme simple lien dans ton navigateur."
    )
