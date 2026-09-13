"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { IconCheck, IconPlus, IconTrash } from "@/components/ui/Icons";
import { api } from "@/lib/api";
import { num } from "@/lib/format";
import { HABIT_ICON_KEYS, HabitIcon } from "@/lib/habit-icons";
import type { Habit, HabitKind, HabitPeriod } from "@/lib/types";

/**
 * **Jules définit ses propres habitudes.** Rien n'est semé.
 *
 * C'est une différence de fond avec les formules d'entraînement du lot 4 : une
 * formule proposée par l'app est un point de départ utile, une habitude
 * proposée par l'app est une leçon de morale. On ne suggère donc ni « boire
 * deux litres » ni « se coucher à 22 h ».
 *
 * La **pause** est le geste normal. La suppression existe — une habitude créée
 * par erreur le premier jour n'a pas à hanter le profil — mais elle n'est
 * proposée qu'après, et elle dit ce qu'elle emporte.
 */

const KINDS: { value: HabitKind; label: string; hint: string }[] = [
  { value: "count", label: "Compteur", hint: "combien de fois" },
  { value: "check", label: "Oui / non", hint: "fait ou pas fait" },
];

const PERIODS: { value: HabitPeriod; label: string }[] = [
  { value: "day", label: "par jour" },
  { value: "week", label: "par semaine" },
];

const TARGETS = [null, 1, 2, 3, 4, 5, 6, 8, 10, 12];

function HabitForm({ onDone }: { onDone: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [icon, setIcon] = useState<string>("check");
  const [kind, setKind] = useState<HabitKind>("count");
  const [unit, setUnit] = useState("");
  const [target, setTarget] = useState<number | null>(null);
  const [period, setPeriod] = useState<HabitPeriod>("day");

  const create = useMutation({
    mutationFn: () =>
      api.createHabit({
        name: name.trim(),
        icon,
        kind,
        unit: unit.trim() || null,
        target,
        target_period: period,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["habits"] });
      queryClient.invalidateQueries({ queryKey: ["profile-stats"] });
      onDone();
    },
  });

  return (
    <div className="mt-3 rounded-card border border-line bg-card px-4 pb-4">
      <p className="pb-1.5 pt-3 text-[12px] font-semibold uppercase tracking-wide text-mute">
        Nom
      </p>
      <input
        type="text"
        value={name}
        onChange={(event) => setName(event.target.value)}
        placeholder="Eau, lecture, étirements…"
        aria-label="Nom de l'habitude"
        className="min-h-touch w-full rounded-button border border-line bg-soft px-3 text-[16px] text-ink placeholder:text-mute"
      />

      <p className="pb-1.5 pt-3 text-[12px] font-semibold uppercase tracking-wide text-mute">
        Icône
      </p>
      <div className="flex flex-wrap gap-1.5">
        {HABIT_ICON_KEYS.map((key) => {
          return (
            <button
              key={key}
              type="button"
              onClick={() => setIcon(key)}
              aria-pressed={icon === key}
              aria-label={`Icône ${key}`}
              className={`flex h-touch w-touch items-center justify-center rounded-cell border ${
                icon === key
                  ? "border-accent bg-accent text-on-accent"
                  : "border-line bg-card text-ink-2"
              }`}
            >
              <HabitIcon name={key} className="h-5 w-5" />
            </button>
          );
        })}
      </div>

      <p className="pb-1.5 pt-3 text-[12px] font-semibold uppercase tracking-wide text-mute">
        Type
      </p>
      <div className="flex gap-1.5">
        {KINDS.map((entry) => (
          <button
            key={entry.value}
            type="button"
            onClick={() => setKind(entry.value)}
            aria-pressed={kind === entry.value}
            className={`min-h-touch flex-1 rounded-button border px-2 text-[14px] font-semibold ${
              kind === entry.value
                ? "border-accent bg-accent text-on-accent"
                : "border-line bg-card text-ink-2"
            }`}
          >
            {entry.label}
          </button>
        ))}
      </div>

      {kind === "count" ? (
        <>
          <p className="pb-1.5 pt-3 text-[12px] font-semibold uppercase tracking-wide text-mute">
            Unité{" "}
            <span className="font-normal normal-case">— facultative</span>
          </p>
          <input
            type="text"
            value={unit}
            onChange={(event) => setUnit(event.target.value)}
            placeholder="verres, minutes, fois"
            aria-label="Unité"
            className="min-h-touch w-full rounded-button border border-line bg-soft px-3 text-[16px] text-ink placeholder:text-mute"
          />
        </>
      ) : null}

      <p className="pb-1.5 pt-3 text-[12px] font-semibold uppercase tracking-wide text-mute">
        Objectif{" "}
        <span className="font-normal normal-case">
          — facultatif, « — » pour juste observer
        </span>
      </p>
      <div className="flex gap-1.5 overflow-x-auto pb-1">
        {TARGETS.map((value) => (
          <button
            key={String(value)}
            type="button"
            onClick={() => setTarget(value)}
            aria-pressed={target === value}
            className={`tabular min-h-touch shrink-0 rounded-pill border px-3.5 text-[15px] font-semibold ${
              target === value
                ? "border-accent bg-accent text-on-accent"
                : "border-line bg-card text-ink-2"
            }`}
          >
            {value === null ? "—" : value}
          </button>
        ))}
      </div>

      {target !== null ? (
        <div className="flex gap-1.5 pt-2">
          {PERIODS.map((entry) => (
            <button
              key={entry.value}
              type="button"
              onClick={() => setPeriod(entry.value)}
              aria-pressed={period === entry.value}
              className={`min-h-touch flex-1 rounded-button border px-2 text-[14px] font-semibold ${
                period === entry.value
                  ? "border-accent bg-accent text-on-accent"
                  : "border-line bg-card text-ink-2"
              }`}
            >
              {entry.label}
            </button>
          ))}
        </div>
      ) : null}

      <div className="flex gap-3 pt-4">
        <button
          type="button"
          onClick={() => create.mutate()}
          disabled={name.trim().length === 0 || create.isPending}
          className="flex min-h-touch flex-1 items-center justify-center gap-2 rounded-button bg-accent px-4 text-[16px] font-semibold text-on-accent disabled:opacity-40"
        >
          <IconCheck className="h-5 w-5" />
          Créer
        </button>
        <button
          type="button"
          onClick={onDone}
          className="min-h-touch rounded-button border border-line bg-card px-4 text-[15px] font-semibold text-ink-2"
        >
          Annuler
        </button>
      </div>
    </div>
  );
}

function HabitLine({ habit }: { habit: Habit }) {
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["habits"] });
    queryClient.invalidateQueries({ queryKey: ["profile-stats"] });
  };

  const toggle = useMutation({
    mutationFn: () =>
      api.updateHabit(habit.id, {
        name: habit.name,
        is_active: !habit.is_active,
      }),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: () => api.deleteHabit(habit.id),
    onSuccess: invalidate,
  });

  return (
    <li className="border-b border-line last:border-0">
      <div className="flex items-center gap-3 px-4 py-2.5">
        <HabitIcon
          name={habit.icon}
          className={`h-5 w-5 shrink-0 ${
            habit.is_active ? "text-ink-2" : "text-mute"
          }`}
        />
        <span className="min-w-0 flex-1">
          <span
            className={`block truncate text-[15px] font-semibold ${
              habit.is_active ? "text-ink" : "text-mute"
            }`}
          >
            {habit.name}
          </span>
          <span className="block truncate text-[12px] text-mute">
            {habit.target !== null
              ? `${num(habit.target, habit.target % 1 ? 1 : 0)}${
                  habit.unit ? ` ${habit.unit}` : ""
                } ${habit.target_period === "day" ? "par jour" : "par semaine"}`
              : "sans objectif"}
            {habit.is_active ? "" : " · en pause"}
          </span>
        </span>

        <button
          type="button"
          onClick={() => toggle.mutate()}
          disabled={toggle.isPending}
          className="min-h-touch shrink-0 rounded-button border border-line bg-soft px-3 text-[13px] font-semibold text-ink-2"
        >
          {habit.is_active ? "Pause" : "Reprendre"}
        </button>

        {!habit.is_active ? (
          <button
            type="button"
            onClick={() => setConfirming((value) => !value)}
            aria-label={`Supprimer ${habit.name}`}
            className="flex h-touch w-touch shrink-0 items-center justify-center rounded-button text-mute"
          >
            <IconTrash className="h-5 w-5" />
          </button>
        ) : null}
      </div>

      {confirming ? (
        <div className="border-t border-line bg-soft px-4 py-3">
          <p className="text-[13px] leading-snug text-ink-2">
            Supprimer emporte tous les comptages de cette habitude. La pause,
            elle, les garde.
          </p>
          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={() => remove.mutate()}
              disabled={remove.isPending}
              className="min-h-touch flex-1 rounded-button border border-line bg-card px-4 text-[15px] font-semibold text-ink"
            >
              Supprimer quand même
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="min-h-touch rounded-button bg-accent px-4 text-[15px] font-semibold text-on-accent"
            >
              Garder
            </button>
          </div>
        </div>
      ) : null}
    </li>
  );
}

export function HabitSettings() {
  const [adding, setAdding] = useState(false);

  const habits = useQuery({
    queryKey: ["habits", "all"],
    queryFn: () => api.habits(true),
  });
  const list = habits.data ?? [];

  return (
    <section className="px-5 pb-6" aria-label="Habitudes">
      <h2 className="pb-2 text-[12px] font-semibold uppercase tracking-wide text-mute">
        Habitudes
      </h2>

      {list.length === 0 && !adding ? (
        <p className="rounded-card border border-line bg-card px-4 py-3 text-[14px] leading-snug text-ink-2">
          Aucune habitude. Définis les tiennes : un compteur, une icône, et un
          objectif si tu en veux un. Elles se comptent ensuite en un tap depuis
          Jour.
        </p>
      ) : (
        <ul className="overflow-hidden rounded-card border border-line bg-card">
          {list.map((habit) => (
            <HabitLine key={habit.id} habit={habit} />
          ))}
        </ul>
      )}

      {adding ? (
        <HabitForm onDone={() => setAdding(false)} />
      ) : (
        <button
          type="button"
          onClick={() => setAdding(true)}
          className="mt-3 flex min-h-touch w-full items-center justify-center gap-2 rounded-button border border-line bg-card px-4 text-[15px] font-semibold text-ink-2"
        >
          <IconPlus className="h-5 w-5" />
          Nouvelle habitude
        </button>
      )}
    </section>
  );
}
