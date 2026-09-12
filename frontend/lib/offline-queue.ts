/**
 * File d'attente hors ligne — la notation d'une session sans réseau.
 *
 * C'est une des règles non négociables du projet : on doit pouvoir noter une
 * session sur le parking de la plage, sans barre de réseau, et que ça parte
 * tout seul au retour (`PROJET.md` §1, règle 6).
 *
 * Trois décisions, et elles tiennent ensemble :
 *
 * 1. **La clé est l'identifiant de session.** Noter deux fois la même session
 *    hors ligne ne met pas deux entrées dans la file : la seconde remplace la
 *    première. C'est la sémantique voulue — la dernière notation gagne — et
 *    c'est gratuit, `put` sur un `keyPath` le fait tout seul.
 * 2. **`flushQueue` reçoit son émetteur en paramètre.** Rien ici ne connaît
 *    `fetch` ni l'API : la file se teste avec une fonction qui compte les
 *    appels, sans serveur ni mock réseau.
 * 3. **Tout échec n'est pas un échec réseau.** Un 404 ou un 422 ne partira
 *    jamais, quel que soit le nombre de tentatives : le garder ferait grossir
 *    la file pour toujours et masquerait les envois qui, eux, peuvent
 *    aboutir. On jette, et on dit pourquoi. Une panne réseau, elle, garde
 *    l'entrée et arrête la passe — l'ordre est préservé.
 *
 * La file ne sert **pas** au chemin rapide (`POST /sessions/quick`) : celui-ci
 * part du raccourci iOS, hors de l'app, et exige le réseau — c'est iOS qui le
 * gère. Et elle ne sert pas aux photos : trois mégaoctets n'ont rien à faire
 * dans IndexedDB à côté de notes de quelques octets.
 */
import type { SessionUpdate } from "./api";

const DB_NAME = "sport-offline";
const DB_VERSION = 1;
const STORE = "pending-ratings";

export interface PendingRating {
  /** L'identifiant de session, en chaîne : c'est la clé du magasin. */
  id: string;
  sessionId: number;
  payload: SessionUpdate;
  queuedAt: number;
  attempts: number;
}

/** Issue d'un envoi, telle que `flushQueue` la comprend. */
export type SendOutcome = "sent" | "retry" | "drop";

export interface FlushResult {
  sent: number;
  /** Restées en file : le réseau est encore absent. */
  kept: number;
  /** Jetées : elles ne partiront jamais (session supprimée, corps refusé). */
  dropped: number;
}

/**
 * IndexedDB peut manquer : navigation privée, stockage bloqué, rendu serveur.
 * L'app doit alors continuer de marcher — en ligne seulement, ce qui est déjà
 * l'essentiel du temps — plutôt que de refuser d'afficher l'écran.
 */
export function isQueueAvailable(): boolean {
  return typeof indexedDB !== "undefined";
}

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: "id" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(new Error("IndexedDB bloqué"));
  });
}

function runTransaction<T>(
  mode: IDBTransactionMode,
  work: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  return openDatabase().then(
    (db) =>
      new Promise<T>((resolve, reject) => {
        const transaction = db.transaction(STORE, mode);
        const request = work(transaction.objectStore(STORE));
        // On attend la fin de la transaction et pas seulement celle de la
        // requête : en écriture, `onsuccess` précède le commit, et fermer la
        // base entre les deux perdrait l'écriture.
        transaction.oncomplete = () => {
          db.close();
          resolve(request.result);
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

/**
 * Met une notation en attente. Une seule entrée par session : re-noter
 * remplace, ce qui est exactement ce qu'on veut.
 */
export async function enqueueRating(
  sessionId: number,
  payload: SessionUpdate,
): Promise<PendingRating> {
  const entry: PendingRating = {
    id: String(sessionId),
    sessionId,
    payload,
    queuedAt: Date.now(),
    attempts: 0,
  };
  await runTransaction("readwrite", (store) => store.put(entry));
  return entry;
}

export async function listPending(): Promise<PendingRating[]> {
  const entries = await runTransaction<PendingRating[]>("readonly", (store) =>
    store.getAll(),
  );
  // Premier arrivé, premier parti : la file est une file.
  return entries.sort((a, b) => a.queuedAt - b.queuedAt);
}

export async function countPending(): Promise<number> {
  return runTransaction<number>("readonly", (store) => store.count());
}

export async function removePending(id: string): Promise<void> {
  await runTransaction("readwrite", (store) => store.delete(id));
}

export async function clearQueue(): Promise<void> {
  await runTransaction("readwrite", (store) => store.clear());
}

/**
 * Vide la file, entrée par entrée, dans l'ordre d'arrivée.
 *
 * `send` décide du sort de chaque entrée. Une entrée `retry` **arrête la
 * passe** : si le réseau est retombé, insister sur les suivantes ne ferait
 * qu'ajouter des échecs, et l'ordre d'envoi a un sens.
 */
export async function flushQueue(
  send: (entry: PendingRating) => Promise<SendOutcome>,
): Promise<FlushResult> {
  if (!isQueueAvailable()) return { sent: 0, kept: 0, dropped: 0 };

  const pending = await listPending();
  let sent = 0;
  let dropped = 0;

  for (let index = 0; index < pending.length; index += 1) {
    const entry = pending[index];
    const outcome = await send(entry);

    if (outcome === "sent") {
      await removePending(entry.id);
      sent += 1;
      continue;
    }

    if (outcome === "drop") {
      await removePending(entry.id);
      dropped += 1;
      continue;
    }

    // Réseau encore absent : on garde celle-ci et toutes les suivantes. Les
    // entrées déjà jetées sont avant `index`, donc plus dans le compte.
    await runTransaction("readwrite", (store) =>
      store.put({ ...entry, attempts: entry.attempts + 1 }),
    );
    return { sent, kept: pending.length - index, dropped };
  }

  return { sent, kept: 0, dropped };
}
