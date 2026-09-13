"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { IconScale } from "@/components/ui/Icons";
import { api } from "@/lib/api";
import { num, shortDate } from "@/lib/format";
import type { Calibration } from "@/lib/types";

/**
 * **La pesée hebdomadaire** — et la calibration qu'elle déclenche.
 *
 * Ce n'est pas un suivi de poids de plus : c'est **le seul terme mesuré** de la
 * cible calorique. Mifflin-St Jeor donne un ordre de grandeur, la dépense d'une
 * session de surf est une estimation grossière, et la balance est ce qui
 * corrige les deux. Sans elle, la cible reste une formule.
 *
 * La saisie est à la molette, comme les mesures d'objectif du lot 4 : on ne
 * tape pas « 75,4 » au clavier numérique un dimanche matin, on tourne.
 *
 * La calibration ne se déclenche presque jamais, et le dit quand elle le fait.
 * Corriger toutes les semaines transformerait le bruit de la balance en
 * oscillation de la cible.
 */

/** Plage de pesée, au dixième de kilo. Cinquante à cent vingt. */
const MIN_KG = 50;
const MAX_KG = 120;

function calibrationMessage(calibration: Calibration): string {
  if (!calibration.applied) return calibration.reason;
  const sign = calibration.adjustment_kcal > 0 ? "+" : "−";
  return (
    `Cible ajustée de ${sign}${num(Math.abs(calibration.adjustment_kcal), 0)} kcal ` +
    `sur ${calibration.days} jours.`
  );
}

export function WeighIn() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const history = useQuery({ queryKey: ["weigh-ins"], queryFn: api.weighIns });
  const last = history.data?.[0];
  const [draft, setDraft] = useState<number | null>(null);

  const weight = draft ?? last?.weight_kg ?? 75;

  const save = useMutation({
    mutationFn: () => api.addWeighIn({ weight_kg: weight }),
    onSuccess: (response) => {
      setMessage(calibrationMessage(response.calibration));
      setOpen(false);
      setDraft(null);
      queryClient.invalidateQueries({ queryKey: ["weigh-ins"] });
      queryClient.invalidateQueries({ queryKey: ["nutrition-day"] });
    },
  });

  // La tendance : l'écart avec la pesée d'il y a une à quatre semaines. Pas
  // avec la précédente — deux pesées à deux jours d'écart ne disent rien.
  const reference = (history.data ?? []).find((entry, index) => index >= 3);
  const trend =
    last?.weight_kg && reference?.weight_kg
      ? last.weight_kg - reference.weight_kg
      : null;

  return (
    <section className="px-5" aria-label="Pesée">
      <div className="overflow-hidden rounded-card border border-line bg-card">
        <div className="flex items-center gap-3 px-4 py-3">
          <IconScale className="h-5 w-5 shrink-0 text-mute" />
          <div className="min-w-0 flex-1">
            <p className="tabular text-[18px] font-semibold text-ink">
              {last?.weight_kg ? `${num(last.weight_kg)} kg` : "Pas encore pesé"}
            </p>
            <p className="text-[12px] text-mute">
              {last ? shortDate(`${last.day}T12:00:00`) : "La cible attend ta balance"}
              {trend !== null
                ? ` · ${trend > 0 ? "+" : "−"}${num(Math.abs(trend))} kg`
                : ""}
            </p>
          </div>
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            className="min-h-touch shrink-0 rounded-button border border-line bg-soft px-3 text-[14px] font-semibold text-ink-2"
          >
            {open ? "Fermer" : "Me peser"}
          </button>
        </div>

        {open ? (
          <div className="border-t border-line px-4 py-4">
            <p className="tabular pb-2 text-center font-display text-[44px] font-bold leading-none text-ink">
              {num(weight)} <span className="text-[20px] text-mute">kg</span>
            </p>
            {/* Molette, pas clavier : on ne tape pas « 75,4 » un dimanche
                matin, on tourne. Même geste que les mesures d'objectif. */}
            <input
              type="range"
              min={MIN_KG}
              max={MAX_KG}
              step={0.1}
              value={weight}
              onChange={(event) => setDraft(Number(event.target.value))}
              aria-label="Poids en kilogrammes"
              className="h-touch w-full accent-[var(--sport-accent)]"
            />
            <button
              type="button"
              onClick={() => save.mutate()}
              disabled={save.isPending}
              className="mt-2 flex min-h-touch w-full items-center justify-center rounded-button bg-accent px-4 text-[16px] font-semibold text-on-accent disabled:opacity-50"
            >
              {save.isPending ? "Enregistrement…" : "Enregistrer"}
            </button>
          </div>
        ) : null}
      </div>

      {message ? (
        <p className="pt-2 text-[12px] leading-snug text-mute">{message}</p>
      ) : null}
    </section>
  );
}
