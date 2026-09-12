"use client";

import { SLOT_HOURS, num, scoreClass } from "@/lib/format";

/**
 * Les huit créneaux d'une journée, en une bande.
 *
 * C'est une **matrice**, pas une liste : les huit colonnes sont fixes, toutes
 * les trois heures, et une heure sans prévision ou de nuit s'éteint au lieu de
 * disparaître. Une colonne manquante décalerait toute la lecture, et cette
 * bande est faite pour être lue en un coup d'œil, à bout de bras.
 *
 * Le meilleur créneau est cerclé d'accent — c'est le seul endroit de la bande
 * où l'accent apparaît, sinon il ne désigne plus rien.
 */

interface BandSlot {
  ts: string;
  score: number | null;
  level: number | null;
  daylight: boolean;
}

interface SlotBandProps {
  slots: BandSlot[];
  /** Journée rendue, en heure locale. */
  day: Date;
  /** Créneau mis en avant — le meilleur de la journée. */
  bestTs?: string | null;
  selectedTs?: string | null;
  onSelect?: (ts: string) => void;
  label?: string;
}

function sameLocalDay(iso: string, day: Date): boolean {
  const date = new Date(iso);
  return (
    date.getFullYear() === day.getFullYear() &&
    date.getMonth() === day.getMonth() &&
    date.getDate() === day.getDate()
  );
}

export function SlotBand({
  slots,
  day,
  bestTs,
  selectedTs,
  onSelect,
  label,
}: SlotBandProps) {
  // Le créneau de trois heures retenu est celui qui l'ouvre : à 9 h on lit la
  // prévision de 9 h, pas la moyenne de 9 h – 12 h. Une moyenne lisserait
  // justement la fenêtre qu'on cherche.
  const byHour = new Map<number, BandSlot>();
  for (const slot of slots) {
    if (!sameLocalDay(slot.ts, day)) continue;
    const hour = new Date(slot.ts).getHours();
    if (SLOT_HOURS.includes(hour as (typeof SLOT_HOURS)[number])) {
      byHour.set(hour, slot);
    }
  }

  return (
    <div className="flex gap-1" role="group" aria-label={label ?? "Créneaux du jour"}>
      {SLOT_HOURS.map((hour) => {
        const slot = byHour.get(hour);
        const best = slot != null && slot.ts === bestTs;
        const selected = slot != null && slot.ts === selectedTs;
        const usable = slot != null && slot.daylight && slot.score !== null;

        const cell = (
          <>
            <span className="block text-[11px] font-medium text-mute">
              {String(hour).padStart(2, "0")}
            </span>
            <span
              className={`tabular mt-1 flex h-9 items-center justify-center rounded-cell text-[14px] font-semibold ${
                usable
                  ? scoreClass(slot.level)
                  : "border border-line bg-soft text-mute"
              } ${best ? "ring-2 ring-accent" : ""} ${
                selected && !best ? "ring-2 ring-ink-2" : ""
              }`}
            >
              {usable ? num(slot.score, 1) : "—"}
            </span>
          </>
        );

        if (!onSelect || slot == null) {
          return (
            <div key={hour} className="flex-1 text-center">
              {cell}
            </div>
          );
        }

        return (
          <button
            key={hour}
            type="button"
            onClick={() => onSelect(slot.ts)}
            aria-pressed={selected}
            className="min-h-touch flex-1 text-center"
          >
            {cell}
          </button>
        );
      })}
    </div>
  );
}
