"use client";

import { IconMinus, IconPlus } from "@/components/ui/Icons";
import { clockLabel } from "@/lib/format";

/**
 * Début et fin d'une session, par pas de quinze minutes.
 *
 * **Pas un `<input type="time">`.** Le sélecteur natif iOS ouvre un rouleau
 * modal, demande une validation, et rend la main deux taps plus tard ; ici on
 * corrige « j'ai commencé une demi-heure plus tôt » en deux appuis, sans
 * quitter l'écran et sans que rien ne s'ouvre par-dessus. La règle du projet
 * est *zéro saisie clavier pendant l'effort*, et un clavier numérique qui
 * monte en est une (`PROJET.md` §1, règle 5).
 *
 * Le quart d'heure est le bon pas : personne ne sait à cinq minutes près quand
 * il s'est mis à l'eau, et la fenêtre de conditions figée est calée à l'heure
 * pleine — un pas plus fin donnerait une précision que la donnée n'a pas.
 */
const STEP_MINUTES = 15;

interface TimeWheelProps {
  label: string;
  value: Date;
  onChange: (next: Date) => void;
  /** Bornes dures : la fin ne passe jamais avant le début. */
  min?: Date;
  max?: Date;
}

function shift(date: Date, minutes: number): Date {
  return new Date(date.getTime() + minutes * 60_000);
}

export function TimeWheel({ label, value, onChange, min, max }: TimeWheelProps) {
  const previous = shift(value, -STEP_MINUTES);
  const next = shift(value, STEP_MINUTES);

  const canGoBack = min === undefined || previous >= min;
  const canGoForward = max === undefined || next <= max;

  return (
    <div className="min-w-0 flex-1">
      <p className="pb-1.5 text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
        {label}
      </p>
      <div className="flex items-stretch overflow-hidden rounded-button border border-line bg-card">
        <button
          type="button"
          disabled={!canGoBack}
          onClick={() => onChange(previous)}
          aria-label={`${label} : quinze minutes plus tôt`}
          className="flex h-touch w-touch shrink-0 items-center justify-center text-ink-2 disabled:opacity-30"
        >
          <IconMinus className="h-5 w-5" />
        </button>
        <span
          aria-live="polite"
          className="tabular flex flex-1 items-center justify-center font-display text-[26px] font-bold leading-none text-ink"
        >
          {clockLabel(value.toISOString())}
        </span>
        <button
          type="button"
          disabled={!canGoForward}
          onClick={() => onChange(next)}
          aria-label={`${label} : quinze minutes plus tard`}
          className="flex h-touch w-touch shrink-0 items-center justify-center text-ink-2 disabled:opacity-30"
        >
          <IconPlus className="h-5 w-5" />
        </button>
      </div>
    </div>
  );
}
