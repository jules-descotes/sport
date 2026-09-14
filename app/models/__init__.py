"""Le registre des modèles — **le seul endroit** qui sait quoi charger.

SQLAlchemy résout les relations écrites en chaîne — `relationship("User")` —
au moment où il configure les mappers, et il ne peut résoudre que ce qui a été
**importé**. Il suffit donc qu'un point d'entrée oublie un module pour que la
première requête lève `InvalidRequestError`, et pas avant : ni l'import, ni le
`--help`, ni un `--dry-run` qui s'arrête tôt ne le montrent.

C'est ce qui est arrivé le 15/09 à `scripts/import_candhis_stations.py`. La
liste des modèles vivait dans `app/main.py`, à raison d'une ligne d'import par
modèle — donc le serveur la tenait à jour et les scripts, non. Chacun importait
les trois modules dont il parlait, et tombait sur le quatrième.

La liste est **explicite** et non déduite d'un `glob` : un fichier de modèle se
lit ici, et l'ordre de chargement reste sous contrôle. Pour qu'elle ne prenne
pas de retard sur le dossier, c'est un test qui compare les deux
(`tests/test_model_registry.py`) — sinon un modèle ajouté dans un an
redonnerait exactement la même panne, sans personne pour s'en souvenir.
"""
from __future__ import annotations

import importlib
from types import ModuleType

# Un module par agrégat, dans l'ordre alphabétique. `enums` n'est pas là :
# il ne déclare aucune table, seulement des valeurs.
MODEL_MODULES: tuple[str, ...] = (
    "api_quota",
    "api_token",
    "calibration",
    "daily_log",
    "exercise",
    "forecast",
    "formula",
    "gear",
    "habit",
    "nutrition",
    "objective",
    "observation_station",
    "profile",
    "session_segment",
    "spot",
    "spot_rule",
    "surf_session",
    "thresholds",
    "user",
    "workout",
)

_loaded: tuple[str, ...] | None = None


def load_all_models() -> tuple[str, ...]:
    """Importe tous les modules de modèles. Idempotent.

    Idempotent pour de vrai, et c'est nécessaire : `main.py` l'appelle, chaque
    script l'appelle, et un script importé par un autre l'appellerait deux
    fois. `importlib.import_module` sert déjà le module depuis `sys.modules`
    au deuxième appel — donc aucune table n'est redéclarée — et le drapeau
    évite même de refaire le tour.

    Renvoie les noms chargés, pour que le contrôle soit lisible dans un test
    et dans un journal.
    """
    global _loaded
    if _loaded is not None:
        return _loaded

    for name in MODEL_MODULES:
        importlib.import_module(f"{__name__}.{name}")

    _loaded = MODEL_MODULES
    return _loaded


def module(name: str) -> ModuleType:
    """Un module de modèle par son nom court, une fois le registre chargé."""
    load_all_models()
    return importlib.import_module(f"{__name__}.{name}")


__all__ = ["MODEL_MODULES", "load_all_models", "module"]
