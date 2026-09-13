// @vitest-environment jsdom
/**
 * Le *stale-while-revalidate* des prévisions — **stale, revalidate, force**.
 *
 * C'est le seul hook du produit qui mérite un test, et il le mérite vraiment :
 * c'est lui qui décide si une requête part ou non. Se tromper veut dire soit un
 * écran vide sur un réseau de parking, soit la prévision d'hier affichée comme
 * celle du matin — et les deux sont invisibles en développement, où le réseau
 * répond en dix millisecondes.
 *
 * Ce qui est vérifié ici est **le nombre d'appels réseau**, pas le rendu : il
 * n'y a rien à regarder, il y a une décision à prendre.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  STALE_MS,
  clearForecastCache,
  forecastKey,
  writeForecastCache,
} from "./forecast-cache";
import { useCachedForecast } from "./useCachedForecast";

interface Payload {
  run_ts: string;
  label: string;
}

const KEY = forecastKey("graviere", "5d-1h");

function Probe({
  queryFn,
  onRefresh,
}: {
  queryFn: () => Promise<Payload>;
  onRefresh?: (refresh: () => void) => void;
}) {
  const forecast = useCachedForecast<Payload>({
    cacheKey: KEY,
    queryKey: ["probe"],
    queryFn,
    runTs: (data) => data.run_ts,
  });

  onRefresh?.(forecast.refresh);

  return (
    <div>
      <span data-testid="label">{forecast.data?.label ?? "rien"}</span>
      <span data-testid="source">{forecast.source ?? "—"}</span>
    </div>
  );
}

function mount(queryFn: () => Promise<Payload>) {
  let refresh: (() => void) | null = null;
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  const view = render(
    <QueryClientProvider client={client}>
      <Probe
        queryFn={queryFn}
        onRefresh={(handler) => {
          refresh = handler;
        }}
      />
    </QueryClientProvider>,
  );

  return { view, refresh: () => refresh?.() };
}

beforeEach(async () => {
  vi.useRealTimers();
  await clearForecastCache();
});

// Le nettoyage automatique de Testing Library ne s'installe que si les
// globales de vitest sont activées ; elles ne le sont pas ici. Sans cet
// `afterEach`, chaque test s'ajouterait au DOM du précédent et `screen`
// trouverait deux éléments pour un.
afterEach(cleanup);

describe("stale-while-revalidate", () => {
  it("interroge le réseau quand il n'y a rien en cache", async () => {
    const queryFn = vi.fn(async () => ({ run_ts: "r1", label: "réseau" }));

    mount(queryFn);

    await waitFor(() =>
      expect(screen.getByTestId("label").textContent).toBe("réseau"),
    );
    expect(queryFn).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("source").textContent).toBe("network");
  });

  it("sert le cache sans requête quand il a moins de deux heures", async () => {
    // Le cœur du sujet : sur un réseau de parking, la prévision de 6 h est
    // déjà connue et n'a pas bougé. La réafficher ne doit rien coûter.
    await writeForecastCache<Payload>(KEY, "r1", {
      run_ts: "r1",
      label: "en cache",
    });
    const queryFn = vi.fn(async () => ({ run_ts: "r2", label: "réseau" }));

    mount(queryFn);

    await waitFor(() =>
      expect(screen.getByTestId("label").textContent).toBe("en cache"),
    );
    expect(screen.getByTestId("source").textContent).toBe("cache");

    // On laisse une fenêtre : le but est de prouver qu'**aucune** requête ne
    // part, pas qu'elle part plus tard.
    await new Promise((resolve) => setTimeout(resolve, 60));
    expect(queryFn).not.toHaveBeenCalled();
  });

  it("revalide quand la donnée a plus de deux heures", async () => {
    const old = Date.now() - STALE_MS - 60_000;
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(old);
    await writeForecastCache<Payload>(KEY, "r1", {
      run_ts: "r1",
      label: "vieux",
    });
    vi.useRealTimers();

    const queryFn = vi.fn(async () => ({ run_ts: "r2", label: "frais" }));
    mount(queryFn);

    // L'ancienne donnée reste à l'écran pendant la requête — c'est tout
    // l'intérêt du *stale-while-revalidate* : on ne vide jamais l'écran.
    await waitFor(() => expect(queryFn).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.getByTestId("label").textContent).toBe("frais"),
    );
  });

  it("force la requête sur demande, même sur une donnée fraîche", async () => {
    // Le « tirer pour rafraîchir » : seul Jules sait qu'il vient de se garer.
    await writeForecastCache<Payload>(KEY, "r1", {
      run_ts: "r1",
      label: "en cache",
    });
    const queryFn = vi.fn(async () => ({ run_ts: "r2", label: "forcé" }));

    const { refresh } = mount(queryFn);

    await waitFor(() =>
      expect(screen.getByTestId("label").textContent).toBe("en cache"),
    );
    expect(queryFn).not.toHaveBeenCalled();

    await act(async () => {
      refresh();
    });

    await waitFor(() => expect(queryFn).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.getByTestId("label").textContent).toBe("forcé"),
    );
  });

  it("écrit ce qui revient du réseau dans le cache", async () => {
    const queryFn = vi.fn(async () => ({ run_ts: "r9", label: "réseau" }));
    mount(queryFn);

    await waitFor(() =>
      expect(screen.getByTestId("label").textContent).toBe("réseau"),
    );

    const { readForecastCache } = await import("./forecast-cache");
    await waitFor(async () => {
      const entry = await readForecastCache<Payload>(KEY);
      expect(entry?.run_ts).toBe("r9");
    });
  });

  it("garde le cache à l'écran quand le réseau échoue", async () => {
    // Une erreur réseau n'efface pas une prévision qui marche : sur le parking
    // de la plage, c'est le cas normal.
    const old = Date.now() - STALE_MS - 60_000;
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(old);
    await writeForecastCache<Payload>(KEY, "r1", {
      run_ts: "r1",
      label: "en cache",
    });
    vi.useRealTimers();

    const queryFn = vi.fn(async () => {
      throw new Error("réseau indisponible");
    });
    mount(queryFn);

    await waitFor(() => expect(queryFn).toHaveBeenCalled());
    expect(screen.getByTestId("label").textContent).toBe("en cache");
  });
});
