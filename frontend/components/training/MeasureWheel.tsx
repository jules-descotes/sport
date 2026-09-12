"use client";

import { useState } from "react";

import { objectiveValueLabel } from "@/components/training/ObjectiveGauge";
import { IconMinus, IconPlus } from "@/components/ui/Icons";
import type { Objective } from "@/lib/types";

/**
 * Saisir une mesure **à la molette**, jamais au clavier.
 *
 * Une mesure se prend les pieds nus, souvent juste après s'être relevé du sol.
 * Un champ numérique ouvre le pavé iOS, mange la moitié de l'écran et demande
 * une validation ; deux boutons font le travail en trois taps.
 *
 * Le pas est propre à l'unité : un centimètre pour une distance, un degré pour
 * un angle, cinq secondes pour un gainage. Un pas d'une seconde sur une
 * planche de deux minutes demanderait cent-vingt taps.
 *
 * L'appui long n'existe pas ici, contrairement au compteur de vagues : on ne
 * corrige pas une mesure de trente unités d'un coup, on la relit.
 */

function stepFor(unit: string): number {
  if (unit === "s") return 5;
  if (unit === "deg") return 1;
  return 1;
}

/** Bornes larges, juste assez pour empêcher l'absurde. */
function boundsFor(unit: string): [number, number] {
  if (unit === "s") return [0, 1800];
  if (unit === "deg") return [0, 180];
  return [-60, 60];
}

export function MeasureWheel({
  objective,
  onSubmit,
  onCancel,
  pending,
}: {
  objective: Objective;
  onSubmit: (value: number) => void;
  onCancel: () => void;
  pending: boolean;
}) {
  const step = stepFor(objective.unit);
  const [min, max] = boundsFor(objective.unit);

  // On repart de la dernière mesure : une souplesse ne change pas de dix
  // centimètres en trois semaines, et partir de zéro ferait vingt taps.
  const [value, setValue] = useState<number>(
    objective.current_value ?? (objective.unit === "s" ? 60 : 0),
  );

  return (
    <section
      className="rounded-card border border-accent bg-card px-5 py-5"
      aria-label={`Mesurer : ${objective.name}`}
    >
      <h3 className="font-display text-[22px] font-semibold uppercase leading-none text-ink">
        {objective.name}
      </h3>
      <p className="mt-1.5 text-[13px] leading-snug text-ink-2">
        {objective.measure}
      </p>

      <div className="mt-4 flex items-stretch overflow-hidden rounded-button border border-line bg-soft">
        <button
          type="button"
          onClick={() => setValue((current) => Math.max(min, current - step))}
          aria-label={`Retirer ${step}`}
          className="flex h-[64px] w-[64px] shrink-0 items-center justify-center text-ink-2"
        >
          <IconMinus className="h-6 w-6" />
        </button>
        <span
          aria-live="polite"
          className="tabular flex flex-1 items-center justify-center font-display text-[44px] font-bold leading-none text-ink"
        >
          {objectiveValueLabel(value, objective.unit)}
        </span>
        <button
          type="button"
          onClick={() => setValue((current) => Math.min(max, current + step))}
          aria-label={`Ajouter ${step}`}
          className="flex h-[64px] w-[64px] shrink-0 items-center justify-center text-ink-2"
        >
          <IconPlus className="h-6 w-6" />
        </button>
      </div>

      <div className="mt-4 flex gap-3">
        <button
          type="button"
          onClick={onCancel}
          className="min-h-touch flex-1 rounded-button border border-line bg-card px-4 text-[15px] font-semibold text-ink-2"
        >
          Annuler
        </button>
        <button
          type="button"
          disabled={pending}
          onClick={() => onSubmit(value)}
          className="min-h-touch flex-1 rounded-button bg-accent px-4 text-[15px] font-semibold text-on-accent disabled:opacity-50"
        >
          {pending ? "Enregistrement…" : "Enregistrer"}
        </button>
      </div>
    </section>
  );
}
