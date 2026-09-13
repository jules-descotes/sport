"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";

import {
  STALE_MS,
  readForecastCache,
  writeForecastCache,
} from "./forecast-cache";

/**
 * *Stale-while-revalidate* sur une prévision — décidé le 13/09.
 *
 * L'écran affiche **tout de suite** ce qu'IndexedDB a gardé, puis ne
 * réinterroge le back que si cette donnée a plus de deux heures. En dessous, on
 * ne bouge pas : la prévision d'un run donné ne change pas, et remplacer un
 * écran déjà juste par le même écran coûte une requête et une seconde d'attente
 * pour rien.
 *
 * **La mécanique passe par TanStack Query, pas à côté.** L'entrée d'IndexedDB
 * est injectée dans son cache avec son `updatedAt` d'origine, et `staleTime`
 * vaut les deux heures. À partir de là c'est la bibliothèque qui tranche :
 * donnée fraîche, aucun appel ; donnée périmée, appel en arrière-plan pendant
 * que l'ancienne reste à l'écran ; `refetch()`, appel immédiat. Un état
 * parallèle « ce que j'ai en cache » aurait deux sources de vérité pour la
 * même donnée, et elles auraient fini par diverger.
 *
 * La requête est **désactivée tant qu'IndexedDB n'a pas répondu** : la lancer
 * avant reviendrait à n'avoir aucun cache, puisqu'elle partirait toujours.
 *
 * `refresh()` court-circuite le délai — c'est ce que branche le « tirer pour
 * rafraîchir ». La décision reste à l'utilisateur : lui seul sait qu'il vient
 * de descendre de voiture et veut la dernière passe.
 */
interface Options<T> {
  /** Clé de cache (`forecastKey`). `null` = rien à lire ni à écrire. */
  cacheKey: string | null;
  queryKey: readonly unknown[];
  queryFn: () => Promise<T>;
  /** Le `run_ts` du payload — il entre dans la clé, comme en base. */
  runTs: (data: T) => string | null;
  enabled?: boolean;
  /**
   * Vrai tant que le back complète en arrière-plan : la requête est alors
   * relancée à intervalle jusqu'à ce qu'il ait fini.
   */
  keepPolling?: (data: T) => boolean;
  refetchInterval?: number;
}

export interface CachedForecastResult<T> {
  data: T | undefined;
  /** D'où vient ce qui est à l'écran. `null` : il n'y a rien encore. */
  source: "cache" | "network" | null;
  /** Quand la donnée affichée a été reçue. Sert à l'indicateur d'âge. */
  cachedAt: number | null;
  /** Vrai tant qu'on n'a **rien** à montrer, ni cache ni réseau. */
  isPending: boolean;
  /** Vrai pendant un aller-retour, cache affiché ou non. */
  isFetching: boolean;
  error: unknown;
  refresh: () => void;
}

export function useCachedForecast<T>({
  cacheKey,
  queryKey,
  queryFn,
  runTs,
  enabled = true,
  keepPolling,
  refetchInterval = 6_000,
}: Options<T>): CachedForecastResult<T> {
  const queryClient = useQueryClient();
  /**
   * Ce qui a été lu d'IndexedDB : pour quelle clé, et à quelle heure l'entrée
   * injectée avait été reçue. Un état et non une ref, parce que le rendu s'en
   * sert — c'est lui qui distingue « ça vient du cache » de « ça vient du
   * réseau ». `null` : la lecture n'a pas encore répondu.
   */
  const [seed, setSeed] = useState<{ key: string | null; at: number | null } | null>(
    null,
  );
  const ready = seed !== null && seed.key === cacheKey;

  // Clé sérialisée : `queryKey` est un tableau reconstruit à chaque rendu, on
  // ne peut pas le mettre tel quel en dépendance d'effet.
  const serializedKey = JSON.stringify(queryKey);

  useEffect(() => {
    let cancelled = false;
    const key = cacheKey;
    // Toujours asynchrone, même sans clé : c'est ce qui garantit que l'état
    // ne bouge jamais pendant le corps de l'effet.
    (key === null ? Promise.resolve(null) : readForecastCache<T>(key)).then(
      (entry) => {
        if (cancelled) return;
        if (entry !== null) {
          // On injecte l'entrée avec son heure d'origine : c'est elle qui
          // rendra la donnée périmée au bout de deux heures, pas maintenant.
          queryClient.setQueryData(queryKey, entry.payload, {
            updatedAt: entry.cached_at,
          });
        }
        setSeed({ key, at: entry?.cached_at ?? null });
      },
    );

    return () => {
      cancelled = true;
    };
    // `queryKey` est couvert par `serializedKey`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cacheKey, serializedKey, queryClient]);

  const query = useQuery({
    queryKey,
    queryFn,
    enabled: enabled && ready,
    // Le cœur du *stale-while-revalidate* : en dessous de deux heures, la
    // donnée est considérée à jour et aucune requête ne part.
    staleTime: STALE_MS,
    refetchInterval: (item) =>
      keepPolling && item.state.data !== undefined && keepPolling(item.state.data)
        ? refetchInterval
        : false,
  });

  const received = query.dataUpdatedAt;
  const seededAt = seed?.at ?? null;
  const fromCache = received !== 0 && received === seededAt;

  // Écriture du cache : au retour d'une **réponse réseau**, et là seulement.
  // Réécrire ce qu'on vient d'injecter ne ferait que repousser sa date de
  // péremption sans que rien n'ait été vérifié.
  useEffect(() => {
    if (cacheKey === null || query.data === undefined) return;
    if (received === 0 || received === seededAt) return;
    void writeForecastCache(cacheKey, runTs(query.data), query.data);
    // `runTs` est une fonction fournie à l'appel : la mettre en dépendance
    // relancerait l'effet à chaque rendu du parent.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cacheKey, received, seededAt, query.data]);

  const refresh = useCallback(() => {
    if (query.isFetching) return;
    void query.refetch();
  }, [query]);

  return {
    data: query.data,
    source: query.data === undefined ? null : fromCache ? "cache" : "network",
    cachedAt: received === 0 ? null : received,
    isPending: query.data === undefined && (!ready || query.isPending),
    isFetching: query.isFetching,
    // Une erreur réseau n'efface pas un cache qui marche : on ne la remonte
    // que s'il n'y a rien à afficher.
    error: query.data === undefined ? query.error : null,
    refresh,
  };
}
