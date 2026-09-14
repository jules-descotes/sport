import { boardFeetInches, lengthFromFeet } from "./format";
import type { Gear, GearType } from "@/lib/types";

/**
 * Ce que la molette du matos manipule, et ce qui part en base quand on corrige.
 *
 * Séparé de l'écran parce que c'est la seule partie qui peut faire des dégâts
 * en silence : un PATCH mal calculé réécrit une longueur juste avec ce que la
 * molette savait afficher, et personne ne s'en aperçoit avant de relire la
 * fiche six mois plus tard.
 */

export const FEET = [4, 5, 6, 7, 8, 9, 10] as const;
// Les pouces impairs comptent : 5'11 et 6'1 sont des planches courantes, et
// une molette qui ne sait pas les dire fabrique exactement les fautes de
// saisie qu'on vient corriger ici.
export const INCHES = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11] as const;
export const VOLUMES = [24, 26, 28, 30, 32, 35, 40, 50, 65] as const;

export const GEAR_TYPES = ["board", "wetsuit", "accessory"] as const;

export interface GearDraft {
  name: string;
  type: GearType;
  feet: number | null;
  inches: number | null;
  volume: number | null;
}

/** Le brouillon d'une création : un 6'2 de 30 L, la planche la plus probable. */
export const NEW_GEAR: GearDraft = {
  name: "",
  type: "board",
  feet: 6,
  inches: 2,
  volume: 30,
};

/**
 * Le brouillon d'une correction : **exactement** ce qu'il y a en base.
 *
 * Rien n'est arrondi vers une valeur « propre » au passage. Une planche entrée
 * à 6'3 s'ouvre à 6'3, même si la molette ne prévoyait pas ce cran — c'est
 * `withValue` qui lui en fabrique un.
 */
export function draftFromGear(gear: Gear): GearDraft {
  const stored = gear.length_m === null ? null : boardFeetInches(gear.length_m);
  return {
    name: gear.name,
    type: gear.gear_type,
    feet: stored?.feet ?? null,
    inches: stored?.inches ?? null,
    volume: gear.volume_l,
  };
}

/**
 * La valeur enregistrée a toujours sa pastille, même si la liste ne la prévoit
 * pas. Une molette qui ne sait pas afficher ce qu'elle doit corriger ferait
 * dire à l'écran autre chose que ce qu'il y a en base — et un volume de 33 L
 * repartirait à 32 pour avoir touché au nom.
 */
export function withValue(
  options: readonly number[],
  value: number | null,
): number[] {
  if (value === null || options.includes(value)) return [...options];
  return [...options, value].sort((a, b) => a - b);
}

/** Comparaison de grandeurs en flottant : 1,88 n'est pas 1,8800000000000001. */
export function same(a: number | null, b: number | null): boolean {
  if (a === null || b === null) return a === b;
  return Math.abs(a - b) < 0.0005;
}

/**
 * La longueur a-t-elle bougé ?
 *
 * La comparaison se fait **en pieds et pouces**, pas en mètres. La molette ne
 * sait dire que des crans d'un pouce : tout ce qu'elle peut changer vaut au
 * moins 2,54 cm. Une planche enregistrée à 2,77 m se relit « 9'1 », qui se
 * réécrit 2,769 m — un millimètre d'écart qui vient de l'arrondi, pas d'un
 * geste. Comparer les mètres ferait repartir ce millimètre en base à chaque
 * correction du nom, et il n'y a aucune raison de toucher à une longueur qu'on
 * n'a pas touchée.
 */
function lengthChanged(gear: Gear, draft: GearDraft): boolean {
  const length = draftLength(draft);
  if (length === null || gear.length_m === null) return length !== gear.length_m;
  const stored = boardFeetInches(gear.length_m);
  return draft.feet !== stored.feet || draft.inches !== stored.inches;
}

/** La longueur d'un brouillon, en mètres. Une combinaison n'en a pas. */
export function draftLength(draft: GearDraft): number | null {
  if (draft.type !== "board" || draft.feet === null || draft.inches === null) {
    return null;
  }
  return lengthFromFeet(draft.feet, draft.inches);
}

/** Le volume d'un brouillon. Une combinaison n'en a pas non plus. */
export function draftVolume(draft: GearDraft): number | null {
  return draft.type === "board" ? draft.volume : null;
}

export interface GearPatch {
  name?: string;
  gear_type?: GearType;
  length_m?: number | null;
  volume_l?: number | null;
}

/**
 * Ce qui a changé, et rien d'autre.
 *
 * Un PATCH qui renverrait tous les champs réécrirait la longueur avec ce que la
 * molette sait afficher : une planche entrée à 6'3 repartirait à 6'2 parce
 * qu'on a corrigé son volume. Le back applique ce qu'il reçoit (`exclude_unset`),
 * donc ne rien envoyer est la seule façon de ne rien toucher.
 *
 * Un patch vide veut dire qu'il n'y a rien à enregistrer — le bouton reste
 * inerte, comme celui de l'écran de notation tant que les deux notes manquent.
 */
export function gearPatch(gear: Gear, draft: GearDraft): GearPatch {
  const patch: GearPatch = {};
  const name = draft.name.trim();
  const length = draftLength(draft);
  const volume = draftVolume(draft);

  if (name !== gear.name) patch.name = name;
  if (draft.type !== gear.gear_type) patch.gear_type = draft.type;
  if (lengthChanged(gear, draft)) patch.length_m = length;
  if (!same(volume, gear.volume_l)) patch.volume_l = volume;

  return patch;
}
