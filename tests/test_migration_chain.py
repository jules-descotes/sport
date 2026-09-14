"""La chaîne de migrations, vérifiée là où elle casse : sur Postgres.

Ce fichier a deux moitiés, et elles ont deux histoires.

**Les contrôles statiques** viennent des deux pannes du 13/09 : deux sessions
en parallèle, chacune chaînant sa migration sur celle de l'autre, encore non
commitée. Sur la machine tout passait ; sur Railway, `alembic upgrade head`
tombait sur `KeyError`, et l'API répondait 502. Ils lisent **git**, pas le
répertoire de travail — c'est toute la différence entre ce qui part en
production et ce qui traîne sur un poste.

**L'aller-retour sur Postgres** vient de la panne du 14/09, et il dit une
chose que les tests SQLite ne pourront jamais dire. La migration du menu
posait `server_default=sa.text("0")` sur une colonne booléenne. SQLite range
les booléens dans des entiers : `DEFAULT 0` y passe sans un mot, et
l'aller-retour complet de `test_migrations.py` était **vert**. Postgres a un
vrai type booléen, refuse l'entier, et la production ne démarrait plus.

La leçon n'est pas « il manquait un test » — il y en avait un, il passait.
Elle est que **le moteur des tests doit être celui de la production**. SQLite
reste pour les tests unitaires, parce qu'une suite de 750 tests qui monte un
Postgres à chaque fixture ne se lance plus ; mais la chaîne, elle, n'est
déclarée bonne que si Postgres l'a jouée.
"""
from __future__ import annotations

import ast
import asyncio
import os
import re
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from tests._alembic import run_alembic

REPO = Path(__file__).resolve().parent.parent
VERSIONS = REPO / "alembic" / "versions"

REVISION = re.compile(r'^revision:\s*str\s*=\s*"([^"]+)"', re.M)
# Tout ce qui suit `down_revision` jusqu'au `=`. L'annotation contient des
# crochets imbriqués (`Union[str, Sequence[str], None]`) : les décrire
# exactement était plus fragile que de les sauter.
DOWN = re.compile(r'^down_revision[^=\n]*=\s*("([^"]+)"|None)', re.M)

POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL", "")

needs_postgres = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="TEST_POSTGRES_URL absent : la chaîne n'est pas jouée sur Postgres ici",
)


# ─────────────────────────── lecture du dépôt ────────────────────────────


def _tracked_files() -> list[tuple[str, str]]:
    """`[(révision, nom de fichier)]` pour les seules migrations **commitées**.

    `git ls-files` et pas un parcours du répertoire : c'est toute la
    différence entre ce qui part en production et ce qui traîne sur la
    machine.

    Une **liste** et pas un dictionnaire : deux fichiers portant la même
    révision s'écraseraient dans un dictionnaire, et le test chargé de les
    détecter ne verrait plus rien.
    """
    result = subprocess.run(
        ["git", "ls-files", "alembic/versions/*.py"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip("git indisponible : le contrôle de chaîne ne peut pas tourner")

    found: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        path = REPO / line.strip()
        if not path.exists() or path.name == "__init__.py":
            continue
        match = REVISION.search(path.read_text(encoding="utf-8"))
        if match:
            found.append((match.group(1), path.name))
    return found


def _tracked_migrations() -> dict[str, str]:
    return dict(_tracked_files())


def _down_revision(filename: str) -> str | None:
    match = DOWN.search((VERSIONS / filename).read_text(encoding="utf-8"))
    return None if match is None else match.group(2)


def _chain_in_order() -> list[tuple[str, str]]:
    """La chaîne parcourue de la base vers la tête, `[(révision, fichier)]`."""
    tracked = _tracked_migrations()
    children = {
        _down_revision(filename): (revision, filename)
        for revision, filename in tracked.items()
    }
    ordered: list[tuple[str, str]] = []
    cursor: str | None = None
    while cursor in children:
        revision, filename = children[cursor]
        ordered.append((revision, filename))
        cursor = revision
    return ordered


# ───────────────────────── les contrôles statiques ───────────────────────


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

    forks = {parent: names for parent, names in by_parent.items() if len(names) > 1}
    assert not forks, f"Deux migrations partent du même parent : {forks}"


def test_no_two_files_declare_the_same_revision() -> None:
    """Deux fichiers, une révision : Alembic en joue un et oublie l'autre.

    Silencieusement. Le schéma de production se met alors à diverger de celui
    des tests sans qu'aucune commande ne le signale — `alembic current`
    répond la bonne révision, et il lui manque une table.
    """
    seen: dict[str, list[str]] = {}
    for revision, filename in _tracked_files():
        seen.setdefault(revision, []).append(filename)

    duplicates = {rev: names for rev, names in seen.items() if len(names) > 1}
    assert not duplicates, (
        f"Révision(s) déclarée(s) par plusieurs fichiers : {duplicates}. "
        "Alembic n'en jouera qu'un, sans le dire."
    )


def _numbering_problems(ordered: list[tuple[str, str]]) -> list[str]:
    """Ce qui cloche dans la numérotation d'une chaîne déjà ordonnée.

    Fonction pure, pour être mise à l'épreuve sur des chaînes fabriquées :
    un contrôle qu'on n'a jamais vu échouer n'est pas un contrôle.
    """
    problems = [
        f"{filename} déclare la révision « {revision} » — le nom du fichier ment"
        for revision, filename in ordered
        if not filename.startswith(f"{revision}_")
    ]

    numbers = [(int(revision), filename) for revision, filename in ordered]
    problems += [
        f"{filename} (n° {number}) vient après le n° {numbers[index - 1][0]}"
        for index, (number, filename) in enumerate(numbers)
        if index and number < numbers[index - 1][0]
    ]
    return problems


def test_revision_numbers_follow_the_chain() -> None:
    """Le numéro dit la place dans la chaîne, jamais la date de rédaction.

    C'est la règle de CLAUDE.md — « numéro de révision = ordre réel dans la
    chaîne, jamais réservé à l'avance ». Une migration écrite en même temps
    que deux autres, livrée après elles, et gardant son numéro de départ rend
    l'ordre illisible : on lit `0015` en queue de chaîne et on en déduit qu'il
    manque `0016` et `0017`.

    Le fichier porte le numéro **et** la révision : les deux doivent
    concorder, sinon le nom du fichier ment sur son contenu.
    """
    ordered = _chain_in_order()
    tracked = _tracked_migrations()
    assert len(ordered) == len(tracked), (
        "la chaîne ne relie pas toutes les migrations commitées — "
        f"{len(ordered)} atteintes sur {len(tracked)}"
    )

    problems = _numbering_problems(ordered)
    assert not problems, (
        "Numérotation en désaccord avec la chaîne :\n  "
        + "\n  ".join(problems)
        + "\n\nRenumérote le fichier à sa place réelle : le numéro est la "
        "seule chose qui dise l'ordre sans dérouler toute la chaîne."
    )


def test_the_numbering_check_catches_a_revision_out_of_order() -> None:
    """La situation exacte du 14/09, jouée sur une chaîne fabriquée.

    `0015` écrite pendant que `0016` et `0017` étaient livrées, donc chaînée
    derrière elles, et gardant son numéro : la chaîne est valide pour Alembic,
    et illisible pour un humain.
    """
    problems = _numbering_problems(
        [
            ("0016", "0016_taxonomie.py"),
            ("0017", "0017_habitudes.py"),
            ("0015", "0015_menu.py"),
        ]
    )
    assert any("0015_menu.py" in problem for problem in problems), problems


def test_the_numbering_check_accepts_a_chain_in_order() -> None:
    """Et ne crie pas sur une chaîne saine — sinon il serait vite désactivé."""
    assert (
        _numbering_problems(
            [
                ("0016", "0016_taxonomie.py"),
                ("0017", "0017_habitudes.py"),
                ("0018", "0018_menu.py"),
            ]
        )
        == []
    )


def test_the_numbering_check_catches_a_filename_that_lies() -> None:
    """Un fichier `0018_...` déclarant `0019` enverrait chercher à côté."""
    problems = _numbering_problems([("0019", "0018_menu.py")])
    assert any("ment" in problem for problem in problems), problems


# ──────────────── le défaut booléen, lu dans le code ──────────────────────

_BOOLEAN_NAMES = {"Boolean", "BOOLEAN"}
_COLUMN_CALLS = {"Column", "mapped_column", "alter_column", "add_column"}


def _is_boolean(node: ast.expr) -> bool:
    """`sa.Boolean()`, `Boolean()`, `sa.Boolean` ou `Boolean`."""
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Attribute):
        return node.attr in _BOOLEAN_NAMES
    if isinstance(node, ast.Name):
        return node.id in _BOOLEAN_NAMES
    return False


def _integer_default(node: ast.expr) -> str | None:
    """Le défaut s'il est un entier déguisé, sinon `None`.

    `0`, `"0"`, `sa.text("0")` et leurs variantes à 1 : les quatre façons
    d'écrire ce que Postgres refusera.
    """
    if isinstance(node, ast.Constant):
        value = str(node.value).strip().strip("'\"")
        return repr(node.value) if value in {"0", "1"} else None
    if isinstance(node, ast.Call):
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name == "text" and node.args and isinstance(node.args[0], ast.Constant):
            inner = str(node.args[0].value).strip()
            if inner.lower() in {"0", "1"}:
                return f"text({inner!r})"
    return None


def _boolean_offenders(paths: list[Path]) -> list[str]:
    """Toutes les colonnes booléennes dont le défaut est un entier."""
    offenders: list[str] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.attr
                if isinstance(func, ast.Attribute)
                else getattr(func, "id", "")
            )
            if name not in _COLUMN_CALLS:
                continue

            default = next(
                (kw.value for kw in node.keywords if kw.arg == "server_default"), None
            )
            if default is None:
                continue

            # Le type est un argument positionnel dans un `Column`, et un
            # `existing_type=` dans un `alter_column`.
            declared = [arg for arg in node.args if _is_boolean(arg)]
            declared += [
                kw.value
                for kw in node.keywords
                if kw.arg in {"existing_type", "type_"} and _is_boolean(kw.value)
            ]
            if not declared:
                continue

            written = _integer_default(default)
            if written:
                offenders.append(
                    f"{_display(path)}:{default.lineno} — "
                    f"server_default={written} sur une colonne booléenne"
                )
    return offenders


def _display(path: Path) -> str:
    """Le chemin relatif au dépôt quand c'est possible, sinon tel quel.

    Le message d'un contrôle ne doit jamais pouvoir lever : un fichier hors
    dépôt — un cas fabriqué par les tests du détecteur — ferait remonter un
    `ValueError` de `relative_to` à la place du défaut qu'on cherchait à
    signaler.
    """
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return path.as_posix()


BOOLEAN_RULE = (
    "\n\nPostgres a un vrai type booléen et refuse « DEFAULT 0 » "
    "(DatatypeMismatchError). SQLite range les booléens dans des entiers et "
    "l'accepte sans un mot — c'est ce décalage qui a mis la production à "
    "terre le 14/09. Écris sa.false() / sa.true() dans les migrations, "
    "func.false() / func.true() dans les modèles : le dialecte choisit le "
    "littéral, pas nous."
)


def test_no_integer_server_default_on_a_boolean_migration() -> None:
    """Le défaut booléen, lu dans les opérations de chaque migration."""
    offenders = _boolean_offenders(sorted(VERSIONS.glob("[0-9]*.py")))
    assert not offenders, (
        "Défaut entier sur une colonne booléenne :\n  "
        + "\n  ".join(offenders)
        + BOOLEAN_RULE
    )


def test_no_integer_server_default_on_a_boolean_model() -> None:
    """Et dans les modèles, qui servent `create_all` — donc les tests.

    Un modèle qui diverge de sa migration, c'est un schéma de test qui diverge
    du schéma de production : le pire endroit où poser une différence,
    puisque c'est celui qui est censé la révéler.
    """
    offenders = _boolean_offenders(sorted((REPO / "app" / "models").glob("*.py")))
    assert not offenders, (
        "Défaut entier sur une colonne booléenne :\n  "
        + "\n  ".join(offenders)
        + BOOLEAN_RULE
    )


# Les quatre façons d'écrire ce que Postgres refusera, plus les trois façons
# de l'écrire correctement. C'est la ligne exacte de la panne du 14/09 qui
# ouvre la liste.
FAULTY_COLUMNS = """
import sqlalchemy as sa
from sqlalchemy import Boolean
from sqlalchemy.orm import mapped_column

sa.Column("a", sa.Boolean(), nullable=False, server_default=sa.text("0"))
sa.Column("b", sa.Boolean(), nullable=False, server_default="0")
sa.Column("c", sa.Boolean(), nullable=False, server_default=sa.text("1"))
mapped_column(Boolean, nullable=False, server_default="1")
"""

SOUND_COLUMNS = """
import sqlalchemy as sa
from sqlalchemy import Boolean, func
from sqlalchemy.orm import mapped_column

sa.Column("a", sa.Boolean(), nullable=False, server_default=sa.false())
sa.Column("b", sa.Boolean(), nullable=False, server_default=sa.true())
mapped_column(Boolean, nullable=False, server_default=func.false())
# Un entier sur une colonne entière reste parfaitement légitime.
sa.Column("n", sa.Integer(), nullable=False, server_default="0")
sa.Column("t", sa.Text(), nullable=True, server_default="1")
"""


def test_the_boolean_check_catches_every_way_of_writing_it(tmp_path: Path) -> None:
    """Le détecteur, mis à l'épreuve sur la ligne qui a cassé la production.

    Un garde-fou qu'on n'a jamais vu refuser quelque chose ne garde rien. Les
    quatre écritures sont celles qu'on retrouve dans du code réel — l'entier
    nu, la chaîne, et `sa.text()` des deux côtés.
    """
    faulty = tmp_path / "0099_faute.py"
    faulty.write_text(FAULTY_COLUMNS, encoding="utf-8")

    offenders = _boolean_offenders([faulty])
    assert len(offenders) == 4, offenders


def test_the_boolean_check_leaves_sound_columns_alone(tmp_path: Path) -> None:
    """Et laisse passer `sa.false()` — comme un entier sur une colonne entière.

    C'est la moitié qui évite qu'on le désactive : un contrôle qui crie sur du
    code correct finit en commentaire.
    """
    sound = tmp_path / "0098_correct.py"
    sound.write_text(SOUND_COLUMNS, encoding="utf-8")

    assert _boolean_offenders([sound]) == []


# ───────────────────────── la chaîne, sur Postgres ───────────────────────


async def _reset_public_schema(url: str) -> None:
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            await connection.execute(text("CREATE SCHEMA public"))
    finally:
        await engine.dispose()


async def _query(url: str, sql: str) -> list[tuple]:
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return [tuple(row) for row in await connection.execute(text(sql))]
    finally:
        await engine.dispose()


@pytest.fixture
def empty_postgres() -> str:
    """Un Postgres **vide** : schéma déposé et recréé, pas seulement vidé.

    Recréer le schéma plutôt que supprimer les tables une à une : une séquence
    ou un type restés derrière feraient passer un `upgrade head` qui aurait
    échoué sur une base réellement neuve — exactement le faux vert qu'on
    cherche à éliminer.
    """
    asyncio.run(_reset_public_schema(POSTGRES_URL))
    return POSTGRES_URL


@needs_postgres
def test_the_whole_chain_applies_on_postgresql(empty_postgres: str) -> None:
    """Monter, redescendre, remonter — sur le moteur de la production.

    Le retour n'est pas de la coquetterie : c'est la seule façon de vérifier
    qu'un `downgrade` sait défaire ce que son `upgrade` a fait. On ne s'en
    sert qu'un soir de panne, c'est-à-dire au moment où l'on peut le moins se
    permettre de le découvrir faux.
    """
    run_alembic(empty_postgres, "upgrade", "head")
    run_alembic(empty_postgres, "downgrade", "base")
    run_alembic(empty_postgres, "upgrade", "head")


@needs_postgres
def test_the_chain_ends_on_the_repository_head(empty_postgres: str) -> None:
    """La base s'arrête exactement où le dépôt s'arrête."""
    run_alembic(empty_postgres, "upgrade", "head")

    expected = _chain_in_order()[-1][0]
    rows = asyncio.run(
        _query(empty_postgres, "SELECT version_num FROM alembic_version")
    )
    assert [row[0] for row in rows] == [expected]


@needs_postgres
def test_every_boolean_column_has_a_boolean_default(empty_postgres: str) -> None:
    """La panne du 14/09, relue dans la base elle-même.

    Le contrôle statique lit le code ; celui-ci lit ce que Postgres a
    réellement écrit. Les deux servent : le premier nomme le fichier à
    corriger, le second attrape ce qui arriverait par un chemin auquel on n'a
    pas pensé — un `ALTER COLUMN SET DEFAULT` glissé dans du SQL brut, par
    exemple, qu'aucune inspection d'opérations Alembic ne verrait.
    """
    run_alembic(empty_postgres, "upgrade", "head")

    rows = asyncio.run(
        _query(
            empty_postgres,
            "SELECT table_name, column_name, column_default "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'boolean' "
            "AND column_default IS NOT NULL "
            "ORDER BY table_name, column_name",
        )
    )
    assert rows, "aucune colonne booléenne à défaut — schéma inattendu"

    wrong = [
        f"{table}.{column} vaut « {default} »"
        for table, column, default in rows
        if default not in {"true", "false"}
    ]
    assert not wrong, "Défaut non booléen en base :\n  " + "\n  ".join(wrong)


def test_postgres_is_configured_in_ci() -> None:
    """Une variable mal écrite ne doit pas retirer tout Postgres en silence.

    Sans ce contrôle, `TEST_POSTGRES_URL` mal orthographiée dans le workflow
    ferait passer la CI au vert en **sautant** toute la moitié qui compte. Un
    test sauté et un test réussi se ressemblent beaucoup trop dans un journal
    de CI qu'on lit en diagonale.
    """
    if os.environ.get("CI", "").lower() not in {"true", "1"}:
        pytest.skip("hors CI : Postgres est facultatif sur un poste de développement")

    assert POSTGRES_URL, (
        "TEST_POSTGRES_URL est vide alors qu'on tourne en CI. La chaîne de "
        "migrations n'a donc pas été jouée sur Postgres, et c'est le seul "
        "moteur sur lequel la vérifier veut dire quelque chose."
    )
