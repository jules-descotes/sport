/**
 * Le cache client des prévisions — ce qui est servi, et quand on réinterroge.
 *
 * Ce qui se teste ici est la **politique** : quelle entrée est servie quand
 * plusieurs runs coexistent, à partir de quand une donnée est périmée, ce qui
 * est élagué. C'est là que sont les décisions.
 *
 * Ce qui ne se teste pas ici est la **mécanique de revalidation** : elle est
 * déléguée à TanStack Query (`staleTime` + `refetch`), et la retester
 * reviendrait à tester la bibliothèque. Le point de contact entre les deux —
 * l'injection de l'entrée avec son `updatedAt` d'origine — est vérifié par
 * `isStale`, qui est la même règle exprimée en clair.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  STALE_MS,
  ageLabel,
  clearForecastCache,
  forecastKey,
  isStale,
  readForecastCache,
  writeForecastCache,
} from "./forecast-cache";

interface Payload {
  label: string;
}

beforeEach(async () => {
  vi.useRealTimers();
  await clearForecastCache();
});

describe("clé de cache", () => {
  it("sépare deux formes de la même prévision", () => {
    // Un résumé de trois heures et un tableau horaire ne sont pas le même
    // objet : servir l'un pour l'autre afficherait une grille à trous.
    expect(forecastKey("graviere", "5d-1h")).not.toBe(
      forecastKey("graviere", "5d-3h"),
    );
  });

  it("accepte un identifiant numérique comme un slug", () => {
    expect(forecastKey(42)).toBe("42");
  });
});

describe("lecture et écriture", () => {
  it("rend ce qui a été écrit", async () => {
    const key = forecastKey("graviere", "5d-1h");
    await writeForecastCache<Payload>(key, "2026-09-13T06:00:00Z", {
      label: "run de 6 h",
    });

    const entry = await readForecastCache<Payload>(key);
    expect(entry?.payload.label).toBe("run de 6 h");
    expect(entry?.run_ts).toBe("2026-09-13T06:00:00Z");
  });

  it("ne mélange pas deux spots", async () => {
    await writeForecastCache(forecastKey("graviere"), "r1", { label: "a" });
    await writeForecastCache(forecastKey("parlementia"), "r1", { label: "b" });

    const entry = await readForecastCache<Payload>(forecastKey("parlementia"));
    expect(entry?.payload.label).toBe("b");
  });

  it("sert le run le plus récent quand deux coexistent", async () => {
    // Même règle qu'en base (`forecast_reads.py`) : la prévision courante est
    // le `run_ts` maximum, jamais la dernière ligne venue.
    const key = forecastKey("graviere");
    await writeForecastCache<Payload>(key, "2026-09-13T06:00:00Z", {
      label: "6 h",
    });
    await writeForecastCache<Payload>(key, "2026-09-13T12:00:00Z", {
      label: "12 h",
    });
    // Écrit en dernier, mais plus ancien : il ne doit pas gagner.
    await writeForecastCache<Payload>(key, "2026-09-13T03:00:00Z", {
      label: "3 h",
    });

    const entry = await readForecastCache<Payload>(key);
    expect(entry?.payload.label).toBe("12 h");
  });

  it("réécrit le même run sans le dupliquer", async () => {
    const key = forecastKey("graviere");
    await writeForecastCache<Payload>(key, "run-1", { label: "avant" });
    await writeForecastCache<Payload>(key, "run-1", { label: "après" });

    const entry = await readForecastCache<Payload>(key);
    expect(entry?.payload.label).toBe("après");
  });

  it("élague les vieux runs et garde le dernier lisible", async () => {
    const key = forecastKey("graviere");
    for (const run of ["r1", "r2", "r3", "r4"]) {
      await writeForecastCache<Payload>(key, run, { label: run });
    }
    const entry = await readForecastCache<Payload>(key);
    expect(entry?.payload.label).toBe("r4");
  });

  it("rend null sur une clé jamais écrite", async () => {
    expect(await readForecastCache(forecastKey("inconnu"))).toBeNull();
  });
});

describe("péremption", () => {
  it("considère à jour une donnée de moins de deux heures", () => {
    const now = Date.UTC(2026, 8, 13, 12, 0);
    const entry = {
      key: "k",
      run_ts: "r",
      cached_at: now - STALE_MS + 60_000,
      payload: null,
    };
    expect(isStale(entry, now)).toBe(false);
  });

  it("marque périmée une donnée de plus de deux heures", () => {
    const now = Date.UTC(2026, 8, 13, 12, 0);
    const entry = {
      key: "k",
      run_ts: "r",
      cached_at: now - STALE_MS - 1,
      payload: null,
    };
    expect(isStale(entry, now)).toBe(true);
  });

  it("traite l'absence de cache comme périmée", () => {
    expect(isStale(null)).toBe(true);
  });

  it("ne sert plus une entrée vieille d'une semaine", async () => {
    // Une prévision de la semaine dernière n'est pas « un peu vieille », elle
    // est fausse : mieux vaut un écran de chargement.
    const key = forecastKey("graviere");
    // `toFake: ["Date"]` et rien d'autre : IndexedDB s'appuie sur les files de
    // tâches du runtime, et des minuteurs simulés la figeraient.
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-09-01T08:00:00Z"));
    await writeForecastCache<Payload>(key, "vieux", { label: "vieux" });
    vi.setSystemTime(new Date("2026-09-13T08:00:00Z"));

    expect(await readForecastCache<Payload>(key)).toBeNull();
    vi.useRealTimers();
  });
});

describe("âge affiché", () => {
  const now = Date.UTC(2026, 8, 13, 12, 0);

  it("dit « à l'instant » sous la minute", () => {
    expect(ageLabel(now - 30_000, now)).toBe("à l'instant");
  });

  it("compte en minutes sous l'heure", () => {
    expect(ageLabel(now - 40 * 60_000, now)).toBe("il y a 40 min");
  });

  it("écrit « il y a 1 h 40 »", () => {
    expect(ageLabel(now - 100 * 60_000, now)).toBe("il y a 1 h 40");
  });

  it("omet les minutes sur une heure pleine", () => {
    expect(ageLabel(now - 120 * 60_000, now)).toBe("il y a 2 h");
  });

  it("passe aux jours au-delà de vingt-quatre heures", () => {
    expect(ageLabel(now - 50 * 3_600_000, now)).toBe("il y a 2 jours");
  });
});
