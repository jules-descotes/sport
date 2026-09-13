import { describe, expect, it } from "vitest";

import { switcherEntries } from "./spot-switcher";
import type { SpotHit } from "./types";

function hit(id: number, name: string): SpotHit {
  return {
    id,
    slug: name.toLowerCase().replace(/\s+/g, "-"),
    name,
    lat: 43.7,
    lon: -1.4,
    country_code: "FR",
    region: null,
    spot_type: "beach",
    source: "osm",
    coast_bearing_deg: null,
    onshore_dir_deg: null,
    webcam_url: null,
    tier: "home",
    distance_km: null,
    is_favorite: true,
    is_home: false,
  };
}

const graviere = hit(1, "La Gravière");
const parlementia = hit(2, "Parlementia");
const culsNus = hit(3, "Les Culs Nus");

describe("switcherEntries", () => {
  it("garde l'ordre des favoris et marque celui qu'on regarde", () => {
    const entries = switcherEntries(
      [graviere, parlementia, culsNus],
      parlementia,
      1,
    );

    expect(entries.map((entry) => entry.name)).toEqual([
      "La Gravière",
      "Parlementia",
      "Les Culs Nus",
    ]);
    expect(entries.map((entry) => entry.active)).toEqual([false, true, false]);
    expect(entries.map((entry) => entry.principal)).toEqual([
      true,
      false,
      false,
    ]);
  });

  it("met en tête le spot ouvert de passage, sans le compter deux fois", () => {
    const uluwatu = { id: 99, slug: "uluwatu", name: "Uluwatu" };
    const entries = switcherEntries([graviere, parlementia], uluwatu, 1);

    expect(entries.map((entry) => entry.name)).toEqual([
      "Uluwatu",
      "La Gravière",
      "Parlementia",
    ]);
    expect(entries[0]).toMatchObject({ active: true, visiting: true });
    expect(entries.filter((entry) => entry.active)).toHaveLength(1);
  });

  it("n'ajoute pas de pastille pour un favori déjà listé", () => {
    const entries = switcherEntries([graviere, parlementia], graviere, 1);

    expect(entries).toHaveLength(2);
    expect(entries.filter((entry) => entry.visiting)).toHaveLength(0);
  });

  it("ne rend rien quand il n'y a rien à choisir", () => {
    // Un seul favori, et c'est lui qu'on regarde : aucun geste à offrir.
    expect(switcherEntries([graviere], graviere, 1)).toEqual([]);
    expect(switcherEntries([], null, null)).toEqual([]);
  });

  it("rend la barre dès qu'un second spot existe, même sans favori ouvert", () => {
    // Deux favoris, prévision pas encore chargée : les pastilles sont là avant
    // le tableau — c'est justement quand l'écran est vide qu'on veut changer.
    const entries = switcherEntries([graviere, parlementia], null, 1);

    expect(entries).toHaveLength(2);
    expect(entries.some((entry) => entry.active)).toBe(false);
  });
});
