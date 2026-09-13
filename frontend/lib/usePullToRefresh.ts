"use client";

import { useEffect, useRef, useState } from "react";

/**
 * « Tirer pour rafraîchir » — le geste qui force la requête (décidé le 13/09).
 *
 * Le cache client sert la prévision sans attendre et ne réinterroge qu'au bout
 * de deux heures. Il faut donc un moyen de dire « non, maintenant » : c'est ce
 * geste, celui qu'on fait sans y penser quand on vient de se garer.
 *
 * Deux précautions qui font la différence entre un geste et une gêne :
 *
 * - **Seulement en haut de page.** Tant que `scrollY > 0`, le doigt fait
 *   défiler, et rien d'autre. Le tableau horaire défile horizontalement : un
 *   mouvement plus horizontal que vertical est laissé au tableau.
 * - **Résistance.** La distance affichée est la racine du déplacement : le
 *   geste freine à mesure qu'on tire, comme partout ailleurs sur le téléphone.
 */

/** Déplacement du doigt, en pixels, à partir duquel le geste part. */
const TRIGGER_PX = 72;
/** Déplacement affiché maximal. */
const MAX_PULL_PX = 88;

export interface PullState {
  /** Hauteur de l'indicateur, en pixels. Zéro = aucun geste en cours. */
  distance: number;
  /** Vrai quand lâcher déclenchera le rafraîchissement. */
  armed: boolean;
}

export function usePullToRefresh(
  onRefresh: () => void,
  enabled = true,
): PullState {
  const [state, setState] = useState<PullState>({ distance: 0, armed: false });
  const origin = useRef<{ x: number; y: number } | null>(null);
  // Le rappel vit dans une ref : sans elle, chaque rendu du parent
  // réabonnerait les trois écouteurs de `touch*` sur la fenêtre.
  const callback = useRef(onRefresh);
  useEffect(() => {
    callback.current = onRefresh;
  }, [onRefresh]);

  useEffect(() => {
    if (!enabled || typeof window === "undefined") return;

    const start = (event: TouchEvent) => {
      if (window.scrollY > 0 || event.touches.length !== 1) {
        origin.current = null;
        return;
      }
      origin.current = {
        x: event.touches[0].clientX,
        y: event.touches[0].clientY,
      };
    };

    const move = (event: TouchEvent) => {
      const from = origin.current;
      if (from === null || event.touches.length !== 1) return;

      const dy = event.touches[0].clientY - from.y;
      const dx = event.touches[0].clientX - from.x;

      // Geste horizontal : c'est le tableau horaire qui défile, pas nous.
      if (Math.abs(dx) > Math.abs(dy)) {
        origin.current = null;
        setState({ distance: 0, armed: false });
        return;
      }
      if (dy <= 0 || window.scrollY > 0) {
        setState({ distance: 0, armed: false });
        return;
      }

      // Résistance : la racine freine le geste à mesure qu'on tire.
      const distance = Math.min(MAX_PULL_PX, Math.sqrt(dy) * 7);
      setState({ distance, armed: dy >= TRIGGER_PX });
    };

    const end = () => {
      if (origin.current !== null && state.armed) callback.current();
      origin.current = null;
      setState({ distance: 0, armed: false });
    };

    // `passive` : on ne fait jamais `preventDefault`, le défilement natif ne
    // doit pas attendre qu'on ait décidé.
    window.addEventListener("touchstart", start, { passive: true });
    window.addEventListener("touchmove", move, { passive: true });
    window.addEventListener("touchend", end);
    window.addEventListener("touchcancel", end);
    return () => {
      window.removeEventListener("touchstart", start);
      window.removeEventListener("touchmove", move);
      window.removeEventListener("touchend", end);
      window.removeEventListener("touchcancel", end);
    };
  }, [enabled, state.armed]);

  return state;
}
