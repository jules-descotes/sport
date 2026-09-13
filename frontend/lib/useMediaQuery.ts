"use client";

import { useSyncExternalStore } from "react";

/**
 * Lecture d'une media query, sans décalage d'hydratation.
 *
 * `useSyncExternalStore` sert exactement ce cas : l'instantané serveur est
 * fixe (`false`), l'instantané client est lu au premier rendu du navigateur, et
 * React fait la bascule lui-même. Un `useEffect` qui poserait l'état après coup
 * afficherait une mise en page mobile pendant une frame sur un écran de
 * 1600 px — visible, et pénible sur un écran qu'on rouvre toute la journée.
 */
function subscribe(query: string) {
  return (onChange: () => void) => {
    if (typeof window === "undefined" || !window.matchMedia) return () => {};
    const list = window.matchMedia(query);
    list.addEventListener("change", onChange);
    return () => list.removeEventListener("change", onChange);
  };
}

export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    subscribe(query),
    () =>
      typeof window !== "undefined" && window.matchMedia
        ? window.matchMedia(query).matches
        : false,
    // Côté serveur, on rend le mobile : c'est la mise en page de référence, et
    // c'est celle qui se dégrade le mieux si le JS n'arrive jamais.
    () => false,
  );
}

/**
 * Le seuil du produit — 1024 px.
 *
 * C'est le même que celui du thème (`globals.css` bascule en sombre au-dessus),
 * et ce n'est pas un hasard : au-dessus de 1024 px on est assis devant un écran
 * avec une souris, en dessous on est debout avec un pouce. Les deux règles
 * suivent la même frontière, et il n'y en a qu'une à retenir.
 */
export function useIsDesktop(): boolean {
  return useMediaQuery("(min-width: 1024px)");
}
