import {
  IconBook,
  IconCheck,
  IconFlame,
  IconHeart,
  IconLeaf,
  IconSleep,
  IconSun,
  IconWater,
} from "@/components/ui/Icons";

/**
 * Les icônes d'habitude — **une petite liste fermée**.
 *
 * Pas une URL, pas un emoji : les icônes du produit sont en trait de 1,75 px,
 * dessinées sur une grille de 24, et le CLAUDE.md interdit les emoji. Un jeu
 * restreint garantit aussi que la rangée de pastilles de l'écran Jour reste
 * lisible quelle que soit la combinaison choisie.
 *
 * La même liste est validée côté serveur (`schemas/habit.py`) : une icône
 * inconnue est refusée plutôt qu'ignorée, sans quoi une faute de frappe
 * donnerait une pastille vide qu'on chercherait longtemps.
 *
 * L'accès se fait par **un composant** et non par une fonction qui rend un
 * composant : fabriquer un type de composant pendant le rendu forcerait React
 * à remonter le sous-arbre à chaque rendu du parent — l'icône clignoterait à
 * chaque tap.
 */
const HABIT_ICONS = {
  check: IconCheck,
  water: IconWater,
  sleep: IconSleep,
  book: IconBook,
  leaf: IconLeaf,
  flame: IconFlame,
  heart: IconHeart,
  sun: IconSun,
} as const;

export type HabitIconName = keyof typeof HABIT_ICONS;

export const HABIT_ICON_KEYS = Object.keys(HABIT_ICONS) as HabitIconName[];

export function HabitIcon({
  name,
  className,
}: {
  name: string;
  className?: string;
}) {
  const key: HabitIconName =
    name in HABIT_ICONS ? (name as HabitIconName) : "check";
  const Icon = HABIT_ICONS[key];
  return <Icon className={className} />;
}
