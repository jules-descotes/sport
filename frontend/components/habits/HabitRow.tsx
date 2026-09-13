"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { api } from "@/lib/api";
import { num } from "@/lib/format";
import { HabitIcon } from "@/lib/habit-icons";
import type { Habit } from "@/lib/types";

/**
 * **La rangée de pastilles de l'écran Jour** — un tap, et c'est compté.
 *
 * Le ton est la contrainte principale, et elle est plus forte que toutes les
 * autres : **jamais de rouge, jamais de morale, jamais de série perdue**. Une
 * habitude atteinte passe en accent, une habitude non atteinte reste neutre.
 * Il n'y a pas de troisième état, parce que « raté » n'est pas une information
 * qu'on a envie de lire un mardi soir — et qu'une application qui gronde est
 * une application qu'on désinstalle.
 *
 * Deux gestes seulement :
 *
 * - **un tap** ajoute un ;
 * - **un appui long** retire un. C'est la correction, et elle est réversible
 *   sans ouvrir de menu. Côté serveur, retirer veut dire ajouter l'inverse :
 *   le geste a eu lieu, et il a été repris — les deux sont de la donnée.
 */

/** Durée d'appui à partir de laquelle on décompte. */
const LONG_PRESS_MS = 450;

function Pill({ habit }: { habit: Habit }) {
  const queryClient = useQueryClient();
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fired = useRef(false);

  const tap = useMutation({
    mutationFn: (quantity: number) => api.addHabitEvent(habit.id, quantity),
    onSuccess: (updated) => {
      // On remplace la ligne à sa place plutôt que d'invalider la liste :
      // recharger ferait clignoter toute la rangée à chaque tap.
      queryClient.setQueryData<Habit[]>(["habits"], (habits) =>
        (habits ?? []).map((item) => (item.id === updated.id ? updated : item)),
      );
      queryClient.invalidateQueries({ queryKey: ["profile-stats"] });
    },
  });

  const value = habit.target_period === "week" ? habit.week : habit.today;
  // **Le même écran dans les deux sens** (13/09, retours n° 4). Un objectif
  // `max` est tenu tant qu'on est en dessous ; un `min`, dès qu'on est
  // au-dessus. Et dans les deux cas il n'y a que deux états : accent quand
  // c'est tenu, neutre sinon. Pas de rouge, pas de troisième état — une
  // habitude qu'on cherche à réduire est déjà assez difficile à tenir sans
  // qu'une application s'en mêle.
  const reached =
    habit.target !== null &&
    (habit.target_direction === "max"
      ? value <= habit.target
      : value >= habit.target);

  const start = () => {
    fired.current = false;
    timer.current = setTimeout(() => {
      fired.current = true;
      if (value > 0) tap.mutate(-1);
    }, LONG_PRESS_MS);
  };

  const end = () => {
    if (timer.current !== null) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  };

  return (
    <button
      type="button"
      onPointerDown={start}
      onPointerUp={end}
      onPointerLeave={end}
      onPointerCancel={end}
      onContextMenu={(event) => event.preventDefault()}
      onClick={() => {
        // L'appui long a déjà décidé : le clic qui le suit ne doit pas
        // rajouter ce qu'on vient de retirer.
        if (fired.current) {
          fired.current = false;
          return;
        }
        tap.mutate(1);
      }}
      aria-label={`${habit.name} : ${num(value, value % 1 ? 1 : 0)}${
        habit.unit ? ` ${habit.unit}` : ""
      }`}
      className={`flex min-h-touch min-w-[68px] shrink-0 flex-col items-center justify-center gap-0.5 rounded-cell border px-2 py-1.5 transition-colors ${
        reached
          ? "border-accent bg-accent text-on-accent"
          : "border-line bg-card text-ink-2"
      }`}
    >
      <HabitIcon name={habit.icon} className="h-5 w-5" />
      <span className="tabular font-display text-[17px] font-bold leading-none">
        {num(value, value % 1 ? 1 : 0)}
        {habit.target !== null ? (
          <span className="text-[12px] font-semibold opacity-70">
            {habit.target_direction === "max" ? " max " : "/"}
            {num(habit.target, habit.target % 1 ? 1 : 0)}
          </span>
        ) : null}
      </span>
      <span className="max-w-[74px] truncate text-[11px] leading-none">
        {habit.name}
      </span>
    </button>
  );
}

export function HabitRow() {
  const [hintSeen, setHintSeen] = useState(false);

  const habits = useQuery({ queryKey: ["habits"], queryFn: () => api.habits() });
  const list = habits.data ?? [];

  if (habits.isPending || list.length === 0) return null;

  return (
    <section className="px-5" aria-label="Habitudes">
      <div
        className="flex gap-2 overflow-x-auto pb-1"
        onScroll={() => setHintSeen(true)}
      >
        {list.map((habit) => (
          <Pill key={habit.id} habit={habit} />
        ))}
      </div>
      {!hintSeen ? (
        <p className="pt-1 text-[11px] text-mute">
          Un tap ajoute, un appui long retire.
        </p>
      ) : null}
    </section>
  );
}
