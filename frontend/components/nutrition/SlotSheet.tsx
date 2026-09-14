"use client";

import {
  IconAway,
  IconBook,
  IconRefresh,
  IconRestore,
  IconSearch,
  IconSwap,
} from "@/components/ui/Icons";
import { MEAL_LABELS, PLANNED_MEALS, type MealPlan, type PlannedMeal } from "@/lib/types";

/**
 * **Ce qu'on peut faire d'un créneau du menu**, en bas de l'écran.
 *
 * Cinq gestes, dans l'ordre où on les veut : voir la recette, en tirer une
 * autre, en choisir une précise, l'échanger avec un autre soir, ou dire qu'on
 * n'est pas là.
 *
 * Le dernier est celui qui manquait, et c'est le plus utile : **« je ne suis
 * pas chez moi » est une contrainte, pas une préférence**. Elle sort le plat
 * du menu *et* ses ingrédients de la liste de courses, et elle survit à une
 * régénération complète de la semaine.
 *
 * L'échange passe avant la régénération dans l'esprit, sinon dans la liste :
 * quand la semaine ne se déroule pas comme prévu, le plat de deux heures tombe
 * le soir où l'on rentre tard. Le déplacer vaut mieux que le refaire tirer —
 * on l'avait choisi.
 */

const DAYS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"];

export interface Slot {
  day: number;
  meal: PlannedMeal;
}

export function slotLabel(slot: Slot): string {
  return `${MEAL_LABELS[slot.meal].toLowerCase()} de ${DAYS[slot.day].toLowerCase()}`;
}

function Backdrop({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex flex-col justify-end">
      <button
        type="button"
        aria-label="Fermer"
        onClick={onClose}
        className="absolute inset-0 bg-ink/40"
      />
      <div className="relative max-h-[85vh] overflow-y-auto rounded-t-card border-t border-line bg-card pb-6 lg:mx-auto lg:mb-6 lg:max-w-[520px] lg:rounded-card lg:border">
        {children}
      </div>
    </div>
  );
}

function Row({
  icon,
  label,
  hint,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  hint?: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex min-h-touch w-full items-center gap-3 border-b border-line px-5 py-3 text-left last:border-0"
    >
      <span className="shrink-0 text-mute">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block text-[15px] font-semibold text-ink">{label}</span>
        {hint ? (
          <span className="block text-[12px] leading-snug text-mute">{hint}</span>
        ) : null}
      </span>
    </button>
  );
}

export function SlotActions({
  plan,
  slot,
  onClose,
  onOpenRecipe,
  onRegenerate,
  onPick,
  onSwap,
  onAway,
}: {
  plan: MealPlan;
  slot: Slot;
  onClose: () => void;
  onOpenRecipe: (recipeId: number) => void;
  onRegenerate: () => void;
  onPick: () => void;
  onSwap: () => void;
  onAway: (away: boolean) => void;
}) {
  const item = plan.items.find(
    (entry) => entry.day_index === slot.day && entry.meal === slot.meal,
  );
  const away = item?.status === "away";

  return (
    <Backdrop onClose={onClose}>
      <header className="px-5 pb-1 pt-4">
        <h2 className="font-display text-[20px] font-semibold uppercase leading-none text-ink">
          {MEAL_LABELS[slot.meal]} — {DAYS[slot.day]}
        </h2>
        <p className="pt-1 text-[13px] text-mute">
          {away
            ? "Tu n'es pas là : rien de prévu, rien à acheter."
            : (item?.recipe?.name ?? "Aucun plat pour l'instant.")}
        </p>
      </header>

      <div className="pt-2">
        {item?.recipe ? (
          <Row
            icon={<IconBook className="h-5 w-5" />}
            label="Voir la recette"
            hint="Ingrédients, étapes, ta note"
            onClick={() => onOpenRecipe(item.recipe!.id)}
          />
        ) : null}

        {!away ? (
          <>
            <Row
              icon={<IconRefresh className="h-5 w-5" />}
              label="Un autre plat"
              hint="Le tirage en propose un différent"
              onClick={onRegenerate}
            />
            <Row
              icon={<IconSearch className="h-5 w-5" />}
              label="Choisir un plat…"
              hint="Tes favorites d'abord"
              onClick={onPick}
            />
            <Row
              icon={<IconSwap className="h-5 w-5" />}
              label="Échanger avec…"
              hint="Le déplacer vaut mieux que le refaire tirer"
              onClick={onSwap}
            />
          </>
        ) : null}

        {away ? (
          <Row
            icon={<IconRestore className="h-5 w-5" />}
            label="Finalement je serai là"
            hint="Un plat revient sur ce créneau"
            onClick={() => onAway(false)}
          />
        ) : (
          <Row
            icon={<IconAway className="h-5 w-5" />}
            label="Je ne suis pas là"
            hint="Ni au menu, ni dans la liste de courses"
            onClick={() => onAway(true)}
          />
        )}
      </div>
    </Backdrop>
  );
}

export function SwapPicker({
  plan,
  slot,
  onClose,
  onSwap,
}: {
  plan: MealPlan;
  slot: Slot;
  onClose: () => void;
  onSwap: (other: Slot) => void;
}) {
  const targets: Slot[] = [];
  for (let day = 0; day < 7; day += 1) {
    for (const meal of PLANNED_MEALS) {
      if (day === slot.day && meal === slot.meal) continue;
      targets.push({ day, meal });
    }
  }

  const label = (other: Slot) => {
    const item = plan.items.find(
      (entry) => entry.day_index === other.day && entry.meal === other.meal,
    );
    if (item?.status === "away") return "Pas là";
    return item?.recipe?.name ?? "À choisir";
  };

  return (
    <Backdrop onClose={onClose}>
      <header className="px-5 pb-3 pt-4">
        <h2 className="font-display text-[20px] font-semibold uppercase leading-none text-ink">
          Échanger
        </h2>
        <p className="pt-1 text-[13px] text-mute">
          Avec quel créneau échanger le {slotLabel(slot)} ?
        </p>
      </header>

      <ul>
        {targets.map((other) => (
          <li key={`${other.day}-${other.meal}`}>
            <button
              type="button"
              onClick={() => onSwap(other)}
              className="flex min-h-touch w-full items-center gap-3 border-b border-line px-5 py-2 text-left"
            >
              <span className="w-[104px] shrink-0 text-[12px] font-semibold uppercase tracking-wide text-mute">
                {DAYS[other.day].slice(0, 3)} · {MEAL_LABELS[other.meal]}
              </span>
              <span className="min-w-0 flex-1 truncate text-[15px] text-ink">
                {label(other)}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </Backdrop>
  );
}
