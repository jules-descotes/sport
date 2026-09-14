/**
 * Corriger une planche mal saisie — le PATCH et la molette qui le pré-remplit.
 *
 * C'est la seule partie de l'écran matos qui peut faire des dégâts en silence.
 * Une longueur juste réécrite par un champ qu'on n'a pas touché ne se voit pas
 * à l'œil : elle se découvre en relisant la fiche six mois plus tard, quand le
 * modèle a déjà appris qu'on surfait cette session-là en 6'2.
 */
import { describe, expect, it } from "vitest";

import {
  FEET,
  INCHES,
  NEW_GEAR,
  VOLUMES,
  draftFromGear,
  gearPatch,
  withValue,
} from "./gear-form";
import type { GearDraft } from "./gear-form";
import type { Gear } from "./types";

const PYZEL: Gear = {
  id: 1,
  name: "6'2 Pyzel",
  gear_type: "board",
  // 6'2 — la base porte des mètres, l'écran porte des pieds.
  length_m: 1.88,
  volume_l: 30,
  discipline: "surf",
  purchased_on: null,
  is_active: true,
  created_at: "2026-09-12T08:00:00Z",
};

const edit = (gear: Gear, change: Partial<GearDraft>): GearDraft => ({
  ...draftFromGear(gear),
  ...change,
});

describe("le brouillon d'une correction", () => {
  it("s'ouvre exactement sur ce qu'il y a en base", () => {
    expect(draftFromGear(PYZEL)).toEqual({
      name: "6'2 Pyzel",
      type: "board",
      feet: 6,
      inches: 2,
      volume: 30,
    });
  });

  it("n'invente pas de longueur pour une combinaison", () => {
    const wetsuit: Gear = {
      ...PYZEL,
      gear_type: "wetsuit",
      length_m: null,
      volume_l: null,
    };
    expect(draftFromGear(wetsuit)).toMatchObject({
      feet: null,
      inches: null,
      volume: null,
    });
  });

  it("ne se confond pas avec le brouillon d'une création", () => {
    // Une création part sur la planche la plus probable ; une correction part
    // sur la planche qui est là. Semer 6'2 dans une correction effacerait la
    // valeur qu'on vient précisément vérifier.
    expect(NEW_GEAR.name).toBe("");
    expect(draftFromGear(PYZEL).name).toBe("6'2 Pyzel");
  });
});

describe("ce qui part en base", () => {
  it("n'envoie rien quand rien n'a changé", () => {
    // Un patch vide, et le bouton reste inerte.
    expect(gearPatch(PYZEL, draftFromGear(PYZEL))).toEqual({});
  });

  it("n'envoie que le champ corrigé", () => {
    expect(gearPatch(PYZEL, edit(PYZEL, { volume: 32 }))).toEqual({
      volume_l: 32,
    });
  });

  it("ne réécrit pas une longueur qu'on n'a pas touchée", () => {
    // Le cas qui justifie tout le module : une planche entrée à 6'3 dont on
    // corrige le volume ne doit pas repartir à 6'2 parce que l'ancienne
    // molette ne savait dire que les pouces pairs.
    const pyzel63: Gear = { ...PYZEL, length_m: 1.905 };
    const patch = gearPatch(pyzel63, edit(pyzel63, { volume: 32 }));

    expect(patch).toEqual({ volume_l: 32 });
    expect(patch.length_m).toBeUndefined();
  });

  it("convertit les pieds-pouces corrigés en mètres", () => {
    expect(gearPatch(PYZEL, edit(PYZEL, { inches: 3 }))).toEqual({
      length_m: 1.905,
    });
  });

  it("ne voit pas de changement dans un aller-retour mètres → pieds → mètres", () => {
    // Ouvrir une fiche et la refermer ne doit pas suffire à la modifier — y
    // compris pour une longueur qui ne tombe pas sur la grille des pouces :
    // 2,77 m se relit 9'1, qui se réécrit 2,769 m. Ce millimètre vient de
    // l'arrondi, pas d'un geste, et il n'a rien à faire en base.
    for (const length of [1.88, 1.905, 2.77, 1.7, 3.05]) {
      const gear: Gear = { ...PYZEL, length_m: length };
      expect(gearPatch(gear, draftFromGear(gear))).toEqual({});
    }
  });

  it("envoie la longueur dès qu'un cran de pouce a bougé", () => {
    // L'autre versant : la tolérance ne doit pas manger un vrai changement.
    const log: Gear = { ...PYZEL, length_m: 2.77 };
    expect(gearPatch(log, edit(log, { inches: 2 }))).toEqual({
      length_m: 2.794,
    });
  });

  it("efface longueur et volume quand la planche devient une combinaison", () => {
    // Un `null` explicite, pas un champ absent : là, l'effacement est voulu.
    expect(gearPatch(PYZEL, edit(PYZEL, { type: "wetsuit" }))).toEqual({
      gear_type: "wetsuit",
      length_m: null,
      volume_l: null,
    });
  });

  it("envoie le nom sans ses espaces", () => {
    expect(gearPatch(PYZEL, edit(PYZEL, { name: "  6'2 Pyzel  " }))).toEqual({});
    expect(gearPatch(PYZEL, edit(PYZEL, { name: " 6'3 Pyzel " }))).toEqual({
      name: "6'3 Pyzel",
    });
  });
});

describe("la molette", () => {
  it("fabrique un cran pour la valeur enregistrée quand elle n'en a pas", () => {
    // 33 L n'est pas dans la liste ; la molette doit quand même pouvoir dire
    // 33, sinon l'écran affiche autre chose que ce qu'il y a en base.
    expect(withValue(VOLUMES, 33)).toContain(33);
    expect(withValue(VOLUMES, 33)).toEqual([...VOLUMES, 33].sort((a, b) => a - b));
  });

  it("ne double pas un cran qui existe déjà", () => {
    expect(withValue(VOLUMES, 30)).toEqual([...VOLUMES]);
    expect(withValue(INCHES, 2)).toEqual([...INCHES]);
  });

  it("laisse la liste intacte quand il n'y a rien à afficher", () => {
    expect(withValue(FEET, null)).toEqual([...FEET]);
  });

  it("sait dire les pouces impairs", () => {
    // 5'11 et 6'1 sont des planches courantes : une molette qui ne les dit pas
    // fabrique les fautes de saisie qu'on vient corriger.
    expect(INCHES).toContain(1);
    expect(INCHES).toContain(11);
  });
});
