"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { DailyLogStatus } from "@/lib/types";

const CHOICES: { status: DailyLogStatus; label: string }[] = [
  { status: "surfed", label: "Surfé" },
  { status: "watched_and_passed", label: "Regardé, renoncé" },
  { status: "not_watched", label: "Pas regardé" },
];

/**
 * Une ligne par jour, trois boutons, et elle disparaît une fois répondu.
 *
 * Ce n'est pas un gadget : les jours de renoncement sont les **seuls exemples
 * négatifs** que le modèle verra jamais. Sans eux il n'apprend que la moitié
 * haute de la distribution et ne sait pas reconnaître un mauvais jour.
 * Trois secondes par jour, et uniquement trois secondes — d'où l'absence de
 * champ libre ici : la raison se saisit plus tard, si l'envie prend.
 */
export function DailyLogSwipe() {
  const queryClient = useQueryClient();

  const { data } = useQuery({
    queryKey: ["daily-log", "today"],
    queryFn: api.dailyLogToday,
  });

  const answer = useMutation({
    mutationFn: (status: DailyLogStatus) => api.setDailyLog({ status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["daily-log", "today"] });
    },
  });

  // Masquée dès qu'il y a une réponse : une question déjà répondue qui reste
  // affichée finit par ne plus être lue du tout.
  if (!data || data.answered) return null;

  return (
    <section className="px-5" aria-label="Journal du jour">
      <div className="rounded-card border border-line bg-card px-4 py-3">
        <p className="text-[12px] font-semibold uppercase tracking-wide text-mute">
          Aujourd&apos;hui
        </p>
        <div className="mt-2 flex gap-2">
          {CHOICES.map(({ status, label }) => (
            <button
              key={status}
              type="button"
              disabled={answer.isPending}
              onClick={() => answer.mutate(status)}
              className="min-h-touch flex-1 rounded-button border border-line bg-soft px-2 text-[13px] font-semibold leading-tight text-ink disabled:opacity-50"
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
