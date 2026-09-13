"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { DayGauges, TargetBreakdown } from "@/components/nutrition/DayGauges";
import { FoodSearch } from "@/components/nutrition/FoodSearch";
import { WeekMenu } from "@/components/nutrition/WeekMenu";
import { WeighIn } from "@/components/nutrition/WeighIn";
import { ScreenHeader } from "@/components/shell/ScreenHeader";
import { IconChevronDown, IconTrash } from "@/components/ui/Icons";
import { api } from "@/lib/api";
import { num } from "@/lib/format";
import { MEALS, MEAL_LABELS, type Meal } from "@/lib/types";

/**
 * **Nutrition** — la cible du jour, le journal, le menu, la pesée.
 *
 * Rendu plein cadre (V4 de `docs/DESIGN-EXPLORATION.md`), dans l'ordre de ce
 * qu'on vient y chercher : *combien il me reste*, *qu'est-ce que j'ai mangé*,
 * *qu'est-ce que je mange ce soir*, *où j'en suis*.
 *
 * **Le ton est neutre, et jamais rouge.** Un journal alimentaire qui gronde est
 * un journal qu'on cesse d'ouvrir, et un journal fermé ne recalibre plus rien —
 * or la calibration est ce qui rend la cible honnête. Le dépassement se voit,
 * il ne s'accuse pas.
 *
 * **Desktop** : cible et journal à gauche, menu de la semaine à droite. Les
 * deux se lisent ensemble — « il me reste 700 kcal, le dîner prévu en fait
 * 650 ».
 */
export default function NutritionPage() {
  const queryClient = useQueryClient();
  const [detailOpen, setDetailOpen] = useState(false);

  const day = useQuery({
    queryKey: ["nutrition-day"],
    queryFn: () => api.nutritionDay(),
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.deleteFoodLog(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["nutrition-day"] });
    },
  });

  if (day.isPending) {
    return (
      <>
        <ScreenHeader title="Nutrition" />
        <p className="px-5 text-[14px] text-mute">Chargement…</p>
      </>
    );
  }

  if (day.error || !day.data) {
    return (
      <>
        <ScreenHeader title="Nutrition" />
        <p className="mx-5 rounded-card border border-line bg-card px-5 py-6 text-[14px] text-ink-2">
          Nutrition indisponible. Réessaie quand le réseau revient.
        </p>
      </>
    );
  }

  const { target, totals, entries, planned } = day.data;

  return (
    <main className="pb-8">
      <ScreenHeader
        title="Nutrition"
        subtitle="Ta cible du jour, ce que tu as mangé, et ce qui est prévu."
      />

      <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:items-start lg:gap-0">
        {/* ── Où j'en suis ────────────────────────────────────────────── */}
        <div>
          <section className="px-5" aria-label="Cible du jour">
            <article className="rounded-card border border-line bg-card px-5 py-5">
              <DayGauges target={target} totals={totals} />

              <button
                type="button"
                onClick={() => setDetailOpen((open) => !open)}
                aria-expanded={detailOpen}
                className="flex min-h-touch w-full items-center justify-between gap-3 pt-1 text-left"
              >
                <span className="text-[13px] font-semibold text-mute">
                  D&apos;où vient cette cible
                </span>
                <IconChevronDown
                  className={`h-5 w-5 shrink-0 text-mute transition-transform ${
                    detailOpen ? "rotate-180" : ""
                  }`}
                />
              </button>

              {detailOpen ? <TargetBreakdown target={target} /> : null}
            </article>
          </section>

          {/* ── Le journal ────────────────────────────────────────────── */}
          <section className="px-5 pt-5" aria-label="Journal du jour">
            <h2 className="pb-2 text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
              Aujourd&apos;hui
            </h2>

            {entries.length === 0 ? (
              <p className="rounded-card border border-line bg-card px-4 py-3 text-[14px] leading-snug text-ink-2">
                Rien de noté. Un repas se saisit en vingt secondes : ce que tu
                manges souvent arrive en tête de la recherche.
              </p>
            ) : (
              <div className="flex flex-col gap-3">
                {MEALS.map((meal) => {
                  const lines = entries.filter((entry) => entry.meal === meal);
                  if (lines.length === 0) return null;
                  const kcal = lines.reduce(
                    (total, line) => total + (line.kcal ?? 0),
                    0,
                  );
                  return (
                    <article
                      key={meal}
                      className="overflow-hidden rounded-card border border-line bg-card"
                    >
                      <header className="flex items-baseline justify-between gap-3 border-b border-line bg-soft px-4 py-2">
                        <h3 className="text-[12px] font-semibold uppercase tracking-wide text-ink-2">
                          {MEAL_LABELS[meal as Meal]}
                        </h3>
                        <span className="tabular text-[12px] text-mute">
                          {num(kcal, 0)} kcal
                        </span>
                      </header>
                      <ul>
                        {lines.map((line) => (
                          <li
                            key={line.id}
                            className="flex items-center gap-3 border-b border-line px-4 py-2 last:border-0"
                          >
                            <span className="min-w-0 flex-1">
                              <span className="block truncate text-[15px] text-ink">
                                {line.label}
                              </span>
                              <span className="tabular block text-[12px] text-mute">
                                {num(line.quantity_g, 0)} g ·{" "}
                                {num(line.kcal, 0)} kcal ·{" "}
                                {num(line.protein_g)} g P
                              </span>
                            </span>
                            <button
                              type="button"
                              onClick={() => remove.mutate(line.id)}
                              aria-label={`Retirer ${line.label}`}
                              className="flex h-touch w-touch shrink-0 items-center justify-center rounded-button text-mute"
                            >
                              <IconTrash className="h-5 w-5" />
                            </button>
                          </li>
                        ))}
                      </ul>
                    </article>
                  );
                })}
              </div>
            )}

            <div className="pt-3">
              <FoodSearch day={day.data.day} />
            </div>
          </section>

          <div className="pt-5">
            <WeighIn />
          </div>
        </div>

        {/* ── Ce qui est prévu ────────────────────────────────────────── */}
        <div className="pt-5 lg:pt-0">
          {planned.length > 0 ? (
            <section className="px-5 pb-5" aria-label="Prévu aujourd'hui">
              <h2 className="pb-2 text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
                Prévu aujourd&apos;hui
              </h2>
              <ul className="overflow-hidden rounded-card border border-line bg-card">
                {planned.map((item) => (
                  <li
                    key={item.meal}
                    className="flex items-center gap-3 border-b border-line px-4 py-2 last:border-0"
                  >
                    <span className="w-[74px] shrink-0 text-[12px] font-semibold uppercase tracking-wide text-mute">
                      {MEAL_LABELS[item.meal]}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-[15px] text-ink">
                      {item.recipe.name}
                    </span>
                    {item.recipe.kcal !== null ? (
                      <span className="tabular shrink-0 text-[13px] text-mute">
                        {num(item.recipe.kcal, 0)} kcal
                      </span>
                    ) : null}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <WeekMenu />
        </div>
      </div>
    </main>
  );
}
