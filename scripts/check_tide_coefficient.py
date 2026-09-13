"""Confronte notre coefficient de marée à l'annuaire SHOM.

Le coefficient est calculé chez nous à partir du niveau marin Open-Meteo à
Brest (cf. `app/services/tide_coefficient`). La vérité, elle, est publiée par
le SHOM. Ce script met les deux côte à côte : c'est la seule validation qui
compte, et elle doit être rejouable — le jour où Open-Meteo recalibre son
modèle de marée, l'écart bougera, et il faudra le savoir.

    python -m scripts.check_tide_coefficient
    python -m scripts.check_tide_coefficient --days 5 --shom 2026-09-14=93/89

Sans `--shom`, le script affiche nos valeurs et s'arrête — de quoi aller les
comparer à la main sur maree.shom.fr. Avec, il calcule l'écart et sort en
erreur au-delà de cinq points, seuil au-delà duquel l'app affiche « ≈ »
(décidé le 13/09). Les coefficients publiés se donnent **dans l'ordre de la
journée** : `2026-09-14=93/89`, matin puis soir.

Il n'écrit **rien en base** : il interroge Open-Meteo directement. C'est ce qui
permet de le lancer depuis n'importe où, y compris avant la première passe
d'ingestion.

La sortie est en ASCII pur, sans accents ni « ≈ » : la console Windows tourne
en cp1252 et planterait au milieu du tableau.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, date, datetime, timedelta

from app.services.openmeteo import OpenMeteoClient
from app.services.tide_coefficient import (
    BREST_LAT,
    BREST_LON,
    MEAN_WINDOW_DAYS,
    TideMark,
    marks_from_levels,
)

# Au-delà, l'app affiche « ≈ » : l'écart n'est plus du bruit d'arrondi.
TOLERANCE = 5


async def fetch_marks(days: int) -> tuple[list[TideMark], float, int]:
    """Les coefficients des `days` prochains jours, et le datum qui les porte."""
    async with OpenMeteoClient() as client:
        bundle = await client.fetch_sea_level(
            BREST_LAT,
            BREST_LON,
            past_days=MEAN_WINDOW_DAYS,
            forecast_days=max(days, 1) + 1,
        )

    levels = [
        (ts, values["sea_level_m"])
        for ts, values in bundle.sorted_rows()
        if values.get("sea_level_m") is not None
    ]
    if not levels:
        raise SystemExit("Open-Meteo n'a rendu aucun niveau marin pour Brest.")

    now = datetime.now(UTC)
    window = [
        level for ts, level in levels if ts >= now - timedelta(days=MEAN_WINDOW_DAYS)
    ]
    datum = sum(window) / len(window)

    marks = marks_from_levels(levels, datum, window_hours=len(window))
    horizon = now + timedelta(days=days)
    return (
        [mark for mark in marks if now <= mark.ts <= horizon],
        datum,
        len(window),
    )


def parse_shom(raw: str) -> dict[date, list[int]]:
    """« 2026-09-13=95/98,2026-09-14=99 » -> les coefficients publiés, par jour."""
    published: dict[date, list[int]] = {}
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        day, _, values = chunk.partition("=")
        published[date.fromisoformat(day.strip())] = [
            int(value) for value in values.replace("/", " ").split()
        ]
    return published


def fit(paired: list[tuple[int, int]]) -> tuple[float, float]:
    """La droite `SHOM = a x nous + b`, par moindres carrés.

    Une pente qui s'écarte de 1 dit que le modèle **comprime** le balancement
    vive-eau / morte-eau : c'est un défaut de résolution, pas un décalage de
    datum, et les deux ne se corrigent pas de la même façon. Les distinguer est
    tout l'intérêt de cette ligne.
    """
    mean_ours = sum(ours for ours, _ in paired) / len(paired)
    mean_theirs = sum(theirs for _, theirs in paired) / len(paired)
    spread = sum((ours - mean_ours) ** 2 for ours, _ in paired)
    if spread == 0:
        return 1.0, mean_theirs - mean_ours
    slope = (
        sum((ours - mean_ours) * (theirs - mean_theirs) for ours, theirs in paired)
        / spread
    )
    return slope, mean_theirs - slope * mean_ours


def main() -> int:
    parser = argparse.ArgumentParser(description="Coefficient de maree vs SHOM")
    parser.add_argument("--days", type=int, default=5)
    parser.add_argument(
        "--shom",
        default="",
        help="Coefficients publies : 2026-09-13=95/98,2026-09-14=99/97",
    )
    args = parser.parse_args()

    marks, datum, window_hours = asyncio.run(fetch_marks(args.days))

    print(f"Niveau moyen du modele sur {window_hours} h : {datum:+.3f} m")
    print(f"{len(marks)} pleine(s) mer(s) sur {args.days} jours\n")
    print(
        f"{'pleine mer (UTC)':<20} {'hauteur':>9} {'nous':>6} {'SHOM':>6} {'ecart':>6}"
    )

    published = parse_shom(args.shom) if args.shom else {}
    # Un jour porte deux pleines mers : on les apparie dans l'ordre.
    consumed: dict[date, int] = {}
    paired: list[tuple[int, int]] = []

    for mark in marks:
        day = mark.ts.date()
        index = consumed.get(day, 0)
        consumed[day] = index + 1
        reference = published.get(day, [])
        expected = reference[index] if index < len(reference) else None

        gap = None if expected is None else mark.value - expected
        if expected is not None:
            paired.append((mark.value, expected))

        print(
            f"{mark.ts:%Y-%m-%d %H:%M}    "
            f"{mark.height_m:>8.3f} "
            f"{mark.value:>6} "
            f"{'-' if expected is None else expected:>6} "
            f"{'-' if gap is None else f'{gap:+d}':>6}"
            + ("  ~" if mark.approximate else "")
        )

    if not paired:
        print("\nAucune reference SHOM fournie : rien a comparer.")
        return 0

    gaps = [ours - theirs for ours, theirs in paired]
    worst = max(abs(gap) for gap in gaps)
    bias = sum(gaps) / len(gaps)
    slope, intercept = fit(paired)

    print(f"\nEcart moyen (biais) : {bias:+.1f} point(s)")
    print(f"Ecart maximal       : {worst} point(s) sur {len(gaps)} marees")
    print(f"Droite d'ajustement : SHOM = {slope:.3f} x nous {intercept:+.1f}")

    if worst > TOLERANCE:
        print(
            f"\nAu-dela de {TOLERANCE} points : l'app affiche le signe approche.\n"
            "Consigner l'ecart dans docs/COEFFICIENT-MAREE.md."
        )
        return 1

    print(f"\nDans la tolerance de {TOLERANCE} points. Coefficient affiche tel quel.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
