"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { dayKey, dayLabel, distanceLabel, num, scoreClass, shortHour } from "@/lib/format";
import type { Recommendation, Slot } from "@/lib/types";

/**
 * Grille heures × spots — **hors navigation depuis le lot 1 ter**.
 *
 * Le comparateur multi-spots sort du produit à l'écran : Jour porte un seul
 * spot, Surf en porte un à la fois (décidé le 12/09 au soir). Ce composant n'est
 * plus routé ; il est conservé parce que `/recommend` sait toujours rendre la
 * grille multi-spots, et qu'un jour de trip il redeviendra la bonne réponse.
 *
 * Ne pas le recâbler sans revenir sur la décision : il rouvrirait la question
 * de l'ingestion de tous les spots du rayon.
 */
export function Comparator({ data }: { data: Recommendation }) {
  const days = useMemo(() => {
    const seen = new Map<string, string>();
    for (const item of data.spots) {
      for (const slot of item.slots) {
        const key = dayKey(slot.ts);
        if (!seen.has(key)) seen.set(key, slot.ts);
      }
    }
    return [...seen.entries()].sort(
      (a, b) => new Date(a[1]).getTime() - new Date(b[1]).getTime(),
    );
  }, [data]);

  const [activeDay, setActiveDay] = useState<string | null>(null);
  const day = activeDay ?? days[0]?.[0] ?? null;

  const hours = useMemo(() => {
    const set = new Set<number>();
    for (const item of data.spots) {
      for (const slot of item.slots) {
        if (dayKey(slot.ts) === day) set.add(new Date(slot.ts).getHours());
      }
    }
    return [...set].sort((a, b) => a - b);
  }, [data, day]);

  if (days.length === 0) {
    return (
      <p className="mx-5 rounded-card border border-line bg-card px-5 py-6 text-[14px] text-ink-2">
        Aucune prévision pour les spots autour de toi. Ajoute un favori ou
        élargis ton rayon dans le profil.
      </p>
    );
  }

  return (
    <>
      <div className="flex gap-2 overflow-x-auto px-5 pb-3">
        {days.map(([key, iso]) => (
          <button
            key={key}
            type="button"
            onClick={() => setActiveDay(key)}
            aria-pressed={key === day}
            className={`min-h-touch shrink-0 rounded-pill border px-4 text-[14px] font-semibold ${
              key === day
                ? "border-accent bg-accent text-on-accent"
                : "border-line bg-card text-ink-2"
            }`}
          >
            {dayLabel(iso)}
          </button>
        ))}
      </div>

      <div className="overflow-x-auto px-5 pb-2">
        <table className="tabular w-max border-separate border-spacing-1">
          <thead>
            <tr>
              {/* Colonne des spots : collée à gauche pendant le scroll. */}
              <th className="sticky left-0 z-10 bg-bg pr-2 text-left text-[11px] font-semibold uppercase tracking-wide text-mute">
                Spot
              </th>
              {hours.map((hour) => (
                <th
                  key={hour}
                  className="w-[42px] pb-1 text-center text-[11px] font-semibold text-mute"
                >
                  {String(hour).padStart(2, "0")}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.spots.map((item) => {
              const byHour = new Map<number, Slot>();
              for (const slot of item.slots) {
                if (dayKey(slot.ts) === day) {
                  byHour.set(new Date(slot.ts).getHours(), slot);
                }
              }

              return (
                <tr key={item.spot.id}>
                  <th className="sticky left-0 z-10 bg-bg pr-3 text-left align-middle">
                    <Link
                      href={`/surf/spots/${item.spot.slug}`}
                      className="block max-w-[128px] truncate text-[13px] font-semibold text-ink"
                    >
                      {item.spot.name}
                    </Link>
                    <span className="text-[11px] text-mute">
                      {distanceLabel(item.distance_km)}
                    </span>
                  </th>

                  {hours.map((hour) => {
                    const slot = byHour.get(hour);
                    if (!slot) {
                      return (
                        <td
                          key={hour}
                          className="h-[38px] w-[42px] rounded-cell border border-line bg-soft"
                        />
                      );
                    }
                    return (
                      <td
                        key={hour}
                        title={`${shortHour(slot.ts)} h — ${slot.line}`}
                        className={`h-[38px] w-[42px] rounded-cell text-center text-[13px] font-semibold ${scoreClass(
                          slot.level,
                        )}`}
                      >
                        {num(slot.score, 1)}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <ul className="flex items-center gap-2 px-5 pt-2 text-[11px] text-mute">
        <li>1</li>
        {[1, 2, 3, 4, 5].map((level) => (
          <li
            key={level}
            className={`h-3 w-6 rounded-chip ${scoreClass(level)}`}
            aria-hidden
          />
        ))}
        <li>5</li>
      </ul>
    </>
  );
}
