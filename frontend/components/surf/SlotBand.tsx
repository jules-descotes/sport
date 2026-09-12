"use client";

import { DirectionArrow } from "@/components/surf/DirectionArrow";
import { SLOT_HOURS, num, scoreClass } from "@/lib/format";

/**
 * Les huit créneaux d'une journée, toutes les trois heures — **le résumé de
 * l'écran Jour**.
 *
 * Depuis le 13/09, chaque créneau porte ce qui décide vraiment d'y aller :
 * hauteur, période, flèche de houle, vent et sa flèche, et la note. Une note
 * seule disait « c'est bon » sans dire pourquoi, et il fallait ouvrir Surf
 * pour le savoir — neuf fois sur dix pour rien.
 *
 * C'est une **matrice**, pas une liste : les huit colonnes sont fixes, et une
 * heure sans prévision ou de nuit s'éteint au lieu de disparaître. Une colonne
 * manquante décalerait toute la lecture.
 *
 * Un tap ouvre Surf **positionné sur cette heure-là** : le résumé et le
 * tableau sont deux échelles de la même chose, pas deux écrans.
 */

interface BandSlot {
  ts: string;
  score: number | null;
  level: number | null;
  daylight: boolean;
  wave_height_m?: number | null;
  wave_period_s?: number | null;
  wave_direction_deg?: number | null;
  wind_speed_kt?: number | null;
  wind_direction_deg?: number | null;
  wind_offshore_kt?: number | null;
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
    <div
      className="grid grid-cols-8 gap-1"
      role="group"
      aria-label={label ?? "Créneaux du jour"}
    >
      {SLOT_HOURS.map((hour) => {
        const slot = byHour.get(hour);
        const best = slot != null && slot.ts === bestTs;
        const selected = slot != null && slot.ts === selectedTs;
        const usable = slot != null && slot.daylight && slot.score !== null;

        // Le vent de terre lisse la vague, celui de mer la hache : la flèche
        // le dit par sa couleur, sans une ligne de légende.
        const windTone =
          slot?.wind_offshore_kt == null
            ? "text-mute"
            : slot.wind_offshore_kt > 2
              ? "text-[#2F6B4F]"
              : slot.wind_offshore_kt < -2
                ? "text-[#B4482E]"
                : "text-ink-2";

        const cell = (
          <>
            <span className="block text-[11px] font-medium text-mute">
              {String(hour).padStart(2, "0")}
            </span>

            {/* Houle : hauteur, période, provenance. */}
            <span className="mt-1 flex flex-col items-center gap-0.5">
              <span
                className={`tabular text-[14px] font-semibold leading-none ${
                  usable ? "text-ink" : "text-mute"
                }`}
              >
                {slot?.wave_height_m != null ? num(slot.wave_height_m) : "—"}
              </span>
              <span className="tabular text-[10px] leading-none text-mute">
                {slot?.wave_period_s != null
                  ? `${num(slot.wave_period_s, 0)}s`
                  : ""}
              </span>
              <DirectionArrow
                direction={slot?.wave_direction_deg ?? null}
                size={16}
                className={usable ? "text-ink-2" : "text-mute"}
              />
            </span>

            {/* Vent : force et provenance, teintées terre / mer. */}
            <span className={`mt-1 flex flex-col items-center gap-0.5 ${windTone}`}>
              <span className="tabular text-[12px] font-semibold leading-none">
                {slot?.wind_speed_kt != null
                  ? num(slot.wind_speed_kt, 0)
                  : "—"}
              </span>
              <DirectionArrow
                direction={slot?.wind_direction_deg ?? null}
                size={16}
              />
            </span>

            <span
              className={`tabular mt-1 flex h-8 items-center justify-center rounded-cell text-[14px] font-semibold ${
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
            <div key={hour} className="text-center">
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
            aria-label={`${String(hour).padStart(2, "0")} h — ouvrir le tableau horaire`}
            className="min-h-touch text-center"
          >
            {cell}
          </button>
        );
      })}
    </div>
  );
}
