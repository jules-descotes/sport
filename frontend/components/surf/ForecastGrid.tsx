"use client";

import { useMemo } from "react";

import { SLOT_HOURS, dayKey, dayLabel, num, scoreClass } from "@/lib/format";
import type { ForecastPoint } from "@/lib/types";

/**
 * La grille 5 jours × 8 créneaux d'un spot — **la seule vue dense de l'app**
 * (V2 de `docs/DESIGN-EXPLORATION.md`).
 *
 * Elle tient **entière sur un écran**, sans défilement ni pagination par jour :
 * c'est tout son intérêt. Cinq lignes, huit colonnes, quarante cellules
 * colorées sur l'échelle 1 → 5 du CLAUDE.md — la même que sur Jour, sinon le
 * fil rouge se casse.
 *
 * Les créneaux de nuit sont **éteints, pas supprimés** : une colonne manquante
 * décalerait la lecture d'une ligne à l'autre, et une matrice qui ne s'aligne
 * pas ne se lit plus en deux secondes.
 */

interface ForecastGridProps {
  points: ForecastPoint[];
  selectedTs: string | null;
  onSelect: (ts: string) => void;
}

export function ForecastGrid({
  points,
  selectedTs,
  onSelect,
}: ForecastGridProps) {
  const days = useMemo(() => {
    const grouped = new Map<string, { iso: string; byHour: Map<number, ForecastPoint> }>();
    for (const point of points) {
      const key = dayKey(point.ts);
      const day =
        grouped.get(key) ?? { iso: point.ts, byHour: new Map<number, ForecastPoint>() };
      day.byHour.set(new Date(point.ts).getHours(), point);
      grouped.set(key, day);
    }
    return [...grouped.values()]
      .sort((a, b) => new Date(a.iso).getTime() - new Date(b.iso).getTime())
      .slice(0, 5);
  }, [points]);

  // Le meilleur créneau de la semaine, cerclé d'accent. Un seul, sinon
  // l'accent ne désigne plus rien.
  const bestTs = useMemo(() => {
    let top: ForecastPoint | null = null;
    for (const point of points) {
      if (!point.daylight || point.score === null) continue;
      if (top === null || point.score > (top.score as number)) top = point;
    }
    return top?.ts ?? null;
  }, [points]);

  if (days.length === 0) {
    return (
      <p className="rounded-card border border-line bg-card px-5 py-6 text-[14px] text-ink-2">
        Pas encore de prévision pour ce spot.
      </p>
    );
  }

  return (
    <div className="overflow-hidden rounded-card border border-line bg-card">
      <table className="tabular w-full table-fixed border-collapse">
        <caption className="sr-only">
          Notes prévues par jour et par créneau de trois heures
        </caption>
        <thead>
          <tr>
            <th className="w-[38px] py-1.5 text-left text-[11px] font-semibold uppercase tracking-wide text-mute" />
            {SLOT_HOURS.map((hour) => (
              <th
                key={hour}
                scope="col"
                className="py-1.5 text-center text-[11px] font-semibold text-mute"
              >
                {String(hour).padStart(2, "0")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {days.map((day) => (
            <tr key={dayKey(day.iso)}>
              <th
                scope="row"
                className="py-0.5 pl-3 pr-1 text-left text-[12px] font-semibold text-ink-2"
              >
                {dayLabel(day.iso)}
              </th>
              {SLOT_HOURS.map((hour) => {
                const point = day.byHour.get(hour);
                const usable =
                  point != null && point.daylight && point.score !== null;

                if (!usable) {
                  return (
                    <td key={hour} className="p-0.5">
                      <span className="flex h-touch items-center justify-center rounded-cell border border-line bg-soft text-[12px] text-mute">
                        {point ? "" : "—"}
                      </span>
                    </td>
                  );
                }

                const selected = point.ts === selectedTs;
                return (
                  <td key={hour} className="p-0.5">
                    <button
                      type="button"
                      onClick={() => onSelect(point.ts)}
                      aria-pressed={selected}
                      aria-label={`${dayLabel(day.iso)} ${hour} h, note ${num(
                        point.score,
                        1,
                      )} sur 5`}
                      className={`flex h-touch w-full items-center justify-center rounded-cell text-[14px] font-semibold ${scoreClass(
                        point.score_level,
                      )} ${point.ts === bestTs ? "ring-2 ring-accent" : ""} ${
                        selected && point.ts !== bestTs ? "ring-2 ring-ink-2" : ""
                      }`}
                    >
                      {num(point.score, 1)}
                    </button>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
