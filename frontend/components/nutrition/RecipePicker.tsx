"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { IconBack, IconClock, IconStar } from "@/components/ui/Icons";
import { api } from "@/lib/api";
import { num } from "@/lib/format";
import { MEAL_LABELS, type PlannedMeal, type Recipe } from "@/lib/types";

/**
 * **Choisir un plat** pour un créneau, plein cadre.
 *
 * Le tirage propose, on dispose : c'est le pendant du bouton « un autre plat ».
 * Régénérer redonne la main à l'algorithme, choisir la lui retire.
 *
 * Les favorites sont en tête — c'est l'ordre dans lequel on cherche un plat de
 * remplacement : d'abord ce qu'on aime, ensuite le reste. Le filtre par repas
 * est un **défaut, pas une barrière** : on peut le lever et mettre des œufs
 * brouillés au dîner, parce que c'est un choix et pas une erreur.
 */
export function RecipePicker({
  meal,
  onPick,
  onClose,
}: {
  meal: PlannedMeal;
  onPick: (recipe: Recipe) => void;
  onClose: () => void;
}) {
  const [search, setSearch] = useState("");
  const [onlyThisMeal, setOnlyThisMeal] = useState(true);

  const recipes = useQuery({
    queryKey: ["recipes", onlyThisMeal ? meal : "all"],
    queryFn: () => api.recipes(onlyThisMeal ? { meal } : {}),
  });

  const needle = search.trim().toLowerCase();
  const shown = (recipes.data ?? []).filter(
    (recipe) => !needle || recipe.name.toLowerCase().includes(needle),
  );

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-bg">
      <header className="flex items-center gap-2 border-b border-line bg-card px-2 py-2">
        <button
          type="button"
          onClick={onClose}
          aria-label="Fermer"
          className="flex h-touch w-touch shrink-0 items-center justify-center rounded-button text-ink-2"
        >
          <IconBack className="h-5 w-5" />
        </button>
        <h2 className="min-w-0 flex-1 truncate font-display text-[19px] font-semibold uppercase leading-none text-ink">
          {MEAL_LABELS[meal]} — choisir
        </h2>
      </header>

      <div className="border-b border-line bg-card px-3 pb-3">
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Chercher une recette"
          className="min-h-touch w-full rounded-button border border-line bg-soft px-3 text-[16px] text-ink"
        />
        <button
          type="button"
          aria-pressed={!onlyThisMeal}
          onClick={() => setOnlyThisMeal((only) => !only)}
          className="mt-2 min-h-touch text-[13px] font-semibold text-mute"
        >
          {onlyThisMeal
            ? "Voir aussi les autres repas"
            : `Ne voir que les ${MEAL_LABELS[meal].toLowerCase()}s`}
        </button>
      </div>

      <ul className="min-h-0 flex-1 overflow-y-auto">
        {recipes.isPending ? (
          <li className="px-5 py-4 text-[14px] text-mute">Chargement…</li>
        ) : shown.length === 0 ? (
          <li className="px-5 py-4 text-[14px] text-ink-2">
            Rien sous ce nom. Tu peux écrire ta propre recette depuis la
            bibliothèque.
          </li>
        ) : (
          shown.map((recipe) => (
            <li key={recipe.id} className="border-b border-line">
              <button
                type="button"
                onClick={() => onPick(recipe)}
                className="flex min-h-touch w-full items-center gap-3 px-5 py-2 text-left"
              >
                {recipe.favorite ? (
                  <IconStar className="h-4 w-4 shrink-0 text-accent" filled />
                ) : null}
                <span className="min-w-0 flex-1">
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
                </span>
              </button>
            </li>
          ))
        )}
      </ul>
    </div>
  );
}
