"use client";

import { IconMinus, IconPlus } from "@/components/ui/Icons";
import { fullDayLabel, shortDate } from "@/lib/format";

/**
 * La **date** d'une session, au jour près, en deux boutons.
 *
 * Même raisonnement que `TimeWheel` pour l'heure : pas de `<input type="date">`.
 * Le sélecteur natif iOS ouvre un rouleau modal par-dessus l'écran, demande
 * une validation, et rend la main deux taps plus tard. Ici on recule d'un jour
 * en un appui, sans que rien ne s'ouvre.
 *
 * Le cas courant est « hier » ou « avant-hier » : une session qu'on n'a pas
 * notée en sortant de l'eau se saisit le soir même ou le lendemain. Les
 * sessions plus anciennes existent aussi — on peut remonter trois mois en
 * arrière, l'archive Open-Meteo suit — mais elles ne dictent pas l'ergonomie.
 *
 * Le futur est refusé : on note ce qu'on a fait, pas ce qu'on fera.
 */
interface DateWheelProps {
  label?: string;
  /** Le jour courant, en heure locale. Seule la partie date compte. */
  value: Date;
  onChange: (next: Date) => void;
  /** Jour le plus ancien accessible. Par défaut, aucune limite. */
  min?: Date;
  /** Jour le plus récent accessible. Par défaut, aujourd'hui. */
  max?: Date;
}

function shiftDays(date: Date, days: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function startOfDay(date: Date): Date {
  const copy = new Date(date);
  copy.setHours(0, 0, 0, 0);
  return copy;
}

export function DateWheel({
  label = "Jour",
  value,
  onChange,
  min,
  max,
}: DateWheelProps) {
  const ceiling = max ?? new Date();
  const previous = shiftDays(value, -1);
  const next = shiftDays(value, 1);

  const canGoBack = min === undefined || startOfDay(previous) >= startOfDay(min);
  const canGoForward = startOfDay(next) <= startOfDay(ceiling);

  return (
    <div className="min-w-0">
      <p className="pb-1.5 text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
        {label}
      </p>
      <div className="flex items-stretch overflow-hidden rounded-button border border-line bg-card">
        <button
          type="button"
          disabled={!canGoBack}
          onClick={() => onChange(previous)}
          aria-label={`${label} : la veille`}
          className="flex h-touch w-touch shrink-0 items-center justify-center text-ink-2 disabled:opacity-30"
        >
          <IconMinus className="h-5 w-5" />
        </button>
        <span
          aria-live="polite"
          className="flex min-w-0 flex-1 flex-col items-center justify-center px-2 py-1"
        >
          <span className="truncate font-display text-[20px] font-bold capitalize leading-none text-ink">
            {fullDayLabel(value.toISOString())}
          </span>
          <span className="tabular mt-0.5 text-[12px] leading-none text-mute">
            {shortDate(value.toISOString())}
          </span>
        </span>
        <button
          type="button"
          disabled={!canGoForward}
          onClick={() => onChange(next)}
          aria-label={`${label} : le lendemain`}
          className="flex h-touch w-touch shrink-0 items-center justify-center text-ink-2 disabled:opacity-30"
        >
          <IconPlus className="h-5 w-5" />
        </button>
      </div>
    </div>
  );
}
