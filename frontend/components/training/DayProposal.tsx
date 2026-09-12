"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { SessionMode } from "@/components/training/SessionMode";
import { IconClock, IconDumbbell } from "@/components/ui/Icons";
import { api } from "@/lib/api";
import type { Formula } from "@/lib/types";

/**
 * La séance proposée sur l'écran Jour — **une seule**, remplaçable en un tap.
 *
 * Une seule, et c'est le point. L'écran Jour est la journée telle qu'elle se
 * vit, pas un catalogue : trois propositions obligeraient à choisir à 7 h du
 * matin, ce qui revient à n'en faire aucune. Le remplacement existe, derrière
 * un tap, et il propose autre chose — pas une variante de la même séance.
 *
 * Le bloc se lance **sur place** : partir sur Training, choisir, revenir, ce
 * sont trois écrans pour un geste qui en vaut zéro.
 */
export function DayProposal() {
  const queryClient = useQueryClient();
  const [swapped, setSwapped] = useState<Formula | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [session, setSession] = useState<{
    formula: Formula;
    workoutId: number;
  } | null>(null);

  const { data, isPending } = useQuery({
    queryKey: ["training-today"],
    queryFn: api.trainingToday,
  });

  const start = useMutation({
    mutationFn: (formula: Formula) => api.startWorkout(formula.id),
    onSuccess: (workout, formula) => setSession({ formula, workoutId: workout.id }),
  });

  if (session) {
    return (
      <SessionMode
        formula={session.formula}
        workoutId={session.workoutId}
        onFinished={() => {
          setSession(null);
          setSwapped(null);
          queryClient.invalidateQueries({ queryKey: ["training-today"] });
          queryClient.invalidateQueries({ queryKey: ["training-overview"] });
        }}
        onAbandon={() => {
          api.deleteWorkout(session.workoutId).catch(() => undefined);
          setSession(null);
        }}
      />
    );
  }

  if (isPending) {
    return (
      <div className="rounded-card border border-line bg-card px-4 py-3">
        <p className="text-[12px] font-semibold uppercase tracking-wide text-mute">
          Séance
        </p>
        <p className="mt-0.5 text-[14px] text-mute">Lecture…</p>
      </div>
    );
  }

  const chosen = swapped ?? data?.formula ?? null;
  if (!chosen) return null;

  return (
    <article className="overflow-hidden rounded-card border border-line bg-card">
      <div className="px-4 pt-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-mute">
          Séance
        </p>
        <h3 className="mt-1 font-display text-[26px] font-bold uppercase leading-none tracking-tight text-ink">
          {chosen.name}
        </h3>
        <p className="tabular mt-1.5 flex items-center gap-1.5 text-[13px] text-ink-2">
          <IconClock className="h-4 w-4 shrink-0" />
          {chosen.duration_min} min · {chosen.items.length} exercices
        </p>
        {/* La phrase qui dit pourquoi celle-ci : une proposition qu'on ne
            comprend pas se remplace au hasard, et on finit par ne plus la lire. */}
        <p className="mt-1.5 text-[13px] leading-snug text-mute">
          {swapped ? chosen.principle : (data?.reason ?? "")}
        </p>
      </div>

      <div className="flex gap-2 px-4 pb-4 pt-3">
        <button
          type="button"
          onClick={() => start.mutate(chosen)}
          disabled={start.isPending}
          className="flex min-h-touch flex-[2] items-center justify-center gap-2 rounded-button bg-accent px-4 text-[16px] font-semibold text-on-accent disabled:opacity-50"
        >
          <IconDumbbell className="h-5 w-5" />
          {start.isPending ? "Ouverture…" : "Commencer"}
        </button>
        {(data?.alternatives.length ?? 0) > 0 ? (
          <button
            type="button"
            onClick={() => setPickerOpen((open) => !open)}
            aria-expanded={pickerOpen}
            className="min-h-touch flex-1 rounded-button border border-line bg-card px-3 text-[14px] font-semibold text-ink-2"
          >
            Autre chose
          </button>
        ) : null}
      </div>

      {pickerOpen ? (
        <ul className="border-t border-line">
          {[...(swapped && data?.formula ? [data.formula] : []), ...(data?.alternatives ?? [])]
            .filter((formula) => formula.id !== chosen.id)
            .map((formula) => (
              <li key={formula.id} className="border-b border-line last:border-0">
                <button
                  type="button"
                  onClick={() => {
                    setSwapped(formula);
                    setPickerOpen(false);
                  }}
                  className="flex min-h-touch w-full items-center gap-3 px-4 py-2.5 text-left"
                >
                  <span className="min-w-0 flex-1 truncate text-[15px] font-semibold text-ink">
                    {formula.name}
                  </span>
                  <span className="tabular shrink-0 text-[12px] text-mute">
                    {formula.duration_min} min
                  </span>
                </button>
              </li>
            ))}
        </ul>
      ) : null}
    </article>
  );
}
