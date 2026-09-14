/**
 * Lire une quantité **comme au supermarché**.
 *
 * Le serveur agrège en grammes — c'est la grandeur vraie, et c'est elle qui a
 * servi à additionner sept dîners. Il rend aussi l'unité dans laquelle la
 * chose s'achète : `piece` pour ce qui se compte, `ml` pour ce qui se verse,
 * `g` pour tout le reste (cf. `app/services/food_units.py`).
 *
 * Ce module ne décide de rien : il met en forme. La décision « les œufs se
 * comptent » vit côté serveur, en un seul endroit, parce qu'elle sert aussi à
 * l'affichage des ingrédients d'une recette.
 */
import { num } from "./format";

export type BuyUnit = "g" | "piece" | "ml";

export interface Buyable {
  unit: BuyUnit;
  quantity: number;
  quantity_g: number;
  unit_label: string | null;
}

/** Grammes vers une quantité lisible : au-delà du kilo, on passe au kilo. */
export function grams(value: number): string {
  return value >= 1000 ? `${num(value / 1000, 1)} kg` : `${Math.round(value)} g`;
}

/** Millilitres vers une quantité lisible : au-delà du litre, on passe au litre. */
export function millilitres(value: number): string {
  return value >= 1000 ? `${num(value / 1000, 1)} L` : `${Math.round(value)} ml`;
}

/**
 * Ce qu'on lit sur la ligne : « 3 œufs », « 1,4 kg », « 1,2 L ».
 *
 * Les pièces sont des entiers — le serveur arrondit au-dessus, parce qu'on ne
 * met pas 2,7 œufs dans un panier.
 */
export function buyQuantity(line: Buyable): string {
  if (line.unit === "piece") {
    return `${Math.round(line.quantity)} ${line.unit_label ?? ""}`.trim();
  }
  if (line.unit === "ml") return millilitres(line.quantity);
  return grams(line.quantity_g);
}

/**
 * Le poids, en second, quand la ligne est comptée en pièces.
 *
 * La masse unitaire est une **moyenne** (un œuf à 55 g, une courgette à 200 g).
 * Une moyenne présentée seule passerait pour une mesure, et c'est le genre de
 * détail qui fait acheter trois courgettes pour une ratatouille qui en demande
 * une et demie. Nul quand l'unité est déjà le poids : répéter « 300 g · 300 g »
 * n'apprend rien.
 */
export function buyHint(line: Buyable): string | null {
  if (line.unit === "g") return null;
  return grams(line.quantity_g);
}
