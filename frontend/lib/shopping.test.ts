/**
 * La liste de courses, telle qu'on la lit dans le rayon.
 *
 * Le serveur décide de l'unité et arrondit ; ce module met en forme. Les deux
 * bouts comptent : une conversion juste affichée « 3.0 œufs » se lit encore
 * comme une sortie de machine, et c'est une liste qu'on n'emporte pas.
 */
import { describe, expect, it } from "vitest";

import { buyHint, buyQuantity, grams, millilitres } from "./shopping";
import type { Buyable } from "./shopping";

function line(over: Partial<Buyable>): Buyable {
  return {
    unit: "g",
    quantity: 300,
    quantity_g: 300,
    unit_label: null,
    ...over,
  };
}

describe("les unités d'achat", () => {
  it("compte ce qui se compte", () => {
    expect(
      buyQuantity(
        line({ unit: "piece", quantity: 3, quantity_g: 165, unit_label: "œufs" }),
      ),
    ).toBe("3 œufs");
  });

  it("n'écrit jamais « 1 bananes »", () => {
    expect(
      buyQuantity(
        line({ unit: "piece", quantity: 1, quantity_g: 100, unit_label: "banane" }),
      ),
    ).toBe("1 banane");
  });

  it("pèse ce qui se pèse, et passe au kilo quand il le faut", () => {
    expect(buyQuantity(line({ quantity_g: 400 }))).toBe("400 g");
    expect(buyQuantity(line({ quantity_g: 1400 }))).toBe("1,4 kg");
  });

  it("verse ce qui se verse, et passe au litre quand il le faut", () => {
    expect(buyQuantity(line({ unit: "ml", quantity: 250 }))).toBe("250 ml");
    expect(buyQuantity(line({ unit: "ml", quantity: 1700 }))).toBe("1,7 L");
  });

  it("rappelle le poids derrière une pièce, jamais derrière un poids", () => {
    // La masse unitaire est une moyenne ; présentée seule, elle passerait pour
    // une mesure.
    expect(
      buyHint(
        line({ unit: "piece", quantity: 3, quantity_g: 165, unit_label: "œufs" }),
      ),
    ).toBe("165 g");
    // Répéter « 300 g · 300 g » n'apprend rien.
    expect(buyHint(line({ quantity_g: 300 }))).toBeNull();
  });

  it("bascule d'unité exactement au seuil", () => {
    // La décimale est celle de `num` : une seule convention de nombre dans
    // toute l'app, y compris quand elle tombe sur un zéro.
    expect(grams(999)).toBe("999 g");
    expect(grams(1000)).toBe("1,0 kg");
    expect(millilitres(999)).toBe("999 ml");
    expect(millilitres(1000)).toBe("1,0 L");
  });
});
