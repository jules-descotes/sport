"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { RecipeEditor } from "@/components/nutrition/RecipeEditor";
import { RecipeSheet } from "@/components/nutrition/RecipeSheet";
import { IconBack, IconClock, IconPlus, IconStar } from "@/components/ui/Icons";
import { api } from "@/lib/api";
import { num } from "@/lib/format";

/**
 * **La bibliothèque de recettes** — les siennes en premier.
 *
 * Le menu de la semaine sait proposer ; il ne sait pas se souvenir de ce qu'on
 * a pensé d'un plat. C'est ici que ça vit : l'étoile, la note libre, et les
 * recettes qu'on écrit soi-même.
 *
 * **Le catalogue est commun et l'app le réécrit** à chaque semis — c'est ce qui
 * lui permet de se corriger et de récupérer ses macros après un import Ciqual.
 * Une version perso est une ligne à part, que le semis ne touche jamais. D'où
 * l'étiquette « ta version » : deux plats du même nom dans la liste ne sont pas
 * un doublon, c'est l'original et le tien.
 *
 * Trois filtres suffisent, et il n'y en aura pas de quatrième : tout, les
 * favorites, les tiennes. Une bibliothèque de quarante recettes ne se range
 * pas, elle se parcourt.
 */

type Filter = "all" | "favorite" | "mine";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "Toutes" },
  { key: "favorite", label: "Favorites" },
  { key: "mine", label: "Les miennes" },
];

export default function RecipeLibraryPage() {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [openId, setOpenId] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);

  const recipes = useQuery({
    queryKey: ["recipes", "library"],
    queryFn: () => api.recipes(),
  });

  const needle = search.trim().toLowerCase();
  const shown = (recipes.data ?? []).filter((recipe) => {
    if (needle && !recipe.name.toLowerCase().includes(needle)) return false;
    if (filter === "favorite") return recipe.favorite;
    if (filter === "mine") return recipe.source === "user";
    return true;
  });

  return (
    <main className="pb-8">
      <header className="flex items-center gap-3 px-5 pb-1 pt-4">
        <Link
          href="/nutrition"
          aria-label="Retour à Nutrition"
          className="-ml-2 flex h-touch w-touch shrink-0 items-center justify-center rounded-button text-ink-2"
        >
          <IconBack className="h-5 w-5" />
        </Link>
        <p className="text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
          Nutrition
        </p>
      </header>

      <section className="px-5 pb-5">
        <h1 className="font-display text-[32px] font-bold uppercase leading-none tracking-tight text-ink">
          Mes recettes
        </h1>
        <p className="mt-2 text-[14px] text-ink-2">
          Ce que tu aimes, ce que tu as noté, ce que tu as écrit.
        </p>
      </section>

      <div className="mx-auto max-w-[900px] px-5">
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Chercher une recette"
          className="min-h-touch w-full rounded-button border border-line bg-card px-3 text-[16px] text-ink"
        />

        <div className="flex flex-wrap gap-2 py-3">
          {FILTERS.map((item) => (
            <button
              key={item.key}
              type="button"
              aria-pressed={filter === item.key}
              onClick={() => setFilter(item.key)}
              className={`min-h-touch rounded-pill border px-4 text-[14px] font-semibold ${
                filter === item.key
                  ? "border-accent bg-accent text-on-accent"
                  : "border-line bg-card text-ink-2"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>

        {creating ? (
          <section className="rounded-card border border-line bg-card px-4 py-4">
            <h2 className="pb-3 font-display text-[20px] font-semibold uppercase leading-none text-ink">
              Nouvelle recette
            </h2>
            <RecipeEditor
              onCancel={() => setCreating(false)}
              onSaved={(saved) => {
                setCreating(false);
                setOpenId(saved.id);
              }}
            />
          </section>
        ) : (
          <button
            type="button"
            onClick={() => setCreating(true)}
            className="flex min-h-touch w-full items-center justify-center gap-2 rounded-button border border-line bg-card text-[15px] font-semibold text-ink-2"
          >
            <IconPlus className="h-4 w-4" />
            Écrire une recette
          </button>
        )}

        {recipes.isPending ? (
          <p className="pt-4 text-[14px] text-mute">Chargement…</p>
        ) : shown.length === 0 ? (
          <p className="mt-4 rounded-card border border-line bg-card px-4 py-3 text-[14px] leading-snug text-ink-2">
            {filter === "favorite"
              ? "Aucune favorite pour l'instant. L'étoile est sur la fiche d'une recette."
              : filter === "mine"
                ? "Tu n'as pas encore écrit de recette. Modifier une recette du catalogue en crée une aussi."
                : "Rien sous ce nom."}
          </p>
        ) : (
          <ul className="mt-4 overflow-hidden rounded-card border border-line bg-card">
            {shown.map((recipe) => (
              <li key={recipe.id} className="border-b border-line last:border-0">
                <button
                  type="button"
                  onClick={() => setOpenId(recipe.id)}
                  className="flex min-h-touch w-full items-center gap-3 px-4 py-2 text-left"
                >
                  {recipe.favorite ? (
                    <IconStar className="h-4 w-4 shrink-0 text-accent" filled />
                  ) : null}
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2">
                      <span className="min-w-0 truncate text-[15px] text-ink">
                        {recipe.name}
                      </span>
                      {recipe.source === "user" ? (
                        <span className="shrink-0 rounded-pill border border-accent px-2 text-[11px] font-semibold text-accent">
                          ta version
                        </span>
                      ) : null}
                    </span>
                    <span className="tabular flex items-center gap-1 text-[12px] text-mute">
                      <IconClock className="h-3.5 w-3.5" />
                      {recipe.prep_min} min
                      {recipe.kcal !== null
                        ? ` · ${num(recipe.kcal, 0)} kcal`
                        : ""}
                      {recipe.note ? " · notée" : ""}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {openId !== null ? (
        <RecipeSheet recipeId={openId} onClose={() => setOpenId(null)} />
      ) : null}
    </main>
  );
}
