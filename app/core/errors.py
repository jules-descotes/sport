"""Le 500 qui traverse CORS.

Bug de production du 13/09 : `PATCH /sessions/1` avec des segments levait une
`IntegrityError`, et le navigateur n'affichait pas « erreur 500 » mais une
**erreur CORS**. Le diagnostic était donc doublement faux — on cherchait une
origine mal déclarée alors que la base refusait une ligne.

La cause tient à l'ordre des couches de Starlette :

```
ServerErrorMiddleware → SecurityHeaders → CORS → ExceptionMiddleware → routes
```

Une exception non rattrapée remonte jusqu'à `ServerErrorMiddleware`, qui est
**au-dessus** de `CORSMiddleware` : sa réponse 500 redescend sans repasser par
lui, donc sans `Access-Control-Allow-Origin`. Le navigateur, qui ne voit jamais
le statut d'une réponse sans en-tête CORS, annonce une erreur d'origine.

Et un `app.add_exception_handler(Exception, ...)` ne corrige rien : FastAPI
confie ce handler-là à `ServerErrorMiddleware`, exactement au même endroit.
Le seul moyen d'être **sous** CORS est d'être un middleware, ajouté à l'app
avant lui (Starlette empile les middlewares à l'envers de leur déclaration).

Ce qui sort d'ici est sobre : un identifiant d'erreur et rien d'autre. Le
traceback va dans les logs Railway et dans Sentry, pas dans la réponse — et
l'identifiant est ce qui permet de retrouver l'un depuis l'autre.
"""
from __future__ import annotations

import logging
import uuid

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)


class ServerErrorJsonMiddleware:
    """Rattrape ce qui n'a pas été rattrapé, et répond du JSON.

    ASGI brut plutôt que `BaseHTTPMiddleware` : il faut savoir si la réponse a
    déjà commencé à partir. Une fois les en-têtes envoyés, il est trop tard
    pour changer d'avis — on laisse alors l'exception remonter, et la connexion
    se coupe comme elle l'aurait fait de toute façon.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def sender(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, sender)
        except Exception as exc:  # noqa: BLE001 — c'est le but du middleware
            error_id = uuid.uuid4().hex[:12]
            logger.error(
                "Erreur %s sur %s %s",
                error_id,
                scope.get("method", "?"),
                scope.get("path", "?"),
                exc_info=exc,
            )
            _report(exc, error_id)

            if started:
                # Les en-têtes sont partis : plus rien à négocier.
                raise

            response = JSONResponse(
                status_code=500,
                content={
                    "detail": "Erreur interne",
                    "error_id": error_id,
                },
            )
            await response(scope, receive, send)


def _report(exc: BaseException, error_id: str) -> None:
    """Sentry, s'il est branché — sinon rien, et surtout pas une seconde erreur.

    Ce middleware est **sous** l'intégration ASGI de Sentry : en avalant
    l'exception, il la lui cacherait. On la lui remet donc à la main, étiquetée
    par le même identifiant que la ligne de log et que la réponse.
    """
    from app.core.config import settings

    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk

        with sentry_sdk.new_scope() as scope:
            scope.set_tag("error_id", error_id)
            sentry_sdk.capture_exception(exc)
    except Exception:  # noqa: BLE001
        logger.debug("Sentry indisponible pour l'erreur %s", error_id)
