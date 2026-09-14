"""Le démarrage du conteneur, joué en entier sur un Postgres vide.

Le 14/09, tout était vert et la production ne démarrait pas. Les tests
couvraient les migrations (sur SQLite) et l'application (sur SQLite en
mémoire, tables créées depuis les métadonnées) — mais **personne ne jouait
`run.py`**, qui est pourtant la seule chose que Railway exécute.

Ce fichier joue la commande du conteneur, sur le moteur du conteneur, depuis
une base réellement vide, et attend de voir uvicorn écouter. C'est le test le
plus lent du dépôt et le seul qui réponde à la question « est-ce que ça
démarre ? ».

Il vérifie aussi la **forme du journal**. Un démarrage qui échoue sans dire de
quelle révision il partait oblige à aller lire la base à la main, un soir de
panne, pour savoir si la migration a été appliquée à moitié — et la réponse
est justement celle qu'on n'a pas le temps de chercher à ce moment-là.
"""
from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

REPO = Path(__file__).resolve().parent.parent
POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL", "")

# Le build de l'image, l'installation des dépendances et la chaîne complète
# des migrations tiennent largement dedans ; au-delà, c'est bloqué et non lent.
BOOT_TIMEOUT_S = 180

needs_postgres = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="TEST_POSTGRES_URL absent : le démarrage n'est pas joué sur Postgres ici",
)


async def _reset_public_schema(url: str) -> None:
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            await connection.execute(text("CREATE SCHEMA public"))
    finally:
        await engine.dispose()


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _Boot:
    """`run.py` lancé pour de vrai, sa sortie lue au fil de l'eau.

    La lecture se fait dans un fil séparé : `readline` bloque, et un
    sous-processus qui se tait sans mourir figerait la suite de tests au lieu
    de la faire échouer. Le fil lit, la boucle principale surveille l'heure.
    """

    def __init__(self, database_url: str, port: int) -> None:
        self.lines: list[str] = []
        self.process = subprocess.Popen(
            [sys.executable, "run.py"],
            cwd=REPO,
            env={
                **os.environ,
                "DATABASE_URL": database_url,
                "PORT": str(port),
                "SECRET_KEY": "startup-test-only",
                "DEBUG": "True",
                "STORAGE_BACKEND": "local",
            },
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()

    def _pump(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            self.lines.append(line.rstrip("\n"))

    @property
    def output(self) -> str:
        return "\n".join(self.lines)

    def wait_for(self, needle: str, timeout: float = BOOT_TIMEOUT_S) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if any(needle in line for line in list(self.lines)):
                return True
            if self.process.poll() is not None:
                # Mort : on laisse le fil de lecture finir de vider le tuyau,
                # sinon le journal d'échec s'arrête avant la cause.
                self._reader.join(timeout=5)
                return any(needle in line for line in list(self.lines))
            time.sleep(0.25)
        return False

    def stop(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=15)


@pytest.fixture
def booted() -> "_Boot":
    """`run.py` démarré sur un Postgres vide, arrêté proprement à la fin."""
    asyncio.run(_reset_public_schema(POSTGRES_URL))
    boot = _Boot(POSTGRES_URL, _free_port())
    try:
        yield boot
    finally:
        boot.stop()


@needs_postgres
def test_run_py_reaches_uvicorn_on_an_empty_postgres(booted: "_Boot") -> None:
    """De rien du tout à un serveur qui écoute, sans intervention.

    C'est le scénario exact d'un premier déploiement — et celui d'un
    redémarrage à froid après une restauration de sauvegarde.
    """
    assert booted.wait_for("Uvicorn running on"), (
        "run.py n'a pas atteint uvicorn sur une base vide.\n"
        f"--- sortie ---\n{booted.output}"
    )


@needs_postgres
def test_the_startup_log_says_where_the_migration_went(booted: "_Boot") -> None:
    """« migration base → 0018 : OK », et non « upgrade head » tout court.

    La révision de départ est la moitié utile du message : c'est elle qui dit,
    après un échec, si la base est restée où elle était ou si elle s'est
    arrêtée en chemin.
    """
    assert booted.wait_for("Uvicorn running on"), booted.output

    migration_lines = [line for line in booted.lines if "migration " in line]
    assert migration_lines, (
        f"aucune ligne de migration dans le journal :\n{booted.output}"
    )

    assert any(
        "base →" in line and line.rstrip().endswith(": OK") for line in migration_lines
    ), (
        "Le journal ne dit pas « migration <départ> → <arrivée> : OK ».\n"
        f"Lignes trouvées : {migration_lines}"
    )


@needs_postgres
def test_a_failed_migration_stops_the_container_and_says_why() -> None:
    """Une migration qui échoue n'ouvre jamais le serveur, et se raconte.

    Le scénario est fabriqué — une `alembic_version` pointant sur une révision
    que le dépôt ne connaît pas — mais c'est la forme exacte de la panne du
    13/09. Ce qui est vérifié tient en deux points, et ce sont les deux qui
    ont manqué le 14/09 : **uvicorn ne démarre pas** (une API sur un schéma
    inconnu est pire qu'une API absente), et la **raison est sur une ligne**,
    avant l'arrêt.
    """
    asyncio.run(_reset_public_schema(POSTGRES_URL))

    async def seed_unknown_revision() -> None:
        engine = create_async_engine(POSTGRES_URL, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "CREATE TABLE alembic_version ("
                        "version_num VARCHAR(32) NOT NULL, "
                        "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
                    )
                )
                await connection.execute(
                    text("INSERT INTO alembic_version VALUES ('9999_jamais_ecrite')")
                )
        finally:
            await engine.dispose()

    asyncio.run(seed_unknown_revision())

    boot = _Boot(POSTGRES_URL, _free_port())
    try:
        assert boot.wait_for("ÉCHEC", timeout=120), (
            "Rien n'a signalé l'échec de la migration.\n"
            f"--- sortie ---\n{boot.output}"
        )
        assert not boot.wait_for("Uvicorn running on", timeout=10), (
            "uvicorn a démarré malgré une migration en échec — l'API "
            "servirait un schéma inconnu.\n"
            f"--- sortie ---\n{boot.output}"
        )

        failure = next(line for line in boot.lines if "ÉCHEC" in line)
        assert failure.rstrip() != "", failure
        assert "ÉCHEC :" in failure, (
            f"La ligne d'échec ne porte pas de raison : {failure!r}"
        )
    finally:
        boot.stop()
