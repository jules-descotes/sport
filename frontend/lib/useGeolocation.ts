"use client";

import { useEffect, useState } from "react";

export type GeolocationState =
  | { status: "pending"; position: null }
  | { status: "ready"; position: { lat: number; lon: number } }
  | { status: "denied"; position: null }
  | { status: "unavailable"; position: null };

/**
 * Position du téléphone, avec repli silencieux.
 *
 * Un refus de géolocalisation n'est pas une erreur : l'écran d'accueil se
 * rabat sur le domicile du profil, côté back. On ne bloque jamais l'affichage
 * en attendant le GPS — d'où le délai court et le cache accepté.
 */
export function useGeolocation(): GeolocationState {
  const [state, setState] = useState<GeolocationState>({
    status: "pending",
    position: null,
  });

  useEffect(() => {
    let cancelled = false;
    const resolve = (next: GeolocationState) => {
      if (!cancelled) setState(next);
    };

    if (typeof navigator === "undefined" || !navigator.geolocation) {
      // L'absence d'API est une réponse comme une autre, mais elle est connue
      // tout de suite : on la publie hors du cycle de rendu, comme les deux
      // autres issues, plutôt que de déclencher un rendu en cascade.
      const immediate = setTimeout(
        () => resolve({ status: "unavailable", position: null }),
        0,
      );
      return () => {
        cancelled = true;
        clearTimeout(immediate);
      };
    }

    navigator.geolocation.getCurrentPosition(
      (position) =>
        resolve({
          status: "ready",
          position: {
            lat: position.coords.latitude,
            lon: position.coords.longitude,
          },
        }),
      () => resolve({ status: "denied", position: null }),
      {
        // Sur le parking, une position à 100 m près suffit largement, et une
        // position d'il y a cinq minutes aussi.
        enableHighAccuracy: false,
        timeout: 6_000,
        maximumAge: 300_000,
      },
    );

    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}
