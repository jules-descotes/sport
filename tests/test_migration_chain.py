"""Une migration ne peut dépendre que d'une révision **commitée dans ce dépôt**.

Ce test existe à cause de deux pannes de production le 13/09, la même à une
heure d'écart. Deux sessions travaillaient en parallèle sur le même dépôt ;
chacune a écrit une migration chaînée sur celle de l'autre, encore non
commitée. Sur la machine, la chaîne était complète et tous les tests passaient.
Sur Railway, `alembic upgrade head` tombait sur `KeyError: '0015'`, le
démarrage échouait, et l'API répondait 502.

Le contrôle habituel — « toutes les migrations s'appliquent à l'endroit et à
l'envers » — ne l'attrape pas : il lit le répertoire de travail, où le fichier
manquant est bien là. **Il faut interroger git**, et c'est la seule chose que
ce fichier fait.

Il vérifie aussi qu'il n'y a **qu'une seule tête**. Deux migrations partant du
même parent donnent exactement la même panne, avec un autre message : « Multiple
head revisions are present ».
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
VERSIONS = REPO / "alembic" / "versions"

REVISION = re.compile(r'^revision:\s*str\s*=\s*"([^"]+)"', re.M)
# Tout ce qui suit `down_revision` jusqu'au `=`. L'annotation contient des
# crochets imbriqués (`Union[str, Sequence[str], None]`) : les décrire
# exactement était plus fragile que de les sauter.
DOWN = re.compile(r'^down_revision[^=\n]*=\s*("([^"]+)"|None)', re.M)


def _tracked_migrations() -> dict[str, str]:
    """`{révision: nom de fichier}` pour les seules migrations **commitées**.

    `git ls-files` et pas un parcours du répertoire : c'est toute la
    différence entre ce qui part en production et ce qui traîne sur la
    machine.
    """
    result = subprocess.run(
        ["git", "ls-files", "alembic/versions/*.py"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip("git indisponible : le contrôle de chaîne ne peut pas tourner")

    revisions: dict[str, str] = {}
    for line in result.stdout.splitlines():
        path = REPO / line.strip()
        if not path.exists() or path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8")
        match = REVISION.search(text)
        if match:
            revisions[match.group(1)] = path.name
    return revisions


def _down_revision(filename: str) -> str | None:
    text = (VERSIONS / filename).read_text(encoding="utf-8")
    match = DOWN.search(text)
    if match is None:
        return None
    return match.group(2)


def test_every_parent_is_a_committed_revision() -> None:
    """Le contrôle qui aurait évité les deux 502 du 13/09."""
    tracked = _tracked_migrations()
    assert tracked, "aucune migration suivie par git — dépôt inattendu"

    orphans = []
    for revision, filename in sorted(tracked.items()):
        parent = _down_revision(filename)
        if parent is None:
            continue
        if parent not in tracked:
            orphans.append(f"{filename} dépend de « {parent} », qui n'est pas commité")

    assert not orphans, (
        "Migration(s) chaînée(s) sur une révision absente du dépôt :\n  "
        + "\n  ".join(orphans)
        + "\n\nEn production, `alembic upgrade head` lèvera KeyError et "
        "l'application ne démarrera pas."
    )


def test_there_is_exactly_one_head() -> None:
    """Deux migrations partant du même parent donnent la même panne.

    Le message est seulement différent : « Multiple head revisions are
    present », et `alembic upgrade head` refuse de choisir.
    """
    tracked = _tracked_migrations()
    parents = {
        _down_revision(filename)
        for filename in tracked.values()
        if _down_revision(filename) is not None
    }
    heads = sorted(set(tracked) - parents)

    assert len(heads) == 1, (
        f"{len(heads)} têtes de migration commitées : {heads}. "
        "Une seule est acceptable — sinon `alembic upgrade head` échoue."
    )


def test_no_two_migrations_share_a_parent() -> None:
    """La branche se voit ici, avant de se voir en production."""
    tracked = _tracked_migrations()
    by_parent: dict[str, list[str]] = {}
    for revision, filename in tracked.items():
        parent = _down_revision(filename)
        if parent is None:
            continue
        by_parent.setdefault(parent, []).append(filename)

    forks = {
        parent: names for parent, names in by_parent.items() if len(names) > 1
    }
    assert not forks, f"Deux migrations partent du même parent : {forks}"
