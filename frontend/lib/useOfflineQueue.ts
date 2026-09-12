"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";

import { ApiError, api } from "./api";
import type { SessionUpdate } from "./api";
import {
  type PendingRating,
  type SendOutcome,
  countPending,
  enqueueRating,
  flushQueue,
  isQueueAvailable,
} from "./offline-queue";

/**
 * Le pont entre la file IndexedDB et l'écran.
 *
 * La règle de vidage est ici, et elle tient en une ligne : **une erreur réseau
 * se retente, une erreur de l'API se jette.** Garder une notation qui a reçu
 * un 404 la ferait rejouer à chaque retour de réseau, pour toujours, en
 * masquant au passage les envois qui pourraient aboutir.
 */
async function sendRating(entry: PendingRating): Promise<SendOutcome> {
  try {
    await api.updateSession(entry.sessionId, entry.payload);
    return "sent";
  } catch (error) {
    // `status === 0` est notre code maison pour « pas de réseau » : c'est le
    // seul cas où réessayer a un sens.
    if (error instanceof ApiError && error.status === 0) return "retry";
    // 401 : la session de navigateur a expiré. Ce n'est pas définitif — on
    // garde, la notation repartira après la reconnexion.
    if (error instanceof ApiError && error.status === 401) return "retry";
    return "drop";
  }
}

export interface OfflineQueueState {
  /** Nombre de notations en attente d'envoi. */
  pending: number;
  /** Met une notation en file et rend `true` si elle y est bien entrée. */
  queue: (sessionId: number, payload: SessionUpdate) => Promise<boolean>;
  /** Tente de vider la file. Sans effet s'il n'y a rien. */
  flush: () => Promise<void>;
}

export function useOfflineQueue(): OfflineQueueState {
  const queryClient = useQueryClient();
  const [pending, setPending] = useState(0);

  const refreshCount = useCallback(async () => {
    if (!isQueueAvailable()) return;
    try {
      setPending(await countPending());
    } catch {
      // Stockage bloqué (navigation privée) : l'app marche en ligne, et
      // l'indicateur se tait plutôt que d'afficher une erreur qu'on ne peut
      // pas corriger depuis cet écran.
      setPending(0);
    }
  }, []);

  const flush = useCallback(async () => {
    if (!isQueueAvailable()) return;
    try {
      const result = await flushQueue(sendRating);
      if (result.sent > 0 || result.dropped > 0) {
        // Ce qui vient de partir doit se voir : l'historique et l'écran Jour
        // portaient encore l'état d'avant l'envoi.
        queryClient.invalidateQueries({ queryKey: ["sessions"] });
        queryClient.invalidateQueries({ queryKey: ["session-journal"] });
      }
    } catch {
      // Rien à faire de plus : la file garde son contenu et retentera.
    }
    await refreshCount();
  }, [queryClient, refreshCount]);

  const queue = useCallback(
    async (sessionId: number, payload: SessionUpdate) => {
      if (!isQueueAvailable()) return false;
      try {
        await enqueueRating(sessionId, payload);
        await refreshCount();
        return true;
      } catch {
        return false;
      }
    },
    [refreshCount],
  );

  useEffect(() => {
    const run = () => void flush();

    // `online` est l'événement qui compte : il se déclenche quand on remonte
    // du parking vers la route. `visibilitychange` rattrape le cas — fréquent
    // sur iOS — où l'app revient de l'arrière-plan sans que `online` ne parte.
    const onVisible = () => {
      if (document.visibilityState === "visible") run();
    };

    window.addEventListener("online", run);
    document.addEventListener("visibilitychange", onVisible);

    // Première passe différée d'un tour de boucle, et pas appelée dans le
    // corps de l'effet. Deux raisons, la seconde étant la vraie : ouvrir
    // IndexedDB et lire la file n'a pas à retarder le premier rendu, et un
    // `setState` synchrone dans un effet déclenche des rendus en cascade.
    const kickoff = window.setTimeout(run, 0);

    return () => {
      window.clearTimeout(kickoff);
      window.removeEventListener("online", run);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [flush]);

  return { pending, queue, flush };
}
