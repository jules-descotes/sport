"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { RecipePicker } from "@/components/nutrition/RecipePicker";
import { RecipeSheet } from "@/components/nutrition/RecipeSheet";
import { SlotActions, SwapPicker, type Slot } from "@/components/nutrition/SlotSheet";
import {
  IconAway,
  IconBasket,
  IconClock,
  IconMore,
  IconRefresh,
} from "@/components/ui/Icons";
import { api } from "@/lib/api";
import { num } from "@/lib/format";
import { buyHint, buyQuantity } from "@/lib/shopping";
import { MEAL_LABELS, PLANNED_MEALS, type MealPlan, type Recipe } from "@/lib/types";

/**
 * **Le menu de la semaine**, et sa liste de courses.
 *
 * Quatorze créneaux : sept déjeuners, sept dîners. Le petit déjeuner et
 * l'en-cas ne s'y trouvent plus — ils se journalisent toujours, ils ne se
 * prévoient plus. Un petit déjeuner ne se choisit pas le dimanche pour le
 * mardi : il se répète. Un en-cas planifié est un en-cas qu'on ne mange pas.
 *
 * **Les quatorze créneaux sont toujours rendus**, même vides. Un jeudi soir
 * sans ligne se relit trois fois avant qu'on comprenne qu'il manque quelque
 * chose ; un jeudi soir marqué « à choisir » se corrige d'un tap.
 *
 * Trois états par créneau, et le troisième est celui qui manquait : un plat
 * prévu, un créneau à remplir, ou **« pas là »**. Le dernier ne se contente
 * pas de vider la ligne — il sort les ingrédients de la liste de courses. On
 * n'achète pas le poisson d'un dîner qu'on prendra au restaurant.
 *
 * La liste de courses reste le vrai produit de cet écran, et elle parle
 * maintenant la langue du rayon : trois œufs, un litre et demi de lait, quatre
 * cents grammes de riz.
 */

const DAYS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"];

type Sheet =
  | { kind: "actions"; slot: Slot }
  | { kind: "swap"; slot: Slot }
  | { kind: "pick"; slot: Slot }
  | { kind: "recipe"; id: number; slot?: Slot };

export function WeekMenu() {
  const queryClient = useQueryClient();
  const [shoppingOpen, setShoppingOpen] = useState(false);
  const [sheet, setSheet] = useState<Sheet | null>(null);

  const plan = useQuery({ queryKey: ["meal-plan"], queryFn: () => api.mealPlan() });

  const receive = (data: MealPlan) => {
    queryClient.setQueryData(["meal-plan"], data);
    queryClient.invalidateQueries({ queryKey: ["nutrition-day"] });
  };

  const generate = useMutation({
    mutationFn: () => api.generateMealPlan(),
    onSuccess: receive,
  });

  const regenerate = useMutation({
    mutationFn: (slot: Slot) => api.regenerateMeal(slot.day, slot.meal),
    onSuccess: (data) => {
      receive(data);
      setSheet(null);
    },
  });

  const choose = useMutation({
    mutationFn: ({ slot, recipe }: { slot: Slot; recipe: Recipe }) =>
      api.setPlanMeal(slot.day, slot.meal, recipe.id),
    onSuccess: (data) => {
      receive(data);
      setSheet(null);
    },
  });

  const swap = useMutation({
    mutationFn: ({ a, b }: { a: Slot; b: Slot }) =>
      api.swapPlanMeals(
        { day_index: a.day, meal: a.meal },
        { day_index: b.day, meal: b.meal },
      ),
    onSuccess: (data) => {
      receive(data);
      setSheet(null);
    },
  });

  const away = useMutation({
    mutationFn: ({ slot, value }: { slot: Slot; value: boolean }) =>
      api.setPlanAway(slot.day, slot.meal, value),
    onSuccess: (data) => {
      receive(data);
      setSheet(null);
    },
  });

  const busy =
    regenerate.isPending || choose.isPending || swap.isPending || away.isPending;

  if (plan.isPending) {
    return <p className="px-5 text-[14px] text-mute">Lecture du menu…</p>;
  }

  const items = plan.data?.items ?? [];
  const empty = items.length === 0;

  return (
    <section className="px-5" aria-label="Menu de la semaine">
      {empty ? (
        <article className="rounded-card border border-line bg-card px-5 py-6">
          <h2 className="font-display text-[24px] font-semibold uppercase leading-none text-ink">
            Menu de la semaine
          </h2>
          <p className="mt-3 text-[15px] leading-snug text-ink-2">
            Sept déjeuners et sept dîners, tirés d&apos;une quarantaine de
            recettes simples, sous contrainte de calories, de protéines et de
            variété. Chaque plat se remplace, se déplace, ou se raye d&apos;un
            tap quand tu n&apos;es pas là.
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
      ) : (
        <>
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
              const kcal = dayMeals.reduce(
                (total, item) =>
                  total +
                  (item.status === "planned" ? (item.recipe?.kcal ?? 0) : 0) *
                    item.servings,
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
                    {PLANNED_MEALS.map((meal) => {
                      const item = dayMeals.find((entry) => entry.meal === meal);
                      const slot: Slot = { day: dayIndex, meal };
                      const isAway = item?.status === "away";
                      const recipe = isAway ? null : (item?.recipe ?? null);

                      return (
                        <li
                          key={meal}
                          className="flex items-center gap-2 border-b border-line px-3 py-2 last:border-0"
                        >
                          <span className="w-[74px] shrink-0 pl-1 text-[12px] font-semibold uppercase tracking-wide text-mute">
                            {MEAL_LABELS[meal]}
                          </span>

                          <button
                            type="button"
                            onClick={() =>
                              setSheet(
                                recipe
                                  ? { kind: "recipe", id: recipe.id, slot }
                                  : { kind: "actions", slot },
                              )
                            }
                            className="min-w-0 flex-1 text-left"
                          >
                            {isAway ? (
                              <span className="flex items-center gap-1.5 text-[15px] text-mute">
                                <IconAway className="h-4 w-4" />
                                Pas là
                              </span>
                            ) : recipe ? (
                              <>
                                <span className="block truncate text-[15px] text-ink">
                                  {recipe.name}
                                </span>
                                <span className="tabular flex items-center gap-1 text-[12px] text-mute">
                                  <IconClock className="h-3.5 w-3.5" />
                                  {recipe.prep_min} min
                                  {recipe.kcal !== null
                                    ? ` · ${num(recipe.kcal, 0)} kcal`
                                    : ""}
                                </span>
                              </>
                            ) : (
                              <span className="text-[15px] text-mute">À choisir</span>
                            )}
                          </button>

                          {!isAway ? (
                            <button
                              type="button"
                              onClick={() => regenerate.mutate(slot)}
                              disabled={busy}
                              aria-label={`Changer le ${MEAL_LABELS[meal].toLowerCase()} de ${label}`}
                              className="flex h-touch w-touch shrink-0 items-center justify-center rounded-button text-mute disabled:opacity-40"
                            >
                              <IconRefresh className="h-5 w-5" />
                            </button>
                          ) : null}

                          <button
                            type="button"
                            onClick={() => setSheet({ kind: "actions", slot })}
                            aria-label={`Options du ${MEAL_LABELS[meal].toLowerCase()} de ${label}`}
                            className="flex h-touch w-touch shrink-0 items-center justify-center rounded-button text-mute"
                          >
                            <IconMore className="h-5 w-5" />
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
              {(plan.data?.shopping ?? []).map((line) => {
                const hint = buyHint(line);
                return (
                  <li
                    key={line.label}
                    className="flex items-baseline justify-between gap-3 border-b border-line px-4 py-2 last:border-0"
                  >
                    <span className="min-w-0 flex-1 truncate text-[15px] text-ink">
                      {line.label}
                    </span>
                    <span className="tabular shrink-0 text-right text-[14px] font-semibold text-ink-2">
                      {buyQuantity(line)}
                      {hint ? (
                        <span className="block text-[11px] font-normal text-mute">
                          ≈ {hint}
                        </span>
                      ) : null}
                    </span>
                  </li>
                );
              })}
            </ul>
          ) : null}
        </>
      )}

      {/* ── Les feuilles ─────────────────────────────────────────────── */}

      {sheet?.kind === "actions" && plan.data ? (
        <SlotActions
          plan={plan.data}
          slot={sheet.slot}
          onClose={() => setSheet(null)}
          onOpenRecipe={(id) =>
            setSheet({ kind: "recipe", id, slot: sheet.slot })
          }
          onRegenerate={() => regenerate.mutate(sheet.slot)}
          onPick={() => setSheet({ kind: "pick", slot: sheet.slot })}
          onSwap={() => setSheet({ kind: "swap", slot: sheet.slot })}
          onAway={(value) => away.mutate({ slot: sheet.slot, value })}
        />
      ) : null}

      {sheet?.kind === "swap" && plan.data ? (
        <SwapPicker
          plan={plan.data}
          slot={sheet.slot}
          onClose={() => setSheet({ kind: "actions", slot: sheet.slot })}
          onSwap={(other) => swap.mutate({ a: sheet.slot, b: other })}
        />
      ) : null}

      {sheet?.kind === "pick" ? (
        <RecipePicker
          meal={sheet.slot.meal}
          onClose={() => setSheet({ kind: "actions", slot: sheet.slot })}
          onPick={(recipe) => choose.mutate({ slot: sheet.slot, recipe })}
        />
      ) : null}

      {sheet?.kind === "recipe" ? (
        <RecipeSheet
          recipeId={sheet.id}
          onClose={() => setSheet(null)}
          onReplaced={() => {
            // Une version perso a remplacé la recette du catalogue : le menu
            // de la semaine la suit, côté serveur. On relit plutôt que de
            // recoller l'état à la main.
            queryClient.invalidateQueries({ queryKey: ["meal-plan"] });
          }}
        />
      ) : null}
    </section>
  );
}
