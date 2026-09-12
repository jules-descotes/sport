"use client";

import { useEffect } from "react";

/**
 * Enregistrement du service worker. Volontairement minimal au lot 0 : coquille
 * en cache et repli hors ligne. La file d'attente IndexedDB des sessions
 * arrive au lot 2 — c'est elle qui rendra le hors-ligne réellement utile.
 */
export function ServiceWorkerRegister() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    if (process.env.NODE_ENV !== "production") return;

    const register = () => {
      navigator.serviceWorker.register("/sw.js").catch(() => {
        // Un service worker absent ne doit jamais empêcher l'app de tourner.
      });
    };

    if (document.readyState === "complete") register();
    else window.addEventListener("load", register);

    return () => window.removeEventListener("load", register);
  }, []);

  return null;
}
