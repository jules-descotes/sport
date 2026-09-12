/**
 * File hors ligne — la seule pièce du front qui peut perdre une session.
 *
 * Une notation mise en attente sur le parking et jamais renvoyée ne laisse
 * aucune trace : personne ne s'en apercevra, et c'est exactement ce qui rend
 * ce code-là digne de tests alors que le reste de l'écran se vérifie à l'œil.
 *
 * IndexedDB est réel ici (`fake-indexeddb`), pas bouché : transactions, clés
 * et persistance sont éprouvées pour de bon.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  type PendingRating,
  type SendOutcome,
  clearQueue,
  countPending,
  enqueueRating,
  flushQueue,
  isQueueAvailable,
  listPending,
  removePending,
} from "./offline-queue";

beforeEach(async () => {
  await clearQueue();
});

describe("mise en file", () => {
  it("garde la notation telle quelle", async () => {
    await enqueueRating(12, { rating_conditions: 4, rating_personal: 3 });

    const pending = await listPending();
    expect(pending).toHaveLength(1);
    expect(pending[0].sessionId).toBe(12);
    expect(pending[0].payload).toEqual({
      rating_conditions: 4,
      rating_personal: 3,
    });
    expect(pending[0].attempts).toBe(0);
  });

  it("survit à la fermeture de la base", async () => {
    // Chaque appel rouvre la base : si la transaction d'écriture n'était pas
    // attendue jusqu'au commit, l'entrée disparaîtrait ici.
    await enqueueRating(12, { rating_conditions: 4 });
    expect(await countPending()).toBe(1);
  });

  it("re-noter la même session remplace, sans doubler la file", async () => {
    // La clé est l'identifiant de session : la dernière notation gagne. Deux
    // entrées pour une session enverraient deux PATCH, dont le premier serait
    // aussitôt écrasé par le second.
    await enqueueRating(12, { rating_conditions: 2, rating_personal: 2 });
    await enqueueRating(12, { rating_conditions: 5, rating_personal: 4 });

    const pending = await listPending();
    expect(pending).toHaveLength(1);
    expect(pending[0].payload.rating_conditions).toBe(5);
  });

  it("garde des sessions distinctes distinctes", async () => {
    await enqueueRating(12, { rating_conditions: 2 });
    await enqueueRating(13, { rating_conditions: 4 });

    expect(await countPending()).toBe(2);
  });

  it("rend la file dans l'ordre d'arrivée", async () => {
    // `toFake: ["Date"]` et pas le jeu complet : IndexedDB planifie ses
    // événements avec `setImmediate`, et geler les minuteries gèlerait la
    // base — les transactions n'aboutiraient jamais. Seule l'horloge est
    // truquée, ce qui est tout ce dont ce test a besoin.
    vi.useFakeTimers({ toFake: ["Date"] });
    try {
      vi.setSystemTime(new Date("2026-09-12T08:00:00Z"));
      await enqueueRating(20, { rating_conditions: 1 });
      vi.setSystemTime(new Date("2026-09-12T09:00:00Z"));
      await enqueueRating(10, { rating_conditions: 2 });

      const pending = await listPending();
      // Par date de mise en file, pas par identifiant de session.
      expect(pending.map((entry) => entry.sessionId)).toEqual([20, 10]);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("vidage au retour du réseau", () => {
  it("envoie et retire chaque notation", async () => {
    await enqueueRating(12, { rating_conditions: 4, rating_personal: 3 });
    await enqueueRating(13, { rating_conditions: 5, rating_personal: 5 });

    const sent: number[] = [];
    const result = await flushQueue(async (entry) => {
      sent.push(entry.sessionId);
      return "sent";
    });

    expect(result).toEqual({ sent: 2, kept: 0, dropped: 0 });
    expect(sent).toEqual([12, 13]);
    expect(await countPending()).toBe(0);
  });

  it("garde tout et s'arrête dès que le réseau retombe", async () => {
    // Insister sur les suivantes n'ajouterait que des échecs, et l'ordre
    // d'envoi a un sens.
    await enqueueRating(12, { rating_conditions: 4 });
    await enqueueRating(13, { rating_conditions: 5 });
    await enqueueRating(14, { rating_conditions: 3 });

    const attempted: number[] = [];
    const result = await flushQueue(async (entry) => {
      attempted.push(entry.sessionId);
      return "retry";
    });

    expect(attempted).toEqual([12]);
    expect(result).toEqual({ sent: 0, kept: 3, dropped: 0 });
    expect(await countPending()).toBe(3);
  });

  it("compte juste quand le réseau lâche en cours de route", async () => {
    await enqueueRating(12, { rating_conditions: 4 });
    await enqueueRating(13, { rating_conditions: 5 });
    await enqueueRating(14, { rating_conditions: 3 });

    const result = await flushQueue(async (entry) =>
      entry.sessionId === 12 ? "sent" : "retry",
    );

    expect(result).toEqual({ sent: 1, kept: 2, dropped: 0 });
    expect((await listPending()).map((entry) => entry.sessionId)).toEqual([
      13, 14,
    ]);
  });

  it("compte les tentatives de celle qui bloque", async () => {
    await enqueueRating(12, { rating_conditions: 4 });

    await flushQueue(async () => "retry");
    await flushQueue(async () => "retry");

    const pending = await listPending();
    expect(pending[0].attempts).toBe(2);
  });

  it("jette une notation que l'API refuse définitivement", async () => {
    // Session supprimée, corps invalide : la garder ferait rejouer l'échec à
    // chaque retour de réseau, pour toujours, en masquant les envois qui,
    // eux, peuvent aboutir.
    await enqueueRating(12, { rating_conditions: 4 });
    await enqueueRating(13, { rating_conditions: 5 });

    const result = await flushQueue(async (entry) =>
      entry.sessionId === 12 ? "drop" : "sent",
    );

    expect(result).toEqual({ sent: 1, kept: 0, dropped: 1 });
    expect(await countPending()).toBe(0);
  });

  it("reprend là où elle en était à la passe suivante", async () => {
    await enqueueRating(12, { rating_conditions: 4 });
    await enqueueRating(13, { rating_conditions: 5 });

    // Sur le parking : rien ne part.
    await flushQueue(async () => "retry");
    expect(await countPending()).toBe(2);

    // De retour sur la route.
    const outcomes: SendOutcome[] = [];
    const result = await flushQueue(async (entry: PendingRating) => {
      outcomes.push("sent");
      expect(entry.payload).toBeTruthy();
      return "sent";
    });

    expect(result.sent).toBe(2);
    expect(outcomes).toHaveLength(2);
    expect(await countPending()).toBe(0);
  });

  it("ne fait rien sur une file vide", async () => {
    const send = vi.fn(async () => "sent" as SendOutcome);
    const result = await flushQueue(send);

    expect(send).not.toHaveBeenCalled();
    expect(result).toEqual({ sent: 0, kept: 0, dropped: 0 });
  });
});

describe("retrait manuel", () => {
  it("retire par identifiant de session", async () => {
    await enqueueRating(12, { rating_conditions: 4 });
    await removePending("12");
    expect(await countPending()).toBe(0);
  });
});

describe("stockage indisponible", () => {
  it("se déclare disponible quand IndexedDB existe", () => {
    expect(isQueueAvailable()).toBe(true);
  });

  it("ne vide rien quand IndexedDB manque", async () => {
    // Navigation privée, stockage bloqué : l'app doit continuer de marcher en
    // ligne plutôt que de refuser d'afficher l'écran.
    const real = globalThis.indexedDB;
    // @ts-expect-error — on simule l'absence complète de l'API.
    delete globalThis.indexedDB;
    try {
      expect(isQueueAvailable()).toBe(false);
      expect(await flushQueue(async () => "sent")).toEqual({
        sent: 0,
        kept: 0,
        dropped: 0,
      });
    } finally {
      globalThis.indexedDB = real;
    }
  });
});
