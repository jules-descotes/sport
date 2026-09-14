"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { IconMinus, IconPlus, IconTrash } from "@/components/ui/Icons";
import { api } from "@/lib/api";
import { MEALS, MEAL_LABELS, type Meal, type Recipe } from "@/lib/types";

/**
 * **Écrire ou corriger une recette.**
 *
 * Trois règles portent ce formulaire, et aucune n'est cosmétique.
 *
 * 1. **Aucune valeur nutritionnelle ne se saisit.** Il n'y a pas de champ
 *    « kcal », et il n'y en aura pas : les macros se déduisent des ingrédients
 *    et de la table Ciqual, côté serveur. Une recette annoncée « à 450 kcal »
 *    par son auteur serait une estimation qu'on prendrait pour une mesure dès
 *    le lendemain.
 * 2. **Les quantités sont en grammes**, et elles se règlent au pas plutôt
 *    qu'au clavier. Le clavier ne sert qu'aux noms — le nom de la recette, le
 *    nom d'un ingrédient, les étapes.
 * 3. **Modifier une recette du catalogue la dédouble.** C'est le serveur qui
 *    s'en charge ; l'écran le dit avant, parce qu'une copie silencieuse se
 *    découvre en retrouvant deux fois le même plat dans la bibliothèque.
 */

/** Le pas d'un ingrédient, par palier. Fin en dessous de 100 g (une cuillère
 *  d'huile, 20 g de parmesan), large au-dessus (une portion de riz). */
function step(grams: number): number {
  if (grams < 50) return 5;
  if (grams < 200) return 10;
  return 25;
}

interface Draft {
  label: string;
  quantity_g: number;
}

export function RecipeEditor({
  recipe,
  onSaved,
  onCancel,
}: {
  /** Absente = création. Présente = modification (fork si elle vient du
   *  catalogue). */
  recipe?: Recipe;
  onSaved: (recipe: Recipe) => void;
  onCancel: () => void;
}) {
  const queryClient = useQueryClient();

  const [name, setName] = useState(recipe?.name ?? "");
  const [prepMin, setPrepMin] = useState(recipe?.prep_min ?? 15);
  const [servings, setServings] = useState(recipe?.servings ?? 1);
  const [meals, setMeals] = useState<Meal[]>(recipe?.meals ?? ["dinner"]);
  const [steps, setSteps] = useState(recipe?.steps ?? "");
  const [items, setItems] = useState<Draft[]>(
    recipe?.items.map((item) => ({
      label: item.label,
      quantity_g: item.quantity_g,
    })) ?? [{ label: "", quantity_g: 100 }],
  );

  const save = useMutation({
    mutationFn: () => {
      const payload = {
        name: name.trim(),
        meals,
        servings,
        prep_min: prepMin,
        steps: steps.trim() || null,
        items: items
          .filter((item) => item.label.trim())
          .map((item) => ({
            label: item.label.trim(),
            quantity_g: item.quantity_g,
          })),
      };
      return recipe
        ? api.updateRecipe(recipe.id, payload)
        : api.createRecipe(payload);
    },
    onSuccess: (saved) => {
      // Le menu et la bibliothèque changent tous les deux : une version perso
      // remplace l'originale dans la semaine en cours.
      queryClient.invalidateQueries({ queryKey: ["recipes"] });
      queryClient.invalidateQueries({ queryKey: ["meal-plan"] });
      queryClient.invalidateQueries({ queryKey: ["nutrition-day"] });
      onSaved(saved);
    },
  });

  const usable = name.trim() !== "" && items.some((item) => item.label.trim());

  const update = (index: number, patch: Partial<Draft>) =>
    setItems((current) =>
      current.map((item, position) =>
        position === index ? { ...item, ...patch } : item,
      ),
    );

  return (
    <form
      className="flex flex-col gap-5"
      onSubmit={(event) => {
        event.preventDefault();
        if (usable) save.mutate();
      }}
    >
      {recipe && recipe.source === "catalog" ? (
        <p className="rounded-card border border-line bg-soft px-4 py-3 text-[13px] leading-snug text-ink-2">
          Cette recette vient du catalogue. La modifier en enregistre{" "}
          <strong className="font-semibold">ta version</strong>, à part :
          l&apos;originale reste disponible, et le catalogue ne réécrira jamais
          la tienne.
        </p>
      ) : null}

      <label className="block">
        <span className="block pb-1 text-[12px] font-semibold uppercase tracking-wide text-mute">
          Nom
        </span>
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Riz poulet brocoli"
          className="min-h-touch w-full rounded-button border border-line bg-card px-3 text-[16px] text-ink"
        />
      </label>

      <div className="flex gap-3">
        <Stepper
          label="Préparation"
          value={prepMin}
          suffix="min"
          onChange={(next) => setPrepMin(Math.max(0, Math.min(240, next)))}
          step={5}
        />
        <Stepper
          label="Portions"
          value={servings}
          suffix={servings > 1 ? "parts" : "part"}
          onChange={(next) => setServings(Math.max(1, Math.min(12, next)))}
          step={1}
        />
      </div>

      <div>
        <span className="block pb-2 text-[12px] font-semibold uppercase tracking-wide text-mute">
          À quels repas
        </span>
        <div className="flex flex-wrap gap-2">
          {MEALS.map((meal) => {
            const on = meals.includes(meal);
            return (
              <button
                key={meal}
                type="button"
                aria-pressed={on}
                onClick={() =>
                  setMeals((current) =>
                    current.includes(meal)
                      ? current.filter((item) => item !== meal)
                      : [...current, meal],
                  )
                }
                className={`min-h-touch rounded-pill border px-4 text-[14px] font-semibold ${
                  on
                    ? "border-accent bg-accent text-on-accent"
                    : "border-line bg-card text-ink-2"
                }`}
              >
                {MEAL_LABELS[meal]}
              </button>
            );
          })}
        </div>
      </div>

      <div>
        <span className="block pb-2 text-[12px] font-semibold uppercase tracking-wide text-mute">
          Ingrédients
        </span>
        <ul className="flex flex-col gap-2">
          {items.map((item, index) => (
            <li
              key={index}
              className="flex items-center gap-2 rounded-card border border-line bg-card px-2 py-2"
            >
              <input
                value={item.label}
                onChange={(event) => update(index, { label: event.target.value })}
                placeholder="Riz blanc cuit"
                className="min-h-touch min-w-0 flex-1 rounded-button bg-soft px-3 text-[15px] text-ink"
              />
              <button
                type="button"
                aria-label={`Moins de ${item.label || "cet ingrédient"}`}
                onClick={() =>
                  update(index, {
                    quantity_g: Math.max(
                      5,
                      item.quantity_g - step(item.quantity_g),
                    ),
                  })
                }
                className="flex h-touch w-9 shrink-0 items-center justify-center rounded-button text-mute"
              >
                <IconMinus className="h-4 w-4" />
              </button>
              <span className="tabular w-[58px] shrink-0 text-center text-[14px] font-semibold text-ink">
                {Math.round(item.quantity_g)} g
              </span>
              <button
                type="button"
                aria-label={`Plus de ${item.label || "cet ingrédient"}`}
                onClick={() =>
                  update(index, {
                    quantity_g: Math.min(
                      5000,
                      item.quantity_g + step(item.quantity_g),
                    ),
                  })
                }
                className="flex h-touch w-9 shrink-0 items-center justify-center rounded-button text-mute"
              >
                <IconPlus className="h-4 w-4" />
              </button>
              <button
                type="button"
                aria-label={`Retirer ${item.label || "cet ingrédient"}`}
                onClick={() =>
                  setItems((current) =>
                    current.filter((_, position) => position !== index),
                  )
                }
                className="flex h-touch w-9 shrink-0 items-center justify-center rounded-button text-mute"
              >
                <IconTrash className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
        <button
          type="button"
          onClick={() =>
            setItems((current) => [...current, { label: "", quantity_g: 100 }])
          }
          className="mt-2 flex min-h-touch w-full items-center justify-center gap-2 rounded-button border border-line bg-card text-[15px] font-semibold text-ink-2"
        >
          <IconPlus className="h-4 w-4" />
          Ajouter un ingrédient
        </button>
      </div>

      <label className="block">
        <span className="block pb-1 text-[12px] font-semibold uppercase tracking-wide text-mute">
          Comment on la fait
        </span>
        <textarea
          value={steps}
          onChange={(event) => setSteps(event.target.value)}
          rows={3}
          placeholder="Riz à l'eau, poulet à la poêle, brocoli vapeur huit minutes."
          className="w-full rounded-button border border-line bg-card px-3 py-2 text-[15px] leading-snug text-ink"
        />
      </label>

      {save.isError ? (
        <p className="text-[13px] text-ink-2">
          Impossible d&apos;enregistrer. Réessaie quand le réseau revient.
        </p>
      ) : null}

      <div className="flex gap-3">
        <button
          type="button"
          onClick={onCancel}
          className="min-h-touch flex-1 rounded-button border border-line bg-card text-[15px] font-semibold text-ink-2"
        >
          Annuler
        </button>
        <button
          type="submit"
          disabled={!usable || save.isPending}
          className="min-h-touch flex-[2] rounded-button bg-accent text-[16px] font-semibold text-on-accent disabled:opacity-40"
        >
          {save.isPending ? "Enregistrement…" : "Enregistrer"}
        </button>
      </div>
    </form>
  );
}

function Stepper({
  label,
  value,
  suffix,
  step: increment,
  onChange,
}: {
  label: string;
  value: number;
  suffix: string;
  step: number;
  onChange: (next: number) => void;
}) {
  return (
    <div className="flex-1">
      <span className="block pb-1 text-[12px] font-semibold uppercase tracking-wide text-mute">
        {label}
      </span>
      <div className="flex items-center rounded-button border border-line bg-card">
        <button
          type="button"
          aria-label={`Moins — ${label}`}
          onClick={() => onChange(value - increment)}
          className="flex h-touch w-touch shrink-0 items-center justify-center text-mute"
        >
          <IconMinus className="h-4 w-4" />
        </button>
        <span className="tabular min-w-0 flex-1 text-center text-[15px] font-semibold text-ink">
          {value} {suffix}
        </span>
        <button
          type="button"
          aria-label={`Plus — ${label}`}
          onClick={() => onChange(value + increment)}
          className="flex h-touch w-touch shrink-0 items-center justify-center text-mute"
        >
          <IconPlus className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
