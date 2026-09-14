"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { DayGauges } from "@/components/nutrition/DayGauges";
import { FoodSearch } from "@/components/nutrition/FoodSearch";
import { IconChevronRight } from "@/components/ui/Icons";
import { api } from "@/lib/api";
import { num } from "@/lib/format";
import { MEAL_LABELS } from "@/lib/types";

/**
 * **Les repas, sur l'écran Jour** — la jauge, le prochain plat prévu, un tap
 * pour saisir.
 *
 * Jour est « la journée dans l'ordre où elle se vit » : la mer, la séance, les
 * repas, la pesée. Ce bloc est la troisième ligne, et il tient en trois
 * informations — combien il reste, ce qui est prévu, et le bouton qui ouvre la
 * saisie. Le détail, le journal complet et le menu de la semaine vivent sur
 * l'onglet Nutrition.
 *
 * La saisie est **ici** et pas seulement là-bas parce qu'un repas se note au
 * moment où on le mange, pas au moment où on ouvre le bon onglet.
 */
export function DayMealBlock() {
  const day = useQuery({
    queryKey: ["nutrition-day"],
    queryFn: () => api.nutritionDay(),
  });

  if (day.isPending || !day.data) {
    return (
      <div className="rounded-card border border-line bg-card px-4 py-3">
        <p className="text-[13px] text-mute">Repas…</p>
      </div>
    );
  }

  const { target, totals, planned, entries } = day.data;
  // Le prochain repas prévu qui n'a pas encore été noté : c'est celui qu'on
  // regarde. Les créneaux « pas là » sont sautés — annoncer un dîner qu'on
  // prend ailleurs serait pire que de ne rien annoncer.
  const logged = new Set(entries.map((entry) => entry.meal));
  const next = planned.find(
    (item) => !logged.has(item.meal) && item.status === "planned" && item.recipe,
  );

  return (
    <div className="overflow-hidden rounded-card border border-line bg-card">
      <div className="px-4 pt-3">
        <DayGauges compact target={target} totals={totals} />
      </div>

      {next ? (
        <p className="tabular px-4 pt-2 text-[13px] text-ink-2">
          <span className="font-semibold uppercase tracking-wide text-mute">
            {MEAL_LABELS[next.meal]}
          </span>{" "}
          {next.recipe?.name}
          {next.recipe?.kcal !== null && next.recipe?.kcal !== undefined
            ? ` · ${num(next.recipe.kcal, 0)} kcal`
            : ""}
        </p>
      ) : null}

      <div className="px-4 py-3">
        <FoodSearch day={day.data.day} />
      </div>

      <Link
        href="/nutrition"
        className="flex min-h-touch items-center justify-between gap-3 border-t border-line px-4 text-[14px] font-semibold text-ink-2"
      >
        Le journal et le menu
        <IconChevronRight className="h-4 w-4 shrink-0 text-mute" />
      </Link>
    </div>
  );
}
