"""En-têtes de sécurité de l'API, et redirection http → https.

Le front porte déjà les siens (`frontend/next.config.ts`). Ceux-ci sont ceux
de `api-sport.atelier-okomi.fr`, et ils ne font pas double emploi : c'est
l'API qui pose le **cookie de session**, et un cookie posé sur une réponse
servie en clair est un cookie perdu, quel que soit le soin apporté au front.

Trois choix méritent une ligne :

- **La CSP de l'API est `default-src 'none'`.** Une API ne rend que du JSON :
  elle n'a besoin d'aucune source. La seule exception est `/docs` et
  `/redoc`, qui chargent Swagger et ReDoc depuis jsDelivr — on leur sert une
  politique distincte plutôt que d'ouvrir la porte à tout le reste.
- **`frame-ancestors 'none'`** partout : rien de ce que rend l'API n'a de
  raison d'être encadré, à commencer par `/docs`.
- **HSTS est posé même en développement ?** Non : `settings.debug` le coupe.
  Poser un HSTS d'un an sur `localhost` condamnerait le navigateur à refuser
  `http://localhost` pendant un an — pour tous les projets de la machine.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from app.core.config import settings

# Un an, sous-domaines compris (cf. CLAUDE.md, décidé le 13/09).
HSTS_VALUE = "max-age=31536000; includeSubDomains"

# La CSP d'une API qui ne rend que du JSON.
API_CSP = (
    "default-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'; "
    "form-action 'none'; "
    "upgrade-insecure-requests"
)

# Swagger et ReDoc : scripts, styles et polices de jsDelivr, et l'appel à
# `/openapi.json` sur la même origine. Rien de plus.
DOCS_CSP = (
    "default-src 'none'; "
    "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "font-src 'self' https://cdn.jsdelivr.net data:; "
    "img-src 'self' https://fastapi.tiangolo.com data:; "
    "connect-src 'self'; "
    "worker-src 'self' blob:; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "upgrade-insecure-requests"
)

DOCS_PATHS = ("/docs", "/redoc", "/docs/oauth2-redirect")


def _is_local(request: Request) -> bool:
    """Requête vers la machine de développement ? (pas de certificat, pas de HSTS)"""
    host = request.headers.get("host", "").split(":")[0].lower()
    return host in {"localhost", "127.0.0.1", "::1", "testserver", "test"}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Pose les en-têtes, et refuse de servir l'API en clair en production."""

    async def dispatch(self, request: Request, call_next):
        # `x-forwarded-proto` et pas `request.url.scheme` : Railway termine le
        # TLS en amont, l'application ne voit jamais que du http, et se fier au
        # schéma interne donnerait une boucle de redirection infinie.
        forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",")[0]
        if (
            not settings.debug
            and forwarded_proto == "http"
            and not _is_local(request)
        ):
            https_url = request.url.replace(scheme="https")
            # 308 : la méthode et le corps sont conservés. Un 301 transformerait
            # le POST du raccourci iPhone en GET, sans le dire.
            return RedirectResponse(str(https_url), status_code=308)

        response: Response = await call_next(request)
        headers = response.headers

        path = request.url.path
        headers["Content-Security-Policy"] = (
            DOCS_CSP if path in DOCS_PATHS else API_CSP
        )
        headers["X-Content-Type-Options"] = "nosniff"
        headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        headers["Permissions-Policy"] = (
            "geolocation=(self), camera=(), microphone=(), payment=()"
        )
        headers["X-Frame-Options"] = "DENY"

        if not settings.debug and not _is_local(request):
            headers["Strict-Transport-Security"] = HSTS_VALUE

        return response
