"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { IconBasket, IconClock, IconRefresh } from "@/components/ui/Icons";
import { api } from "@/lib/api";
import { num } from "@/lib/format";
import { MEALS, MEAL_LABELS, type Meal } from "@/lib/types";

/**
 * **Le menu de la semaine**, et sa liste de courses.
 *
 * Un glouton sous contrainte de macros et de variété, calculé côté serveur —
 * lisible et testable, pas une IA (cf. PROJET.md §9). Ce qui compte à l'écran,
 * c'est **la régénération d'un seul repas** : un menu qu'il faut refaire en
 * entier pour corriger un dîner se jette, un menu dont on change un plat se
 * garde.
 *
 * La liste de courses est le vrai produit de cet écran. Sept dîners qui
 * demandent chacun deux cents grammes de riz font un kilo quatre de riz, et
 * c'est ça qu'on lit au supermarché — pas sept lignes de riz.
 */

const DAYS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"];

/** Grammes vers une quantité lisible : au-delà du kilo, on passe au kilo. */
function amount(grams: number): string {
  return grams >= 1000 ? `${num(grams / 1000, 1)} kg` : `${Math.round(grams)} g`;
}

export function WeekMenu() {
  const queryClient = useQueryClient();
  const [shoppingOpen, setShoppingOpen] = useState(false);

  const plan = useQuery({ queryKey: ["meal-plan"], queryFn: () => api.mealPlan() });

  const invalidate = (data: unknown) => {
    queryClient.setQueryData(["meal-plan"], data);
    queryClient.invalidateQueries({ queryKey: ["nutrition-day"] });
  };

  const generate = useMutation({
    mutationFn: () => api.generateMealPlan(),
    onSuccess: invalidate,
  });

  const regenerate = useMutation({
    mutationFn: ({ day, meal }: { day: number; meal: Meal }) =>
      api.regenerateMeal(day, meal),
    onSuccess: invalidate,
  });

  const items = plan.data?.items ?? [];

  if (plan.isPending) {
    return <p className="px-5 text-[14px] text-mute">Lecture du menu…</p>;
  }

  if (items.length === 0) {
    return (
      <section className="px-5" aria-label="Menu de la semaine">
        <article className="rounded-card border border-line bg-card px-5 py-6">
          <h2 className="font-display text-[24px] font-semibold uppercase leading-none text-ink">
            Menu de la semaine
          </h2>
          <p className="mt-3 text-[15px] leading-snug text-ink-2">
            Vingt-huit repas tirés d&apos;une quarantaine de recettes simples,
            sous contrainte de calories, de protéines et de variété. Chaque plat
            se remplace en un tap.
          </p>
          <button
            type="button"
            onClick={() => generate.mutate()}
            disabled={generate.isPending}
            className="mt-4 flex min-h-touch w-full items-center justify-center rounded-button bg-accent px-4 text-[16px] font-semibold text-on-accent disabled:opacity-50"
          >
            {generate.isPending ? "Génération…" : "Générer la semaine"}
          </button>
        </article>
      </section>
    );
  }

  return (
    <section className="px-5" aria-label="Menu de la semaine">
      <div className="flex items-baseline justify-between gap-3 pb-2">
        <h2 className="text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
          Menu de la semaine
        </h2>
        <button
          type="button"
          onClick={() => generate.mutate()}
          disabled={generate.isPending}
          className="min-h-touch text-[13px] font-semibold text-mute disabled:opacity-50"
        >
          Tout régénérer
        </button>
      </div>

      <div className="flex flex-col gap-3">
        {DAYS.map((label, dayIndex) => {
          const dayMeals = items.filter((item) => item.day_index === dayIndex);
          if (dayMeals.length === 0) return null;
          const kcal = dayMeals.reduce(
            (total, item) => total + (item.recipe.kcal ?? 0) * item.servings,
            0,
          );

          return (
            <article
              key={label}
              className="overflow-hidden rounded-card border border-line bg-card"
            >
              <header className="flex items-baseline justify-between gap-3 border-b border-line bg-soft px-4 py-2">
                <h3 className="font-display text-[17px] font-semibold uppercase leading-none text-ink">
                  {label}
                </h3>
                {kcal > 0 ? (
                  <span className="tabular text-[12px] text-mute">
                    {num(kcal, 0)} kcal
                  </span>
                ) : null}
              </header>

              <ul>
                {MEALS.map((meal) => {
                  const item = dayMeals.find((entry) => entry.meal === meal);
                  if (!item) return null;
                  return (
                    <li
                      key={meal}
                      className="flex items-center gap-3 border-b border-line px-4 py-2 last:border-0"
                    >
                      <span className="w-[74px] shrink-0 text-[12px] font-semibold uppercase tracking-wide text-mute">
                        {MEAL_LABELS[meal]}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[15px] text-ink">
                          {item.recipe.name}
                        </span>
                        <span className="tabular flex items-center gap-1 text-[12px] text-mute">
                          <IconClock className="h-3.5 w-3.5" />
                          {item.recipe.prep_min} min
                          {item.recipe.kcal !== null
                            ? ` · ${num(item.recipe.kcal, 0)} kcal`
                            : ""}
                        </span>
                      </span>
                      <button
                        type="button"
                        onClick={() =>
                          regenerate.mutate({ day: dayIndex, meal })
                        }
                        disabled={regenerate.isPending}
                        aria-label={`Changer le ${MEAL_LABELS[meal].toLowerCase()} de ${label}`}
                        className="flex h-touch w-touch shrink-0 items-center justify-center rounded-button text-mute disabled:opacity-40"
                      >
                        <IconRefresh className="h-5 w-5" />
                      </button>
                    </li>
                  );
                })}
              </ul>
            </article>
          );
        })}
      </div>

      {/* La liste de courses, repliée : on l'ouvre une fois par semaine, au
          moment de partir, et elle n'a rien à faire au-dessus du menu. */}
      <button
        type="button"
        onClick={() => setShoppingOpen((open) => !open)}
        aria-expanded={shoppingOpen}
        className="mt-3 flex min-h-touch w-full items-center justify-center gap-2 rounded-button border border-line bg-card px-4 text-[15px] font-semibold text-ink-2"
      >
        <IconBasket className="h-5 w-5" />
        Liste de courses
        <span className="text-mute">
          ({plan.data?.shopping.length ?? 0} lignes)
        </span>
      </button>

      {shoppingOpen ? (
        <ul className="mt-2 overflow-hidden rounded-card border border-line bg-card">
          {(plan.data?.shopping ?? []).map((line) => (
            <li
              key={line.label}
              className="flex items-baseline justify-between gap-3 border-b border-line px-4 py-2 last:border-0"
            >
              <span className="min-w-0 flex-1 truncate text-[15px] text-ink">
                {line.label}
              </span>
              <span className="tabular shrink-0 text-[14px] font-semibold text-ink-2">
                {amount(line.quantity_g)}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
