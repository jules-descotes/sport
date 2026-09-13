import { describe, expect, it } from "vitest";

import { SLOT_SPAN_HOURS, slotIsPast } from "./slot-time";

/**
 * Les heures sont écrites en local (`T09:00`, sans `Z`) : c'est ainsi que la
 * bande les lit, et un `Z` testerait le fuseau de la machine plutôt que la
 * règle.
 */
describe("slotIsPast", () => {
  const now = new Date("2026-09-13T14:20:00");

  it("éteint un créneau entièrement écoulé", () => {
    expect(slotIsPast("2026-09-13T09:00:00", now)).toBe(true);
    expect(slotIsPast("2026-09-13T06:00:00", now)).toBe(true);
  });

  it("laisse allumé le créneau en cours", () => {
    // 12 h court jusqu'à 15 h : à 14 h 20, l'éteindre barrerait l'heure qu'on
    // est en train de vivre.
    expect(slotIsPast("2026-09-13T12:00:00", now)).toBe(false);
  });

  it("laisse allumé ce qui vient", () => {
    expect(slotIsPast("2026-09-13T15:00:00", now)).toBe(false);
    expect(slotIsPast("2026-09-14T09:00:00", now)).toBe(false);
  });

  it("bascule à la seconde où le créneau se ferme", () => {
    expect(slotIsPast("2026-09-13T12:00:00", new Date("2026-09-13T15:00:00"))).toBe(
      true,
    );
    expect(slotIsPast("2026-09-13T12:00:00", new Date("2026-09-13T14:59:59"))).toBe(
      false,
    );
  });

  it("suit le pas qu'on lui donne — une heure pour le tableau de Surf", () => {
    expect(slotIsPast("2026-09-13T13:00:00", now, 1)).toBe(true);
    expect(slotIsPast("2026-09-13T14:00:00", now, 1)).toBe(false);
    expect(SLOT_SPAN_HOURS).toBe(3);
  });
});
