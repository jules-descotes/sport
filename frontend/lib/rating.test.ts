/**
 * Les demi-points et le découpage horaire — décidés le 13/09.
 *
 * Le cycle d'un bouton décide de ce qui finit en base : c'est la logique la
 * plus exposée au doigt de tout l'écran de notation, et la seule qu'on ne
 * puisse pas vérifier à l'œil.
 */
import { describe, expect, it } from "vitest";

import { scoreClass } from "./format";
import { cycleRating, isValidRating, startedHours } from "./rating";

describe("le cycle d'un bouton", () => {
  it("pose l'entier au premier tap", () => {
    expect(cycleRating(3, null)).toBe(3);
  });

  it("donne le demi-point supérieur au second tap", () => {
    expect(cycleRating(3, 3)).toBe(3.5);
  });

  it("revient à l'entier au troisième", () => {
    // Le geste est réversible sans chercher : c'est ce qui permet de l'essayer.
    expect(cycleRating(3, 3.5)).toBe(3);
  });

  it("repart de l'entier quand on change de bouton", () => {
    // On choisit une note, on n'incrémente pas un compteur.
    expect(cycleRating(4, 3.5)).toBe(4);
    expect(cycleRating(2, 5)).toBe(2);
  });

  it("ne fabrique pas de 5,5", () => {
    // 5 n'a pas de demi-point supérieur : un second tap le laisse à 5 plutôt
    // que de retomber à 4,5, qui serait une note qu'on n'a pas demandée.
    expect(cycleRating(5, 5)).toBe(5);
  });
});

describe("ce qui est une note", () => {
  it("accepte les entiers et les demis de 1 à 5", () => {
    for (const value of [1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5]) {
      expect(isValidRating(value)).toBe(true);
    }
  });

  it("refuse les quarts de point", () => {
    expect(isValidRating(3.7)).toBe(false);
    expect(isValidRating(2.25)).toBe(false);
  });

  it("refuse ce qui sort de l'échelle", () => {
    expect(isValidRating(0.5)).toBe(false);
    expect(isValidRating(5.5)).toBe(false);
  });
});

describe("la couleur interpole", () => {
  it("garde les paliers entiers inchangés", () => {
    // La non-régression qui compte : une note 4 posée à la main doit avoir
    // exactement la couleur d'une note 4 calculée par le moteur.
    expect(scoreClass(4)).toBe("score-4");
    expect(scoreClass(1)).toBe("score-1");
  });

  it("donne un palier intermédiaire aux demi-points", () => {
    expect(scoreClass(3.5)).toBe("score-35");
    expect(scoreClass(1.5)).toBe("score-15");
    expect(scoreClass(4.5)).toBe("score-45");
  });

  it("arrondit au demi-point le plus proche, pas à l'entier", () => {
    // Une note calculée à 3,47 tombe sur 3,5 : c'est la granularité de
    // l'échelle, et arrondir à 3 perdrait la moitié des paliers.
    expect(scoreClass(3.47)).toBe("score-35");
    expect(scoreClass(3.8)).toBe("score-4");
  });

  it("borne aux extrémités de l'échelle", () => {
    expect(scoreClass(0)).toBe("score-1");
    expect(scoreClass(9)).toBe("score-5");
    expect(scoreClass(null)).toBe("score-1");
  });
});

describe("les heures entamées d'une session", () => {
  const at = (hour: number, minute = 0) =>
    new Date(2026, 8, 13, hour, minute, 0, 0);

  it("compte l'heure du départ même entamée en retard", () => {
    expect(startedHours(at(8, 45), at(9, 30)).map((d) => d.getHours())).toEqual([
      8, 9,
    ]);
  });

  it("compte la dernière heure entamée", () => {
    // 8 h 15 → 10 h 40 : l'heure de 10 h a été vécue, elle mérite sa ligne.
    expect(startedHours(at(8, 15), at(10, 40)).map((d) => d.getHours())).toEqual(
      [8, 9, 10],
    );
  });

  it("s'arrête pile sur une fin à l'heure ronde", () => {
    // 8 h → 10 h : deux heures vécues, pas trois. L'heure de 10 h commence
    // quand on sort de l'eau.
    expect(startedHours(at(8), at(10)).map((d) => d.getHours())).toEqual([8, 9]);
  });

  it("rend une seule heure pour une session courte", () => {
    expect(startedHours(at(8, 10), at(8, 50))).toHaveLength(1);
  });

  it("ne s'emballe pas sur une durée absurde", () => {
    // Une session de trente heures est une erreur de saisie, et une frise de
    // trente lignes ne se remplirait jamais.
    const overnight = new Date(2026, 8, 14, 20, 0);
    expect(startedHours(at(8), overnight).length).toBeLessThanOrEqual(12);
  });
});
