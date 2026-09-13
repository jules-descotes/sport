/**
 * Cache client des prévisions — IndexedDB, clé `(spot, run_ts)`.
 *
 * Décidé le 13/09 après deux jours d'usage : ouvrir Surf sur un réseau de
 * parking de plage montrait un écran vide pendant trois secondes, alors que la
 * prévision de 6 h était déjà connue et n'avait pas bougé. On sert donc **la
 * donnée en cache tout de suite**, et on ne rafraîchit derrière que si elle a
 * plus de deux heures (*stale-while-revalidate*). Le cache serveur de trois
 * heures ne change pas : ce sont deux étages indépendants.
 *
 * Trois décisions valent d'être écrites :
 *
 * 1. **La clé porte `run_ts`, comme en base.** Une prévision n'est pas « la
 *    prévision du spot », c'est « ce qu'on en savait à telle heure ». Deux runs
 *    du même spot coexistent donc ici aussi, et la lecture prend le `run_ts`
 *    maximum — la même règle que `services/forecast_reads.py`, pour la même
 *    raison. Au-delà de `KEEP_RUNS`, les plus vieux sont élagués : le cache
 *    n'est pas un historique, l'historique est en base.
 * 2. **La clé de spot porte aussi la forme demandée.** Un résumé toutes les
 *    trois heures et un tableau heure par heure ne sont pas le même objet ;
 *    servir l'un pour l'autre afficherait une grille à trous. `forecastKey`
 *    est le seul endroit où cette clé se fabrique.
 * 3. **Un cache indisponible n'est jamais une erreur.** Navigation privée,
 *    stockage bloqué, rendu serveur : toutes les fonctions rendent « rien » au
 *    lieu de lever. Une prévision non mise en cache reste une prévision.
 */

const DB_NAME = "sport-forecasts";
const DB_VERSION = 1;
const STORE = "runs";

/** Au-delà, la donnée est rafraîchie en arrière-plan. Elle reste affichée. */
export const STALE_MS = 2 * 60 * 60 * 1000;

/** Runs conservés par spot. Deux suffisent à couvrir un aller-retour. */
const KEEP_RUNS = 2;

/** Au-delà, l'entrée est périmée pour de bon et n'est plus servie. */
const MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

export interface CachedForecast<T> {
  /** Le spot **et** la forme demandée — voir `forecastKey`. */
  key: string;
  /** Heure d'émission du run servi. `""` quand le back n'en a pas donné. */
  run_ts: string;
  /** Quand *nous* l'avons reçue. C'est cette heure que l'écran affiche. */
  cached_at: number;
  payload: T;
}

export function isCacheAvailable(): boolean {
  return typeof indexedDB !== "undefined";
}

/**
 * La clé d'un cache de prévision.
 *
 * `shape` décrit ce qui a été demandé (« 5 jours, pas d'une heure »). Deux
 * formes différentes sont deux entrées différentes, et c'est voulu.
 */
export function forecastKey(spot: string | number, shape = ""): string {
  return shape ? `${spot}|${shape}` : String(spot);
}

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE)) {
        // Clé composite `(key, run_ts)` : deux runs du même spot coexistent,
        // et l'index par spot sert à les relire tous pour prendre le dernier.
        const store = db.createObjectStore(STORE, {
          keyPath: ["key", "run_ts"],
        });
        store.createIndex("by-key", "key", { unique: false });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(new Error("IndexedDB bloqué"));
  });
}

function runTransaction<T>(
  mode: IDBTransactionMode,
  work: (store: IDBObjectStore) => IDBRequest<T> | null,
): Promise<T | null> {
  return openDatabase().then(
    (db) =>
      new Promise<T | null>((resolve, reject) => {
        const transaction = db.transaction(STORE, mode);
        const request = work(transaction.objectStore(STORE));
        transaction.oncomplete = () => {
          db.close();
          resolve(request ? request.result : null);
        };
        transaction.onerror = () => {
          db.close();
          reject(transaction.error);
        };
        transaction.onabort = () => {
          db.close();
          reject(transaction.error);
        };
      }),
  );
}

async function entriesFor<T>(key: string): Promise<CachedForecast<T>[]> {
  const rows = await runTransaction<CachedForecast<T>[]>(
    "readonly",
    (store) => store.index("by-key").getAll(key),
  );
  return rows ?? [];
}

/**
 * La prévision en cache pour cette clé : le run le plus récent, et lui seul.
 *
 * Le classement est fait sur `cached_at` et non sur `run_ts` : un back qui ne
 * rendrait pas de `run_ts` mettrait toutes ses entrées sous la chaîne vide, et
 * le tri retomberait alors sur l'ordre d'arrivée, qui reste juste.
 */
export async function readForecastCache<T>(
  key: string,
): Promise<CachedForecast<T> | null> {
  if (!isCacheAvailable()) return null;
  try {
    const rows = await entriesFor<T>(key);
    const fresh = rows.filter((row) => Date.now() - row.cached_at < MAX_AGE_MS);
    if (fresh.length === 0) return null;
    return fresh.reduce((best, row) =>
      row.run_ts > best.run_ts ||
      (row.run_ts === best.run_ts && row.cached_at > best.cached_at)
        ? row
        : best,
    );
  } catch {
    return null;
  }
}

/** Écrit une prévision et élague les runs en trop pour ce spot. */
export async function writeForecastCache<T>(
  key: string,
  runTs: string | null,
  payload: T,
): Promise<void> {
  if (!isCacheAvailable()) return;
  const entry: CachedForecast<T> = {
    key,
    run_ts: runTs ?? "",
    cached_at: Date.now(),
    payload,
  };
  try {
    await runTransaction("readwrite", (store) => store.put(entry));

    const rows = await entriesFor<T>(key);
    if (rows.length <= KEEP_RUNS) return;
    // Le `run_ts` départage les ex æquo, et ce n'est pas théorique : deux
    // écritures dans la même milliseconde — un rafraîchissement déclenché
    // deux fois — laisseraient sinon l'ordre d'insertion décider, et c'est le
    // run **le plus récent** qui serait élagué.
    const doomed = rows
      .sort(
        (a, b) =>
          b.cached_at - a.cached_at || b.run_ts.localeCompare(a.run_ts),
      )
      .slice(KEEP_RUNS);
    await runTransaction("readwrite", (store) => {
      for (const row of doomed) store.delete([row.key, row.run_ts]);
      return null;
    });
  } catch {
    // Quota plein, stockage refusé : on n'a pas de cache, on a la donnée.
  }
}

/** Vrai quand la donnée mérite un rafraîchissement en arrière-plan. */
export function isStale(
  entry: CachedForecast<unknown> | null,
  now = Date.now(),
): boolean {
  return entry === null || now - entry.cached_at >= STALE_MS;
}

export async function clearForecastCache(): Promise<void> {
  if (!isCacheAvailable()) return;
  try {
    await runTransaction("readwrite", (store) => store.clear());
  } catch {
    // Rien à faire : un cache qu'on ne peut pas vider se périmera tout seul.
  }
}

/**
 * « il y a 1 h 40 » — l'âge d'une donnée en cache, en français.
 *
 * Sous la minute on dit « à l'instant » plutôt que « il y a 0 min » : la
 * seconde n'intéresse personne, et une prévision de la minute précédente est la
 * prévision courante.
 */
export function ageLabel(cachedAt: number, now = Date.now()): string {
  const minutes = Math.max(0, Math.floor((now - cachedAt) / 60_000));
  if (minutes < 1) return "à l'instant";
  if (minutes < 60) return `il y a ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours < 24) {
    return rest === 0 ? `il y a ${hours} h` : `il y a ${hours} h ${rest}`;
  }
  const days = Math.floor(hours / 24);
  return days === 1 ? "il y a 1 jour" : `il y a ${days} jours`;
}
