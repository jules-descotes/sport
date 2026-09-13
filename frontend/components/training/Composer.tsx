"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { ExerciseImage } from "@/components/training/ExerciseImage";
import { IconBack, IconCheck, IconPlus } from "@/components/ui/Icons";
import { api } from "@/lib/api";
import { durationLabel } from "@/lib/format";
import {
  EQUIPMENTS,
  EQUIPMENT_LABELS,
  EXERCISE_GROUPS,
  EXERCISE_GROUP_LABELS,
  INTENTS,
  INTENT_LABELS,
} from "@/lib/types";
import type {
  EquipmentKey,
  ExerciseGroup,
  GeneratedWorkout,
  Intent,
} from "@/lib/types";

/**
 * **Composer une séance** — trois choix, trois propositions.
 *
 * Décidé le 13/09 (retours n° 3). Trois écrans et pas un formulaire : le
 * groupe, la durée, le matériel. Un formulaire à cinq champs se remplit une
 * fois puis ne se rouvre plus ; trois taps se refont tous les matins.
 *
 * Les propositions arrivent en cartes, avec **le principe de chacune en une
 * ligne**. Ce n'est pas de la décoration : une proposition qu'on ne comprend
 * pas se remplace au hasard, et on finit par ne plus la lire — la leçon du
 * lot 4, appliquée au générateur.
 *
 * Tout ce qui est visible ici est en français, y compris les catégories, les
 * patterns et le matériel (règle E.3 du 13/09). Les libellés viennent du
 * serveur avec chaque exercice : l'écran ne porte pas une seconde copie du
 * dictionnaire, qui finirait par diverger.
 */

const DURATIONS = [10, 15, 20, 30, 45] as const;

type Step = "groupe" | "duree" | "materiel" | "resultat";

function Choice({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`min-h-[56px] flex-1 rounded-cell border px-3 text-[16px] font-semibold ${
        active
          ? "border-accent bg-accent text-on-accent"
          : "border-line bg-card text-ink-2"
      }`}
    >
      {children}
    </button>
  );
}

function WorkoutCard({
  workout,
  onStart,
  onSave,
  saving,
}: {
  workout: GeneratedWorkout;
  onStart: () => void;
  onSave: () => void;
  saving: boolean;
}) {
  const work = workout.items.filter((item) => !item.warmup);
  const warmup = workout.items.filter((item) => item.warmup);

  return (
    <article className="rounded-card border border-line bg-card">
      <button
        type="button"
        onClick={onStart}
        className="w-full px-4 pb-3 pt-4 text-left"
      >
        <p className="tabular text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
          {durationLabel(workout.duration_min)} · {work.length} exercices
          {warmup.length > 0 ? ` · ${warmup.length} d'échauffement` : ""}
        </p>
        {/* La ligne qui justifie la séance. Sans elle, les trois cartes se
            valent et le choix se fait au hasard. */}
        <p className="pt-1 font-display text-[22px] font-bold leading-tight text-ink">
          {workout.principle}
        </p>
      </button>

      <ul className="border-t border-line">
        {workout.items.map((item, index) => (
          <li
            key={`${item.exercise.id}-${index}`}
            className="flex items-center gap-3 border-b border-line px-4 py-2 last:border-0"
          >
            <ExerciseImage
              exercise={item.exercise}
              className="h-12 w-16 shrink-0"
            />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[15px] font-semibold text-ink">
                {item.exercise.name_fr ?? item.exercise.name}
              </span>
              <span className="tabular block text-[12px] text-mute">
                {item.warmup ? "Échauffement · " : ""}
                {item.sets} ×{" "}
                {item.duration_s ? `${item.duration_s} s` : `${item.reps} reps`}
                {item.note ? ` · ${item.note}` : ""}
                {item.rest_s > 0 ? ` · repos ${item.rest_s} s` : ""}
              </span>
            </span>
          </li>
        ))}
      </ul>

      <div className="flex gap-2 px-4 py-3">
        <button
          type="button"
          onClick={onStart}
          className="flex min-h-touch flex-[2] items-center justify-center gap-2 rounded-button bg-accent px-4 text-[16px] font-semibold text-on-accent"
        >
          <IconCheck className="h-5 w-5" />
          Faire celle-ci
        </button>
        <button
          type="button"
          onClick={onSave}
          disabled={saving}
          className="min-h-touch flex-1 rounded-button border border-line bg-card px-3 text-[14px] font-semibold text-ink-2 disabled:opacity-50"
        >
          {saving ? "…" : "Garder"}
        </button>
      </div>
    </article>
  );
}

export function Composer({
  onClose,
  onStart,
}: {
  onClose: () => void;
  /** Le slug de la formule sauvée, pour la lancer en mode séance. */
  onStart: (formulaId: number) => void;
}) {
  const [step, setStep] = useState<Step>("groupe");
  const [groups, setGroups] = useState<ExerciseGroup[]>(["abdos"]);
  const [duration, setDuration] = useState<number>(15);
  const [equipment, setEquipment] = useState<EquipmentKey[]>([]);
  const [intent, setIntent] = useState<Intent>("entretien");
  const [variant, setVariant] = useState(0);
  const [saved, setSaved] = useState<string | null>(null);

  const composed = useQuery({
    queryKey: ["compose", groups, duration, equipment, intent, variant],
    queryFn: () =>
      api.composeWorkout({
        groups,
        duration_min: duration,
        equipment,
        intent,
        variant,
      }),
    enabled: step === "resultat",
  });

  const keep = useMutation({
    mutationFn: (workout: GeneratedWorkout) =>
      api.saveComposedWorkout({
        key: workout.key,
        name: workout.name,
        groups,
        duration_min: duration,
        equipment,
        intent,
        variant,
      }),
    onSuccess: (formula) => setSaved(formula.name),
  });

  const start = useMutation({
    mutationFn: (workout: GeneratedWorkout) =>
      api.saveComposedWorkout({
        key: workout.key,
        // Le nom porte le jour : deux séances composées le même matin ne
        // doivent pas se confondre dans l'historique.
        name: `${workout.name} · ${new Date().toLocaleDateString("fr-FR", {
          day: "2-digit",
          month: "2-digit",
        })}`,
        groups,
        duration_min: duration,
        equipment,
        intent,
        variant,
      }),
    onSuccess: (formula) => onStart(formula.id),
  });

  const toggleGroup = (group: ExerciseGroup) =>
    setGroups((current) =>
      current.includes(group)
        ? current.filter((item) => item !== group).length
          ? current.filter((item) => item !== group)
          : current
        : [...current, group],
    );

  const toggleEquipment = (item: EquipmentKey) =>
    setEquipment((current) =>
      current.includes(item)
        ? current.filter((value) => value !== item)
        : [...current, item],
    );

  return (
    <div className="fixed inset-0 z-50 flex flex-col overflow-y-auto bg-bg">
      <header className="flex items-center gap-3 px-5 pb-1 pt-4">
        <button
          type="button"
          onClick={() =>
            step === "groupe"
              ? onClose()
              : setStep(
                  step === "duree"
                    ? "groupe"
                    : step === "materiel"
                      ? "duree"
                      : "materiel",
                )
          }
          aria-label="Retour"
          className="-ml-2 flex h-touch w-touch shrink-0 items-center justify-center rounded-button text-ink-2"
        >
          <IconBack className="h-5 w-5" />
        </button>
        <p className="text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
          Composer une séance
        </p>
      </header>

      {step === "groupe" ? (
        <section className="flex flex-col gap-3 px-5 pt-4">
          <h1 className="font-display text-[30px] font-bold uppercase leading-none text-ink">
            Quoi travailler ?
          </h1>
          <div className="grid grid-cols-2 gap-2">
            {EXERCISE_GROUPS.map((group) => (
              <Choice
                key={group}
                active={groups.includes(group)}
                onClick={() => toggleGroup(group)}
              >
                {EXERCISE_GROUP_LABELS[group]}
              </Choice>
            ))}
          </div>
          <button
            type="button"
            onClick={() => setStep("duree")}
            className="mt-2 flex min-h-[56px] items-center justify-center rounded-button bg-accent text-[17px] font-semibold text-on-accent"
          >
            Suivant
          </button>
        </section>
      ) : null}

      {step === "duree" ? (
        <section className="flex flex-col gap-3 px-5 pt-4">
          <h1 className="font-display text-[30px] font-bold uppercase leading-none text-ink">
            Combien de temps ?
          </h1>
          <div className="grid grid-cols-3 gap-2">
            {DURATIONS.map((value) => (
              <Choice
                key={value}
                active={duration === value}
                onClick={() => setDuration(value)}
              >
                {value} min
              </Choice>
            ))}
          </div>

          <h2 className="pt-3 text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
            Pour quoi faire
          </h2>
          <div className="flex gap-2">
            {INTENTS.map((value) => (
              <Choice
                key={value}
                active={intent === value}
                onClick={() => setIntent(value)}
              >
                {INTENT_LABELS[value]}
              </Choice>
            ))}
          </div>

          <button
            type="button"
            onClick={() => setStep("materiel")}
            className="mt-2 flex min-h-[56px] items-center justify-center rounded-button bg-accent text-[17px] font-semibold text-on-accent"
          >
            Suivant
          </button>
        </section>
      ) : null}

      {step === "materiel" ? (
        <section className="flex flex-col gap-3 px-5 pt-4">
          <h1 className="font-display text-[30px] font-bold uppercase leading-none text-ink">
            Avec quoi ?
          </h1>
          <p className="text-[14px] text-ink-2">
            Rien de coché = poids du corps seul. C&apos;est le cas du parking de
            la plage, et le plus fréquent.
          </p>
          <div className="grid grid-cols-2 gap-2">
            {EQUIPMENTS.filter((item) => item !== "aucun").map((item) => (
              <Choice
                key={item}
                active={equipment.includes(item)}
                onClick={() => toggleEquipment(item)}
              >
                {EQUIPMENT_LABELS[item]}
              </Choice>
            ))}
          </div>
          <button
            type="button"
            onClick={() => setStep("resultat")}
            className="mt-2 flex min-h-[56px] items-center justify-center rounded-button bg-accent text-[17px] font-semibold text-on-accent"
          >
            Composer
          </button>
        </section>
      ) : null}

      {step === "resultat" ? (
        <section className="flex flex-col gap-3 px-5 pb-10 pt-4">
          <h1 className="font-display text-[30px] font-bold uppercase leading-none text-ink">
            Trois façons
          </h1>

          {composed.isPending ? (
            <p className="text-[14px] text-mute">Composition…</p>
          ) : composed.error ? (
            <p className="rounded-card border border-line bg-card px-5 py-6 text-[14px] text-ink-2">
              Impossible de composer pour le moment.
            </p>
          ) : composed.data && composed.data.workouts.length === 0 ? (
            // Un écran blanc n'apprend rien : on dit ce qui manque.
            <div className="rounded-card border border-line bg-card px-5 py-6">
              <p className="text-[15px] text-ink">
                Rien à proposer avec ces choix.
              </p>
              {composed.data.reasons.length > 0 ? (
                <ul className="mt-2 list-inside list-disc text-[14px] text-ink-2">
                  {composed.data.reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              ) : null}
              <p className="mt-3 text-[13px] text-mute">
                Un exercice sans nom français ou sans image n&apos;est jamais
                proposé — c&apos;est voulu. Relance l&apos;import des exercices
                pour en avoir davantage.
              </p>
            </div>
          ) : (
            <>
              {composed.data?.levels.map((level) => (
                <p key={level.group} className="text-[13px] text-mute">
                  {level.group_label} — niveau {level.level}{" "}
                  {level.origin === "deduit"
                    ? `(déduit de ${level.sets_counted} séries)`
                    : level.origin === "manuel"
                      ? "(réglé à la main)"
                      : "(par défaut, rien de fait récemment)"}
                </p>
              ))}

              {composed.data?.workouts.map((workout) => (
                <WorkoutCard
                  key={workout.key}
                  workout={workout}
                  saving={keep.isPending || start.isPending}
                  onStart={() => start.mutate(workout)}
                  onSave={() => keep.mutate(workout)}
                />
              ))}

              {saved ? (
                <p className="text-[14px] text-ink-2">
                  « {saved} » est gardée dans tes formules.
                </p>
              ) : null}

              <button
                type="button"
                onClick={() => setVariant((value) => (value + 1) % 100)}
                className="flex min-h-touch items-center justify-center gap-2 rounded-button border border-line bg-card px-4 text-[15px] font-semibold text-ink-2"
              >
                <IconPlus className="h-5 w-5" />
                Autre chose
              </button>
            </>
          )}
        </section>
      ) : null}
    </div>
  );
}
