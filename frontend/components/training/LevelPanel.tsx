"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { IconChevronDown } from "@/components/ui/Icons";
import { api } from "@/lib/api";
import type { GroupLevel } from "@/lib/types";

/**
 * **Ton niveau, par groupe** — déduit, et corrigeable.
 *
 * Décidé le 13/09 (retours n° 3). Le niveau vient de `workout_sets` sur huit
 * semaines glissantes : ce qui a vraiment été fait, pas ce qu'on a déclaré un
 * dimanche soir.
 *
 * **La provenance est affichée, et c'est le point.** « Déduit de 14 séries » se
 * discute ; « niveau 3 » ne se discute pas. Un niveau qu'on ne peut pas
 * discuter est un niveau qu'on n'ira jamais corriger — et il y a de vraies
 * raisons de le corriger : une reprise après un plâtre, un mois passé à
 * grimper. Une déduction ne discute pas avec quelqu'un qui était là.
 *
 * « Reprendre la déduction » efface la correction. Sans ce geste, une
 * correction posée un dimanche resterait vraie pour toujours.
 */

const ORIGIN_LABEL: Record<string, string> = {
  deduit: "déduit",
  defaut: "par défaut",
  manuel: "réglé à la main",
};

function Row({
  level,
  onSet,
  pending,
}: {
  level: GroupLevel;
  onSet: (value: number | null) => void;
  pending: boolean;
}) {
  return (
    <div className="border-t border-line py-2 first:border-0">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[15px] font-semibold text-ink">
          {level.group_label}
        </span>
        <span className="text-[12px] text-mute">
          {ORIGIN_LABEL[level.origin] ?? level.origin}
          {level.origin === "deduit"
            ? ` de ${level.sets_counted} séries`
            : level.origin === "defaut"
              ? " — rien de fait récemment"
              : ""}
          {level.best_reps ? ` · record ${level.best_reps} reps` : ""}
          {level.best_seconds ? ` · record ${level.best_seconds} s` : ""}
        </span>
      </div>

      <div className="flex items-center gap-1.5 pt-1.5">
        {[1, 2, 3, 4, 5].map((value) => (
          <button
            key={value}
            type="button"
            disabled={pending}
            aria-pressed={level.level === value}
            aria-label={`${level.group_label} : niveau ${value}`}
            onClick={() => onSet(level.level === value ? null : value)}
            className={`tabular flex h-touch flex-1 items-center justify-center rounded-cell font-display text-[18px] font-bold ${
              level.level === value
                ? "bg-accent text-on-accent"
                : "border border-line bg-card text-mute"
            }`}
          >
            {value}
          </button>
        ))}
      </div>

      {level.origin === "manuel" ? (
        <button
          type="button"
          onClick={() => onSet(null)}
          className="pt-1 text-[12px] text-mute underline underline-offset-2"
        >
          Reprendre la déduction
        </button>
      ) : null}
    </div>
  );
}

export function LevelPanel() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);

  const levels = useQuery({
    queryKey: ["training-levels"],
    queryFn: api.trainingLevels,
    enabled: open,
  });

  const set = useMutation({
    mutationFn: ({ group, level }: { group: string; level: number | null }) =>
      api.setTrainingLevel(group, level),
    onSuccess: (rows) => {
      queryClient.setQueryData(["training-levels"], rows);
      // Les propositions dépendent du niveau : elles changent avec lui.
      queryClient.invalidateQueries({ queryKey: ["compose"] });
      queryClient.invalidateQueries({ queryKey: ["training-overview"] });
    },
  });

  return (
    <section className="px-5 pt-6" aria-label="Ton niveau">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex min-h-touch w-full items-center justify-between gap-3 text-left"
      >
        <span>
          <span className="block text-[12px] font-semibold uppercase tracking-wide text-mute">
            Ton niveau
          </span>
          <span className="block text-[14px] text-ink-2">
            Déduit de ce que tu as fait — corrigeable
          </span>
        </span>
        <IconChevronDown
          className={`h-5 w-5 shrink-0 text-mute transition-transform ${
            open ? "rotate-180" : ""
          }`}
        />
      </button>

      {open ? (
        <div className="mt-3 rounded-card border border-line bg-card px-4 py-2">
          {levels.isPending ? (
            <p className="py-3 text-[14px] text-mute">Calcul…</p>
          ) : levels.error ? (
            <p className="py-3 text-[14px] text-ink-2">
              Niveaux indisponibles pour le moment.
            </p>
          ) : (
            (levels.data ?? []).map((level) => (
              <Row
                key={level.group}
                level={level}
                pending={set.isPending}
                onSet={(value) =>
                  set.mutate({ group: level.group, level: value })
                }
              />
            ))
          )}
          <p className="py-2 text-[12px] leading-snug text-mute">
            Huit semaines glissantes, séries passées exclues. Un groupe jamais
            travaillé part au niveau 2 — pas au 1, qui est réservé à ce qui se
            fait assis.
          </p>
        </div>
      ) : null}
    </section>
  );
}
