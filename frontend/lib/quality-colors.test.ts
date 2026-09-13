/**
 * Les couleurs du tableau horaire disent **ce qui est bon**, pas ce qui est
 * gros (décidé le 13/09, retours n° 4).
 *
 * C'est testé ici parce qu'une erreur d'un cran ne se remarque pas à la
 * lecture et ne se voit pas à l'écran : une cellule un ton trop pâle reste une
 * cellule plausible. Ce qui se voit, au bout de trois semaines, c'est qu'on ne
 * fait plus confiance au tableau.
 */
import { describe, expect, it } from "vitest";

import {
  DEFAULT_THRESHOLDS,
  energyQualityClass,
  legendRows,
  periodQualityClass,
  waveQualityClass,
  windQualityClass,
} from "./quality-colors";
import type { Thresholds } from "./types";

const T = DEFAULT_THRESHOLDS;

/** Le rang d'une teinte sur la rampe, pour comparer sans coder les classes. */
function rank(className: string): number {
  if (className === "seq-empty") return -2;
  if (className === "seq-quiet") return -1;
  if (className === "wind-top") return -1;
  return Number(className.replace("seq-", ""));
}

describe("houle", () => {
  it("reste neutre sous le minimum", () => {
    // Pas un palier bas : un palier bas se lit « un peu de quelque chose de
    // bien », et 0,8 m n'est pas un peu de bonne houle.
    expect(waveQualityClass(0.8, T)).toBe("seq-quiet");
    expect(waveQualityClass(1.19, T)).toBe("seq-quiet");
  });

  it("s'allume au minimum et se sature en grossissant", () => {
    const start = rank(waveQualityClass(1.2, T));
    const good = rank(waveQualityClass(1.8, T));
    const big = rank(waveQualityClass(2.5, T));

    expect(start).toBeGreaterThan(0);
    expect(good).toBeGreaterThan(start);
    expect(big).toBeGreaterThan(good);
  });

  it("ne pâlit pas au-delà du « gros »", () => {
    // Le fait qu'une houle de 5 m redevienne injouable est dit par la **note**,
    // qui redescend. Une couleur qui pâlirait ne dirait pas si c'est trop
    // petit ou trop gros.
    expect(rank(waveQualityClass(5, T))).toBe(rank(waveQualityClass(3.2, T)));
  });

  it("suit les seuils de chacun", () => {
    const smallIsFine: Thresholds = {
      ...T,
      wave_min_m: 0.6,
      wave_good_m: 1.0,
      wave_big_m: 1.5,
    };
    // 1 m : sous le minimum de Jules, « bon » pour quelqu'un d'autre.
    expect(waveQualityClass(1.0, T)).toBe("seq-quiet");
    expect(rank(waveQualityClass(1.0, smallIsFine))).toBeGreaterThan(1);
  });

  it("rend une case creuse quand la donnée manque", () => {
    expect(waveQualityClass(null, T)).toBe("seq-empty");
    expect(waveQualityClass(undefined, T)).toBe("seq-empty");
    expect(waveQualityClass(Number.NaN, T)).toBe("seq-empty");
  });
});

describe("période", () => {
  it("reste neutre sous le seuil « bon »", () => {
    expect(periodQualityClass(5, T)).toBe("seq-quiet");
    expect(periodQualityClass(7.9, T)).toBe("seq-quiet");
  });

  it("monte de mieux en mieux", () => {
    const good = rank(periodQualityClass(8, T));
    const great = rank(periodQualityClass(12, T));
    const beyond = rank(periodQualityClass(17, T));

    expect(good).toBeGreaterThan(0);
    expect(great).toBeGreaterThan(good);
    expect(beyond).toBeGreaterThanOrEqual(great);
  });

  it("ne se replie pas si les deux seuils sont collés", () => {
    // Le serveur refuse l'ordre inversé ; les seuils très proches, lui, sont
    // une préférence légitime, et la rampe doit rester monotone.
    const tight: Thresholds = { ...T, period_good_s: 10, period_great_s: 10.5 };
    expect(rank(periodQualityClass(9, tight))).toBe(-1);
    expect(rank(periodQualityClass(14, tight))).toBeGreaterThan(
      rank(periodQualityClass(10, tight)),
    );
  });
});

describe("vent", () => {
  it("est le seul axe chaud, et seulement sous le seuil « top »", () => {
    expect(windQualityClass(4, T)).toBe("wind-top");
    expect(windQualityClass(9.9, T)).toBe("wind-top");
    expect(windQualityClass(10, T)).not.toBe("wind-top");
  });

  it("va de plus en plus marqué en montant — l'inverse des autres", () => {
    const calm = rank(windQualityClass(11, T));
    const strong = rank(windQualityClass(16, T));
    const gale = rank(windQualityClass(30, T));

    expect(strong).toBeGreaterThan(calm);
    expect(gale).toBeGreaterThan(strong);
  });

  it("ne passe jamais par le rouge", () => {
    // Règle C.2 du 13/09 : le rouge dit « danger », et vingt-cinq nœuds ne
    // sont pas un danger, c'est une mauvaise journée de surf. Toutes les
    // classes sortantes appartiennent au séquentiel froid ou à l'accent.
    const allowed = new Set([
      "wind-top",
      "seq-empty",
      "seq-quiet",
      "seq-1",
      "seq-2",
      "seq-3",
      "seq-4",
      "seq-5",
      "seq-6",
    ]);
    for (let kt = 0; kt <= 60; kt += 1) {
      expect(allowed.has(windQualityClass(kt, T))).toBe(true);
    }
  });
});

describe("énergie", () => {
  it("porte exactement la teinte de la houle qui la produit", () => {
    // Elle vaut 0,49 × H² × T : lui donner sa propre rampe ferait diverger
    // deux cellules de la même colonne.
    for (const height of [0.9, 1.2, 1.8, 2.5, 4]) {
      expect(energyQualityClass(height, 30, T)).toBe(
        waveQualityClass(height, T),
      );
    }
  });

  it("reste creuse quand l'énergie manque, même si la houle est connue", () => {
    expect(energyQualityClass(2.0, null, T)).toBe("seq-empty");
  });
});

describe("légende", () => {
  it("affiche les seuils réellement réglés, pas des exemples", () => {
    const mine: Thresholds = { ...T, period_good_s: 10, period_great_s: 14 };
    const rows = legendRows(mine);
    const period = rows.find((row) => row.axis === "Période");

    expect(period?.entries.map((entry) => entry.label)).toContain("10 s");
    expect(period?.entries.map((entry) => entry.label)).toContain("14 s");
  });

  it("écrit les décimales à la française", () => {
    const rows = legendRows(T);
    const wave = rows.find((row) => row.axis === "Houle");

    expect(wave?.entries.map((entry) => entry.label)).toContain("1,8 m");
    // Et jamais « 2,5,0 » ni « 2.5 ».
    expect(wave?.entries.map((entry) => entry.label)).toContain("2,5 m");
  });

  it("couvre les trois axes, et seulement eux", () => {
    expect(legendRows(T).map((row) => row.axis)).toEqual([
      "Houle",
      "Période",
      "Vent",
    ]);
  });
});
