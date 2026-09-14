"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { RecipeEditor } from "@/components/nutrition/RecipeEditor";
import {
  IconBack,
  IconClock,
  IconPencil,
  IconStar,
  IconTrash,
} from "@/components/ui/Icons";
import { api } from "@/lib/api";
import { num } from "@/lib/format";
import { buyHint, buyQuantity } from "@/lib/shopping";
import { MEAL_LABELS, type Recipe } from "@/lib/types";

/**
 * **La fiche d'une recette**, plein cadre.
 *
 * C'est ce qui manquait au menu : un nom de plat ne dit pas comment on le
 * fait. La fiche porte les ingrédients dans l'unité où on les achète (deux
 * œufs, pas 110 g), les étapes, les macros par portion — et surtout les deux
 * choses qui la rendent **sienne** : l'étoile et la note libre.
 *
 * La note est le seul champ de texte libre de l'écran Nutrition, et c'est
 * assumé : « sans le piment c'est meilleur », « cuire le riz deux minutes de
 * plus ». C'est ce qui transforme une banque de recettes générique en carnet
 * de cuisine, et c'est exactement ce qu'un semis ne doit jamais pouvoir
 * effacer — d'où sa table à part, côté serveur.
 *
 * Modifier une recette du catalogue **la dédouble**. L'écran le dit avant, pas
 * après : une copie silencieuse se découvre en retrouvant deux fois le même
 * plat dans la bibliothèque, des semaines plus tard.
 */
export function RecipeSheet({
  recipeId,
  onClose,
  onReplaced,
}: {
  recipeId: number;
  onClose: () => void;
  /** Appelé quand la modification a créé une version perso : le menu doit
   *  suivre, et l'écran qui nous a ouverts doit connaître le nouvel identifiant. */
  onReplaced?: (recipe: Recipe) => void;
}) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  // Le brouillon de la note porte **l'identifiant de la recette qu'il décrit**.
  // Sans lui, il faudrait un effet pour recharger le champ quand la fiche
  // change, et un effet qui écrit dans l'état écrase ce qu'on est en train de
  // taper. Ici, tant que l'identifiant colle, c'est le brouillon qui gagne ;
  // sinon on retombe sur la note du serveur, sans rien synchroniser.
  const [draft, setDraft] = useState<{ id: number; text: string } | null>(null);
  // Modifier une recette du catalogue en crée une copie perso, avec un autre
  // identifiant. La fiche **bascule dessus** : rester sur l'originale
  // afficherait la version qu'on vient justement de ne pas garder, et on
  // relirait trois fois l'écran en se demandant où est passée la correction.
  const [forkedId, setForkedId] = useState<number | null>(null);
  const id = forkedId ?? recipeId;

  const recipe = useQuery({
    queryKey: ["recipe", id],
    queryFn: () => api.recipe(id),
  });

  const note = draft && draft.id === id ? draft.text : (recipe.data?.note ?? "");
  const setNote = (text: string) => setDraft({ id, text });

  const invalidate = (saved: Recipe) => {
    queryClient.setQueryData(["recipe", saved.id], saved);
    queryClient.invalidateQueries({ queryKey: ["recipes"] });
    queryClient.invalidateQueries({ queryKey: ["meal-plan"] });
  };

  const setNoteOnServer = useMutation({
    mutationFn: (data: { favorite?: boolean; note?: string }) =>
      api.setRecipeNote(id, data),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: () => api.deleteRecipe(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["recipes"] });
      queryClient.invalidateQueries({ queryKey: ["meal-plan"] });
      queryClient.invalidateQueries({ queryKey: ["nutrition-day"] });
      onClose();
    },
  });

  const data = recipe.data;

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-bg">
      <header className="flex items-center gap-2 border-b border-line bg-card px-2 py-2">
        <button
          type="button"
          onClick={onClose}
          aria-label="Fermer la recette"
          className="flex h-touch w-touch shrink-0 items-center justify-center rounded-button text-ink-2"
        >
          <IconBack className="h-5 w-5" />
        </button>
        <h2 className="min-w-0 flex-1 truncate font-display text-[19px] font-semibold uppercase leading-none text-ink">
          {data?.name ?? "Recette"}
        </h2>
        {data ? (
          <button
            type="button"
            aria-pressed={data.favorite}
            aria-label={data.favorite ? "Retirer des favorites" : "Mettre en favorite"}
            onClick={() =>
              setNoteOnServer.mutate({ favorite: !data.favorite })
            }
            className={`flex h-touch w-touch shrink-0 items-center justify-center rounded-button ${
              data.favorite ? "text-accent" : "text-mute"
            }`}
          >
            <IconStar className="h-5 w-5" filled={data.favorite} />
          </button>
        ) : null}
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        {!data ? (
          <p className="text-[14px] text-mute">Lecture de la recette…</p>
        ) : editing ? (
          <RecipeEditor
            recipe={data}
            onCancel={() => setEditing(false)}
            onSaved={(saved) => {
              setEditing(false);
              // Le brouillon de note appartenait à la recette d'avant : une
              // version perso repart de la note qu'elle a héritée.
              setDraft(null);
              if (saved.id !== data.id) {
                setForkedId(saved.id);
                onReplaced?.(saved);
              }
            }}
          />
        ) : (
          <div className="mx-auto flex max-w-[720px] flex-col gap-5">
            {/* Ce qu'on veut savoir avant de se lancer : combien de temps,
                combien ça pèse dans la journée. */}
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] text-ink-2">
              <span className="tabular flex items-center gap-1">
                <IconClock className="h-4 w-4 text-mute" />
                {data.prep_min} min
              </span>
              {data.kcal !== null ? (
                <span className="tabular">
                  {num(data.kcal, 0)} kcal · {num(data.protein_g)} g P ·{" "}
                  {num(data.carb_g)} g G · {num(data.fat_g)} g L
                </span>
              ) : (
                <span className="text-mute">
                  Macros inconnues tant que la table Ciqual n&apos;est pas
                  importée.
                </span>
              )}
              {data.servings > 1 ? (
                <span className="tabular text-mute">
                  {data.servings} parts
                </span>
              ) : null}
            </div>

            <div className="flex flex-wrap gap-2">
              {data.meals.map((meal) => (
                <span
                  key={meal}
                  className="rounded-pill border border-line bg-soft px-3 py-1 text-[12px] font-semibold uppercase tracking-wide text-ink-2"
                >
                  {MEAL_LABELS[meal]}
                </span>
              ))}
              {data.tags.map((tag) => (
                <span
                  key={tag}
                  className="rounded-pill border border-line bg-card px-3 py-1 text-[12px] text-mute"
                >
                  {tag}
                </span>
              ))}
              {data.source === "user" ? (
                <span className="rounded-pill border border-accent px-3 py-1 text-[12px] font-semibold text-accent">
                  ta version
                </span>
              ) : null}
            </div>

            <section>
              <h3 className="pb-2 text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
                Ingrédients
              </h3>
              <ul className="overflow-hidden rounded-card border border-line bg-card">
                {data.items.map((item, index) => {
                  const hint = buyHint(item);
                  return (
                    <li
                      key={`${item.label}-${index}`}
                      className="flex items-baseline justify-between gap-3 border-b border-line px-4 py-2 last:border-0"
                    >
                      <span className="min-w-0 flex-1 text-[15px] text-ink">
                        {item.label}
                      </span>
                      <span className="tabular shrink-0 text-right text-[14px] font-semibold text-ink-2">
                        {buyQuantity(item)}
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
            </section>

            {data.steps ? (
              <section>
                <h3 className="pb-2 text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
                  Comment on la fait
                </h3>
                <p className="whitespace-pre-line rounded-card border border-line bg-card px-4 py-3 text-[15px] leading-relaxed text-ink">
                  {data.steps}
                </p>
              </section>
            ) : null}

            <section>
              <h3 className="pb-2 text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
                Ta note
              </h3>
              <textarea
                value={note}
                onChange={(event) => setNote(event.target.value)}
                rows={3}
                placeholder="Sans le piment c'est meilleur."
                className="w-full rounded-card border border-line bg-card px-4 py-3 text-[15px] leading-snug text-ink"
              />
              {note !== (data.note ?? "") ? (
                <button
                  type="button"
                  onClick={() => setNoteOnServer.mutate({ note })}
                  disabled={setNoteOnServer.isPending}
                  className="mt-2 flex min-h-touch w-full items-center justify-center rounded-button bg-accent text-[15px] font-semibold text-on-accent disabled:opacity-50"
                >
                  {setNoteOnServer.isPending ? "Enregistrement…" : "Enregistrer la note"}
                </button>
              ) : null}
              {data.cooked_count > 0 ? (
                <p className="tabular pt-2 text-[12px] text-mute">
                  Cuisinée {data.cooked_count} fois.
                </p>
              ) : null}
            </section>

            <div className="flex gap-3 pb-4">
              <button
                type="button"
                onClick={() => setEditing(true)}
                className="flex min-h-touch flex-1 items-center justify-center gap-2 rounded-button border border-line bg-card text-[15px] font-semibold text-ink-2"
              >
                <IconPencil className="h-4 w-4" />
                Modifier
              </button>
              {data.source === "user" ? (
                <button
                  type="button"
                  onClick={() => remove.mutate()}
                  disabled={remove.isPending}
                  aria-label="Supprimer cette recette"
                  className="flex h-touch w-touch shrink-0 items-center justify-center rounded-button border border-line bg-card text-mute disabled:opacity-50"
                >
                  <IconTrash className="h-5 w-5" />
                </button>
              ) : null}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
