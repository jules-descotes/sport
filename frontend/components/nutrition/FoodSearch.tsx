"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { IconBarcode, IconCheck, IconSearch } from "@/components/ui/Icons";
import { api } from "@/lib/api";
import { num } from "@/lib/format";
import { MEALS, MEAL_LABELS, type Food, type Meal } from "@/lib/types";
import { useBarcodeScanner } from "@/lib/useBarcodeScanner";

/**
 * **Un repas en vingt secondes.**
 *
 * C'est la seule contrainte qui compte ici, et elle vient tout droit de la
 * leçon du lot 2 : le risque du projet est la friction de saisie, pas la
 * rareté des données. Un journal alimentaire qui demande une minute par repas
 * est abandonné en trois semaines, et un journal abandonné ne recalibre plus
 * rien.
 *
 * D'où trois partis pris :
 *
 * 1. **L'écran s'ouvre sur ce qu'on mange.** Sans rien taper, ce sont les
 *    vingt aliments les plus journalisés qui s'affichent — neuf fois sur dix,
 *    ce qu'on cherche y est déjà, et le clavier ne s'ouvre jamais.
 * 2. **La quantité est en pastilles**, avec les portions courantes de
 *    l'aliment. Un pavé numérique recouvre la moitié de l'écran pour saisir un
 *    nombre qu'on connaît de toute façon mal.
 * 3. **Le scan quand il est là.** `BarcodeDetector` existe sur Android et dans
 *    Chrome ; ailleurs, on tape le code à la main. On ne bricole pas un
 *    décodeur maison pour un cas qui se règle en huit chiffres.
 */

/** Portions courantes, en grammes. Volontairement rondes : personne ne pèse. */
const PORTIONS = [30, 50, 80, 100, 150, 200, 250, 300];

interface FoodSearchProps {
  day: string;
  meal?: Meal;
  onAdded?: () => void;
  /** Replié par défaut sur l'écran Jour, déplié sur l'écran Nutrition. */
  defaultOpen?: boolean;
}

export function FoodSearch({
  day,
  meal: initialMeal,
  onAdded,
  defaultOpen = false,
}: FoodSearchProps) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(defaultOpen);
  const [query, setQuery] = useState("");
  const [meal, setMeal] = useState<Meal>(initialMeal ?? "lunch");
  const [chosen, setChosen] = useState<Food | null>(null);
  const [quantity, setQuantity] = useState(100);
  const [codeInput, setCodeInput] = useState("");

  const foods = useQuery({
    queryKey: ["foods", query],
    queryFn: () => api.searchFoods(query),
    enabled: open,
  });

  const scan = useMutation({
    mutationFn: (barcode: string) => api.scanBarcode(barcode),
    onSuccess: (food) => {
      setChosen(food);
      setCodeInput("");
    },
  });

  // Déstructuré : une ref qui reste accrochée à un objet rendu par un hook
  // finit par être lue pendant le rendu, ce que React interdit.
  const {
    attach: attachVideo,
    running: scanning,
    available: canScan,
    start: startScan,
    stop: stopScan,
  } = useBarcodeScanner((code) => scan.mutate(code));

  const add = useMutation({
    mutationFn: () =>
      api.addFoodLog({
        day,
        meal,
        food_id: chosen?.id,
        quantity_g: quantity,
      }),
    onSuccess: () => {
      setChosen(null);
      setQuery("");
      queryClient.invalidateQueries({ queryKey: ["nutrition-day"] });
      queryClient.invalidateQueries({ queryKey: ["foods"] });
      onAdded?.();
    },
  });

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex min-h-touch w-full items-center justify-center gap-2 rounded-button border border-line bg-card px-4 text-[15px] font-semibold text-ink-2"
      >
        <IconSearch className="h-5 w-5" />
        Ajouter un aliment
      </button>
    );
  }

  const factor = quantity / 100;

  return (
    <div className="rounded-card border border-line bg-card p-3">
      {/* Le repas d'abord : c'est le seul champ qu'on change souvent, et il se
          règle en un tap. */}
      <div className="flex gap-1.5 overflow-x-auto pb-2">
        {MEALS.map((candidate) => (
          <button
            key={candidate}
            type="button"
            onClick={() => setMeal(candidate)}
            aria-pressed={meal === candidate}
            className={`min-h-touch shrink-0 rounded-pill border px-3.5 text-[14px] font-semibold ${
              meal === candidate
                ? "border-accent bg-accent text-on-accent"
                : "border-line bg-card text-ink-2"
            }`}
          >
            {MEAL_LABELS[candidate]}
          </button>
        ))}
      </div>

      {chosen ? (
        <div>
          <p className="text-[16px] font-semibold text-ink">{chosen.name}</p>
          <p className="tabular pt-0.5 text-[13px] text-mute">
            {num(chosen.kcal_100g, 0)} kcal · {num(chosen.protein_100g)} g de
            protéines pour 100 g
          </p>

          <p className="pb-1.5 pt-3 text-[12px] font-semibold uppercase tracking-wide text-mute">
            Quantité
          </p>
          <div className="flex gap-1.5 overflow-x-auto pb-1">
            {PORTIONS.map((grams) => (
              <button
                key={grams}
                type="button"
                onClick={() => setQuantity(grams)}
                aria-pressed={quantity === grams}
                className={`tabular min-h-touch shrink-0 rounded-pill border px-3.5 text-[15px] font-semibold ${
                  quantity === grams
                    ? "border-accent bg-accent text-on-accent"
                    : "border-line bg-card text-ink-2"
                }`}
              >
                {grams} g
              </button>
            ))}
          </div>

          <p className="tabular pt-2 text-[15px] font-semibold text-ink">
            {num((chosen.kcal_100g ?? 0) * factor, 0)} kcal ·{" "}
            {num((chosen.protein_100g ?? 0) * factor)} g P
          </p>

          <div className="flex gap-3 pt-3">
            <button
              type="button"
              onClick={() => add.mutate()}
              disabled={add.isPending}
              className="flex min-h-touch flex-1 items-center justify-center gap-2 rounded-button bg-accent px-4 text-[16px] font-semibold text-on-accent disabled:opacity-50"
            >
              <IconCheck className="h-5 w-5" />
              {add.isPending ? "Ajout…" : "Ajouter"}
            </button>
            <button
              type="button"
              onClick={() => setChosen(null)}
              className="min-h-touch rounded-button border border-line bg-card px-4 text-[15px] font-semibold text-ink-2"
            >
              Autre
            </button>
          </div>
        </div>
      ) : (
        <>
          <div className="flex gap-2">
            <input
              type="search"
              inputMode="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Chercher un aliment"
              aria-label="Chercher un aliment"
              className="min-h-touch min-w-0 flex-1 rounded-button border border-line bg-soft px-3 text-[16px] text-ink placeholder:text-mute"
            />
            <button
              type="button"
              onClick={canScan ? startScan : undefined}
              disabled={!canScan || scanning}
              aria-label="Scanner un code-barres"
              className="flex h-touch w-touch shrink-0 items-center justify-center rounded-button border border-line bg-card text-ink-2 disabled:opacity-40"
            >
              <IconBarcode className="h-5 w-5" />
            </button>
          </div>

          {/* Le scan quand le navigateur le sait faire, le code à la main
              sinon. On ne bricole pas un décodeur pour huit chiffres. */}
          {scanning ? (
            <div className="pt-2">
              <video
                ref={attachVideo}
                playsInline
                muted
                className="w-full rounded-cell border border-line"
              />
              <button
                type="button"
                onClick={stopScan}
                className="min-h-touch pt-1 text-[13px] font-semibold text-mute"
              >
                Arrêter le scan
              </button>
            </div>
          ) : null}

          {!canScan ? (
            <div className="flex gap-2 pt-2">
              <input
                type="text"
                inputMode="numeric"
                value={codeInput}
                onChange={(event) => setCodeInput(event.target.value)}
                placeholder="Code-barres"
                aria-label="Saisir un code-barres"
                className="min-h-touch min-w-0 flex-1 rounded-button border border-line bg-soft px-3 text-[16px] text-ink placeholder:text-mute"
              />
              <button
                type="button"
                onClick={() => scan.mutate(codeInput.trim())}
                disabled={codeInput.trim().length < 6 || scan.isPending}
                className="min-h-touch shrink-0 rounded-button border border-line bg-card px-4 text-[15px] font-semibold text-ink-2 disabled:opacity-40"
              >
                Chercher
              </button>
            </div>
          ) : null}

          {scan.error ? (
            <p className="pt-2 text-[13px] text-ink-2">
              Produit inconnu. Cherche-le par son nom.
            </p>
          ) : null}

          {foods.isPending ? (
            <p className="pt-3 text-[14px] text-mute">Lecture…</p>
          ) : (foods.data ?? []).length === 0 ? (
            <p className="pt-3 text-[13px] leading-snug text-ink-2">
              {query
                ? "Rien trouvé. La table Ciqual n'est peut-être pas encore importée."
                : "Les aliments les plus utilisés apparaîtront ici."}
            </p>
          ) : (
            <ul className="pt-2">
              {(foods.data ?? []).map((food) => (
                <li key={food.id} className="border-b border-line last:border-0">
                  <button
                    type="button"
                    onClick={() => setChosen(food)}
                    className="flex min-h-touch w-full items-center gap-3 py-2 text-left"
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[15px] text-ink">
                        {food.name}
                      </span>
                      <span className="tabular block truncate text-[12px] text-mute">
                        {num(food.kcal_100g, 0)} kcal / 100 g
                        {food.recent_count > 0
                          ? ` · ${food.recent_count}×`
                          : ""}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      <button
        type="button"
        onClick={() => setOpen(false)}
        className="min-h-touch pt-2 text-[13px] font-semibold text-mute"
      >
        Fermer
      </button>
    </div>
  );
}
