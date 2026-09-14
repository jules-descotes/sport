"""Tout point d'entrée enregistre **tous** les modèles, ou il ne démarre pas.

Le 15/09, `scripts/import_candhis_stations.py` plantait avant le moindre appel
réseau : `InvalidRequestError`, le mapper `Profile` ne trouvait pas `User`.
SQLAlchemy résout les relations écrites en chaîne (`relationship("User")`) au
moment où il configure les mappers, et il ne peut résoudre que ce qui a été
**importé**. `app/main.py` importait les vingt-deux modèles un par un ; les
scripts importaient les trois dont ils parlaient.

Ce n'était donc pas un bug de script, mais un bug d'architecture : la liste des
modèles à charger vivait dans `main.py`, là où seul le serveur la lisait.

D'où ce test, et sa forme :

- **un interpréteur frais par module.** Dans le processus pytest, `app.main`
  est déjà importé, donc tous les modèles le sont aussi, et n'importe quel
  script passerait. Le bug ne se voit que dans un processus qui n'a chargé que
  le script. Un test qui ne le ferait pas serait vert sur le code cassé.
- **`configure_mappers()` explicitement.** L'import seul ne résout rien :
  SQLAlchemy attend la première requête. C'est exactement pour ça que le bug
  n'a été vu qu'en production, et pas au `--help`.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"


def script_modules() -> list[str]:
    return sorted(
        f"scripts.{path.stem}"
        for path in SCRIPTS.glob("*.py")
        if not path.stem.startswith("_")
    )


def run_in_fresh_interpreter(module: str) -> subprocess.CompletedProcess:
    """Importe `module` et configure les mappers, dans un processus neuf."""
    code = (
        "import importlib\n"
        "from sqlalchemy.orm import configure_mappers\n"
        f"importlib.import_module({module!r})\n"
        "configure_mappers()\n"
        "print('OK')\n"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_there_is_at_least_one_script_to_check() -> None:
    """Sans ce garde-fou, un dossier vide rendrait le test suivant vert.

    Un contrôle qu'on n'a jamais vu refuser quelque chose ne garde rien
    (cf. CLAUDE.md, panne du 14/09).
    """
    assert len(script_modules()) >= 5


@pytest.mark.parametrize("module", script_modules())
def test_a_script_alone_can_configure_every_mapper(module: str) -> None:
    """Chaque script, seul dans son interpréteur, doit tenir debout.

    C'est le test qui échouait avant la correction : `import_candhis_stations`,
    `backfill_candhis` et les autres tombaient sur `InvalidRequestError`.
    """
    result = run_in_fresh_interpreter(module)
    assert result.returncode == 0, (
        f"{module} ne configure pas les mappers seul :\n"
        f"{result.stderr[-1500:]}\n\n"
        "Le script doit appeler `load_all_models()` "
        "(`from app.models import load_all_models`) avant toute requête."
    )
    assert "OK" in result.stdout


def test_the_app_itself_configures_every_mapper() -> None:
    """La même exigence pour le serveur, par le même chemin."""
    result = run_in_fresh_interpreter("app.main")
    assert result.returncode == 0, result.stderr[-1500:]


def test_load_all_models_is_idempotent() -> None:
    """Appelé deux fois, il ne redéclare rien.

    Les scripts et `main.py` peuvent l'appeler chacun : SQLAlchemy lèverait sur
    une table déclarée deux fois, et c'est la panne qu'on ne veut pas créer en
    réparant celle-ci.
    """
    from app.models import load_all_models

    first = load_all_models()
    second = load_all_models()
    assert first == second
    assert len(first) >= 20


def test_every_model_module_is_loaded() -> None:
    """La liste ne doit pas prendre du retard sur le dossier.

    Un modèle ajouté demain et oublié ici redonnerait exactement la panne du
    15/09, un an plus tard et sans personne pour s'en souvenir.
    """
    from app.models import MODEL_MODULES

    on_disk = {
        path.stem
        for path in (REPO / "app" / "models").glob("*.py")
        if path.stem not in {"__init__", "enums"}
    }
    assert on_disk == set(MODEL_MODULES), (
        "app/models/__init__.py doit lister tous les modules de modèles : "
        f"manquants {sorted(on_disk - set(MODEL_MODULES))}, "
        f"en trop {sorted(set(MODEL_MODULES) - on_disk)}"
    )
