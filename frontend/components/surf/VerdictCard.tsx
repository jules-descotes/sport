"use client";

import Link from "next/link";

import { distanceLabel, fullDayLabel, hourLabel, num, scoreClass } from "@/lib/format";
import type { Recommendation } from "@/lib/types";

/**
 * L'écran d'accueil répond à une seule question : « je vais à l'eau, oui ou
 * non, et où ? ». Le verdict est en très grand, le spot juste dessous, et le
 * reste est à un tap.
 *
 * Si cet écran demande plus de deux secondes de lecture, c'est raté.
 */
export function VerdictCard({ data }: { data: Recommendation }) {
  const { headline, headline_spot: spot } = data;
  // La liste est triée sur le meilleur créneau des cinq jours ; le verdict, lui,
  // porte sur la prochaine fenêtre de jour. Les deux ne désignent pas forcément
  // le même spot : on retrouve donc le bon par son identifiant.
  const entry = data.spots.find((item) => item.spot.id === spot?.id);

  if (!headline || !spot) {
    return (
      <section className="px-5">
        <div className="rounded-card border border-line bg-card px-5 py-8">
          <p className="font-display text-[56px] leading-none font-bold text-ink-2">
            ?
          </p>
          <p className="mt-3 text-[16px] text-ink-2">{data.sentence}</p>
        </div>
      </section>
    );
  }

  return (
    <section className="px-5">
      <div className="overflow-hidden rounded-card border border-line bg-card">
        <div className="flex items-start justify-between gap-4 px-5 pt-6">
          <div>
            <p
              className="font-display text-[64px] leading-[0.85] font-bold tracking-tight text-ink"
              aria-label={`Verdict : ${data.verdict}`}
            >
              {data.verdict}
            </p>
            <p className="mt-3 font-display text-[26px] leading-none font-semibold uppercase text-ink">
              {spot.name}
            </p>
            <p className="mt-1 text-[14px] text-mute">
              {fullDayLabel(headline.ts)} {hourLabel(headline.ts)}
              {entry?.distance_km != null
                ? ` · ${distanceLabel(entry.distance_km)}`
                : ""}
            </p>
          </div>

          <div
            className={`tabular flex h-[72px] w-[72px] shrink-0 flex-col items-center justify-center rounded-card ${scoreClass(
              headline.level,
            )}`}
          >
            <span className="font-display text-[30px] leading-none font-bold">
              {num(headline.score, 1)}
            </span>
            <span className="text-[11px] font-semibold opacity-80">/ 5</span>
          </div>
        </div>

        <p className="tabular px-5 pt-4 text-[15px] leading-snug text-ink-2">
          {headline.line}
        </p>

        {headline.reasons.length > 0 ? (
          <ul className="flex flex-wrap gap-2 px-5 pt-4">
            {headline.reasons.map((reason) => (
              <li
                key={reason}
                className="rounded-chip border border-line bg-soft px-2.5 py-1 text-[12px] text-ink-2"
              >
                {reason}
              </li>
            ))}
          </ul>
        ) : null}

        <div className="mt-5 flex gap-3 border-t border-line px-5 py-4">
          <Link
            href={`/surf/spots/${spot.slug}`}
            className="flex min-h-touch flex-1 items-center justify-center rounded-button border border-line bg-soft px-4 text-[15px] font-semibold text-ink"
          >
            Voir le spot
          </Link>
          <Link
            href="/surf/comparateur"
            className="flex min-h-touch flex-1 items-center justify-center rounded-button border border-line bg-soft px-4 text-[15px] font-semibold text-ink"
          >
            Comparer
          </Link>
        </div>
      </div>

      {/* Le formulaire de session arrive au lot 2 : le bouton est là pour que
          la place soit prise et la hiérarchie visuelle juste, mais il ne
          promet rien qu'il ne tienne. */}
      <button
        type="button"
        disabled
        className="mt-3 min-h-touch w-full rounded-button bg-accent px-4 text-[16px] font-semibold text-on-accent opacity-50"
      >
        Enregistrer une session
      </button>
      <p className="mt-2 text-center text-[12px] text-mute">
        La saisie de session arrive au lot 2.
      </p>
    </section>
  );
}
