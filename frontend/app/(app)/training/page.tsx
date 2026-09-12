"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { MeasureWheel } from "@/components/training/MeasureWheel";
import { ObjectiveGauge } from "@/components/training/ObjectiveGauge";
import { SessionMode } from "@/components/training/SessionMode";
import { ScreenHeader } from "@/components/shell/ScreenHeader";
import {
  IconChevronDown,
  IconClock,
  IconDumbbell,
  IconSearch,
} from "@/components/ui/Icons";
import { api } from "@/lib/api";
import { durationLabel, scoreClass, shortDate } from "@/lib/format";
import type { Exercise, Formula, Objective } from "@/lib/types";

/**
 * **Training** — trois jauges, les formules, la prochaine séance.
 *
 * Rendu plein cadre (V4 de `docs/DESIGN-EXPLORATION.md`) : sur cet écran, le
 * fait que l'objectif en retard passe en accent dit tout sans une ligne de
 * texte. C'est ce qui remplace un tableau de bord qu'il faudrait déchiffrer.
 *
 * L'ordre de l'écran est celui de la décision : où j'en suis (les jauges), ce
 * que je fais maintenant (la proposition), ce qu'il reste à faire cette
 * semaine (les formules), ce que j'ai fait (l'historique). Le rappel
 * « mesurer » passe devant tout quand la fréquence est dépassée : un objectif
 * qu'on ne mesure plus n'est plus un objectif.
 */

/** Les catégories de la bibliothèque, dans l'ordre du document design. */
const CATEGORIES = [
  { key: "mobility", label: "Mobilité" },
  { key: "strength", label: "Renfo" },
  { key: "core", label: "Gainage" },
] as const;

function FormulaCard({
  formula,
  onStart,
  starting,
}: {
  formula: Formula;
  onStart: (formula: Formula) => void;
  starting: boolean;
}) {
  const [open, setOpen] = useState(false);
  const target = formula.weekly_target;
  const done = formula.done_this_week;

  return (
    <article className="overflow-hidden rounded-card border border-line bg-card">
      <div className="flex items-start gap-3 px-4 pt-4">
        <div className="min-w-0 flex-1">
          <h3 className="font-display text-[21px] font-semibold uppercase leading-none text-ink">
            {formula.name}
          </h3>
          <p className="tabular mt-1.5 flex items-center gap-1.5 text-[13px] text-mute">
            <IconClock className="h-4 w-4 shrink-0" />
            {formula.duration_min} min
            {target > 0 ? (
              <span
                className={
                  done >= target ? "font-semibold text-ink-2" : "text-mute"
                }
              >
                · {done} / {target} cette semaine
              </span>
            ) : (
              <span>· à la demande</span>
            )}
          </p>
        </div>
        <button
          type="button"
          onClick={() => onStart(formula)}
          disabled={starting}
          className="min-h-touch shrink-0 rounded-button bg-accent px-4 text-[15px] font-semibold text-on-accent disabled:opacity-50"
        >
          Commencer
        </button>
      </div>

      {/* Le principe qui la justifie — c'est ce qui la distingue d'un
          programme recopié, et ce qui permet de trancher entre deux. */}
      <p className="px-4 pt-2.5 text-[13px] leading-snug text-ink-2">
        {formula.principle}
      </p>

      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="mt-2 flex min-h-touch w-full items-center justify-between gap-3 border-t border-line px-4 text-left"
      >
        <span className="text-[13px] font-semibold text-mute">
          {formula.items.length} exercices
        </span>
        <IconChevronDown
          className={`h-5 w-5 shrink-0 text-mute transition-transform ${
            open ? "rotate-180" : ""
          }`}
        />
      </button>

      {open ? (
        <ol className="border-t border-line">
          {formula.items.map((item) => (
            <li
              key={item.id}
              className="flex items-baseline justify-between gap-3 border-b border-line px-4 py-2 last:border-0"
            >
              <span className="min-w-0 flex-1 text-[14px] text-ink">
                {item.exercise.name}
                {item.note ? (
                  <span className="text-mute"> · {item.note}</span>
                ) : null}
              </span>
              <span className="tabular shrink-0 text-[13px] font-semibold text-ink-2">
                {item.sets > 1 ? `${item.sets} × ` : ""}
                {item.duration_s ? `${item.duration_s} s` : `${item.reps}`}
              </span>
            </li>
          ))}
        </ol>
      ) : null}
    </article>
  );
}

function ExerciseLibrary() {
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState<
    (typeof CATEGORIES)[number]["key"] | null
  >(null);

  const exercises = useQuery({
    queryKey: ["exercises", category],
    queryFn: () => api.exercises(category ? { category } : {}),
    enabled: open,
  });

  return (
    <section className="px-5 pt-6" aria-label="Bibliothèque d'exercices">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex min-h-touch w-full items-center justify-center gap-2 rounded-button border border-line bg-card px-4 text-[15px] font-semibold text-ink-2"
      >
        <IconSearch className="h-5 w-5" />
        Bibliothèque d&apos;exercices
      </button>

      {open ? (
        <>
          <div className="flex gap-2 overflow-x-auto pb-1 pt-3">
            <button
              type="button"
              onClick={() => setCategory(null)}
              aria-pressed={category === null}
              className={`min-h-touch shrink-0 rounded-pill border px-4 text-[14px] font-semibold ${
                category === null
                  ? "border-accent bg-accent text-on-accent"
                  : "border-line bg-card text-ink-2"
              }`}
            >
              Tous
            </button>
            {CATEGORIES.map((entry) => (
              <button
                key={entry.key}
                type="button"
                onClick={() =>
                  setCategory(category === entry.key ? null : entry.key)
                }
                aria-pressed={category === entry.key}
                className={`min-h-touch shrink-0 rounded-pill border px-4 text-[14px] font-semibold ${
                  category === entry.key
                    ? "border-accent bg-accent text-on-accent"
                    : "border-line bg-card text-ink-2"
                }`}
              >
                {entry.label}
              </button>
            ))}
          </div>

          {exercises.isPending ? (
            <p className="pt-3 text-[14px] text-mute">Lecture…</p>
          ) : (
            <ul className="mt-3 flex flex-col gap-2">
              {(exercises.data ?? []).map((exercise: Exercise) => (
                <li
                  key={exercise.id}
                  className="flex gap-3 rounded-card border border-line bg-card p-3"
                >
                  {exercise.image_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={exercise.image_url}
                      alt=""
                      loading="lazy"
                      className="h-16 w-16 shrink-0 rounded-cell border border-line bg-soft object-cover"
                    />
                  ) : null}
                  <div className="min-w-0 flex-1">
                    <p className="text-[15px] font-semibold text-ink">
                      {exercise.name}
                    </p>
                    {exercise.instructions ? (
                      <p className="mt-0.5 line-clamp-3 text-[13px] leading-snug text-ink-2">
                        {exercise.instructions}
                      </p>
                    ) : null}
                    {/* Source et licence, sur chaque ligne : une image CC BY-SA
                        ne s'affiche pas comme une image du domaine public. */}
                    <p className="mt-1 truncate text-[11px] text-mute">
                      {exercise.muscle_group ? `${exercise.muscle_group} · ` : ""}
                      {exercise.source}
                      {exercise.license ? ` · ${exercise.license}` : ""}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      ) : null}
    </section>
  );
}

export default function TrainingPage() {
  const queryClient = useQueryClient();
  const [measuring, setMeasuring] = useState<Objective | null>(null);
  const [session, setSession] = useState<{
    formula: Formula;
    workoutId: number;
  } | null>(null);
  const [swapped, setSwapped] = useState<Formula | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);

  const overview = useQuery({
    queryKey: ["training-overview"],
    queryFn: api.trainingOverview,
  });

  const measure = useMutation({
    mutationFn: ({ id, value }: { id: number; value: number }) =>
      api.addMeasurement(id, { value }),
    onSuccess: () => {
      setMeasuring(null);
      queryClient.invalidateQueries({ queryKey: ["training-overview"] });
      queryClient.invalidateQueries({ queryKey: ["training-today"] });
    },
  });

  const start = useMutation({
    mutationFn: (formula: Formula) => api.startWorkout(formula.id),
    onSuccess: (workout, formula) => {
      setSession({ formula, workoutId: workout.id });
    },
  });

  // L'objectif le plus en retard — le seul en accent. Un objectif sans mesure
  // est le plus en retard de tous : c'est d'abord de mesurer qu'il a besoin.
  const behindSlug = useMemo(() => {
    const objectives = overview.data?.objectives ?? [];
    if (objectives.length === 0) return null;
    return objectives.reduce((worst, item) =>
      (item.ratio ?? -1) < (worst.ratio ?? -1) ? item : worst,
    ).slug;
  }, [overview.data]);

  if (session) {
    return (
      <SessionMode
        formula={session.formula}
        workoutId={session.workoutId}
        onFinished={() => {
          setSession(null);
          setSwapped(null);
          queryClient.invalidateQueries({ queryKey: ["training-overview"] });
          queryClient.invalidateQueries({ queryKey: ["training-today"] });
        }}
        onAbandon={() => {
          // Séance ouverte par erreur, aucune série faite : on la retire au
          // lieu de laisser une ligne vide dans l'historique.
          api.deleteWorkout(session.workoutId).catch(() => undefined);
          setSession(null);
        }}
      />
    );
  }

  if (overview.isPending) {
    return (
      <>
        <ScreenHeader title="Training" />
        <p className="px-5 text-[14px] text-mute">Chargement…</p>
      </>
    );
  }

  if (overview.error || !overview.data) {
    return (
      <>
        <ScreenHeader title="Training" />
        <p className="mx-5 rounded-card border border-line bg-card px-5 py-6 text-[14px] text-ink-2">
          Training indisponible. Réessaie quand le réseau revient.
        </p>
      </>
    );
  }

  const { objectives, formulas, proposal, recent } = overview.data;
  const chosen = swapped ?? proposal.formula;
  const toMeasure = objectives.filter((item) => item.needs_measurement);

  return (
    <main className="pb-8">
      <ScreenHeader
        title="Training"
        subtitle="Objectifs mesurés, formules, séances."
      />

      {/* Le rappel passe devant : un objectif qu'on ne mesure plus n'est plus
          un objectif. */}
      {toMeasure.length > 0 && !measuring ? (
        <section className="px-5 pb-4">
          <button
            type="button"
            onClick={() => setMeasuring(toMeasure[0])}
            className="flex w-full items-center gap-3 rounded-card bg-accent px-5 py-4 text-left text-on-accent"
          >
            <span className="min-w-0 flex-1">
              <span className="block text-[11px] font-semibold uppercase tracking-[0.14em] opacity-75">
                À mesurer
              </span>
              <span className="mt-1 block truncate font-display text-[26px] font-bold uppercase leading-none tracking-tight">
                {toMeasure.map((item) => item.name).join(" · ")}
              </span>
            </span>
          </button>
        </section>
      ) : null}

      {measuring ? (
        <section className="px-5 pb-5">
          <MeasureWheel
            objective={measuring}
            pending={measure.isPending}
            onCancel={() => setMeasuring(null)}
            onSubmit={(value) =>
              measure.mutate({ id: measuring.id, value })
            }
          />
        </section>
      ) : null}

      <section className="flex flex-col gap-3 px-5" aria-label="Objectifs">
        {objectives.map((objective) => (
          <ObjectiveGauge
            key={objective.id}
            objective={objective}
            behind={objective.slug === behindSlug}
            onMeasure={() => setMeasuring(objective)}
          />
        ))}
      </section>

      {/* La séance du jour : une seule, remplaçable en un tap. */}
      {chosen ? (
        <section className="px-5 pt-6" aria-label="Séance du jour">
          <h2 className="pb-2 text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
            La séance du jour
          </h2>
          <article className="overflow-hidden rounded-card border border-line bg-card">
            <div className="px-5 pt-5">
              <h3 className="font-display text-[32px] font-bold uppercase leading-none tracking-tight text-ink">
                {chosen.name}
              </h3>
              <p className="tabular mt-2 flex items-center gap-1.5 text-[14px] text-ink-2">
                <IconClock className="h-4 w-4 shrink-0" />
                {chosen.duration_min} min · {chosen.items.length} exercices
              </p>
              <p className="mt-2 text-[14px] leading-snug text-mute">
                {swapped ? chosen.principle : proposal.reason}
              </p>
            </div>

            <div className="flex gap-3 px-5 pb-5 pt-4">
              <button
                type="button"
                onClick={() => start.mutate(chosen)}
                disabled={start.isPending}
                className="flex min-h-[56px] flex-[2] items-center justify-center gap-2 rounded-button bg-accent px-4 text-[17px] font-semibold text-on-accent disabled:opacity-50"
              >
                <IconDumbbell className="h-5 w-5" />
                {start.isPending ? "Ouverture…" : "Commencer"}
              </button>
              {proposal.alternatives.length > 0 ? (
                <button
                  type="button"
                  onClick={() => setPickerOpen((open) => !open)}
                  aria-expanded={pickerOpen}
                  className="min-h-[56px] flex-1 rounded-button border border-line bg-card px-4 text-[15px] font-semibold text-ink-2"
                >
                  Autre chose
                </button>
              ) : null}
            </div>

            {pickerOpen ? (
              <ul className="border-t border-line">
                {[
                  ...(swapped && proposal.formula ? [proposal.formula] : []),
                  ...proposal.alternatives,
                ]
                  .filter((formula) => formula.id !== chosen.id)
                  .map((formula) => (
                    <li
                      key={formula.id}
                      className="border-b border-line last:border-0"
                    >
                      <button
                        type="button"
                        onClick={() => {
                          setSwapped(formula);
                          setPickerOpen(false);
                        }}
                        className="flex min-h-touch w-full items-center gap-3 px-5 py-2.5 text-left"
                      >
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[15px] font-semibold text-ink">
                            {formula.name}
                          </span>
                          <span className="block truncate text-[12px] text-mute">
                            {formula.duration_min} min ·{" "}
                            {formula.weekly_target > 0
                              ? `${formula.done_this_week} / ${formula.weekly_target} cette semaine`
                              : "à la demande"}
                          </span>
                        </span>
                      </button>
                    </li>
                  ))}
              </ul>
            ) : null}
          </article>

          {proposal.surf_streak >= 3 ? (
            <p className="pt-2 text-[12px] leading-snug text-mute">
              {proposal.surf_streak} jours de surf d&apos;affilée : le renfo est
              écarté aujourd&apos;hui.
            </p>
          ) : null}
        </section>
      ) : null}

      <section className="px-5 pt-6" aria-label="Formules">
        <h2 className="pb-2 text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
          Les formules
        </h2>
        <div className="flex flex-col gap-3">
          {formulas
            .filter((formula) => formula.variant_of === null)
            .map((formula) => (
              <FormulaCard
                key={formula.id}
                formula={formula}
                starting={start.isPending}
                onStart={(item) => start.mutate(item)}
              />
            ))}
        </div>
        <p className="pt-2 text-[12px] leading-snug text-mute">
          Chaque formule a deux variantes, proposées quand elle revient trop
          souvent — une séance faite tous les matins pendant six mois se fait de
          moins en moins bien.
        </p>
      </section>

      <ExerciseLibrary />

      {recent.length > 0 ? (
        <section className="px-5 pt-6" aria-label="Séances récentes">
          <h2 className="pb-2 text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
            Dernières séances
          </h2>
          <ul className="overflow-hidden rounded-card border border-line bg-card">
            {recent.map((workout) => (
              <li
                key={workout.id}
                className="flex items-center gap-3 border-b border-line px-4 py-2.5 last:border-0"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[15px] font-semibold text-ink">
                    {workout.formula_name}
                  </span>
                  <span className="tabular block text-[12px] text-mute">
                    {shortDate(workout.started_at)}
                    {workout.duration_min !== null
                      ? ` · ${durationLabel(workout.duration_min)}`
                      : ""}
                    {/* Écourtée, et dite comme telle : c'est une information
                        sur la formule, pas un échec à cacher. */}
                    {workout.cut_short ? " · écourtée" : ""}
                  </span>
                </span>
                <span
                  className={`tabular flex h-9 w-9 shrink-0 items-center justify-center rounded-chip font-display text-[18px] font-bold leading-none ${
                    workout.feeling === null
                      ? "border border-line bg-soft text-mute"
                      : scoreClass(workout.feeling)
                  }`}
                >
                  {workout.feeling ?? "—"}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </main>
  );
}
