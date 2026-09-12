import type { NextConfig } from "next";

import { frameSrcSources } from "./lib/webcam-hosts";

/**
 * En-têtes de sécurité du front.
 *
 * Le site est servi en HTTPS de bout en bout (Vercel force déjà la
 * redirection ; `middleware.ts` la double au cas où un chemin lui échapperait).
 * Ce qui manque, et que ces en-têtes apportent :
 *
 * - **HSTS** — un an, sous-domaines compris. Sans lui, la toute première
 *   requête d'un navigateur qui n'a jamais vu le site part en clair, et c'est
 *   celle-là qui porte le cookie de session au retour.
 * - **CSP** — `upgrade-insecure-requests` rattrape une ressource en clair
 *   oubliée plutôt que de la laisser bloquer l'écran, et `frame-src` limite
 *   l'encadrement aux hôtes de webcam déclarés (`lib/webcam-hosts.ts`).
 * - **`frame-ancestors 'none'`** — personne n'encadre l'app. C'est la version
 *   moderne de `X-Frame-Options`, gardé en plus pour les vieux navigateurs.
 * - **`Permissions-Policy`** — la géolocalisation ne sert qu'à nous ; le micro
 *   et la caméra ne servent à personne. Un iframe de webcam ne doit pas
 *   pouvoir demander la position de Jules.
 *
 * `'unsafe-inline'` sur `script-src` n'est pas une négligence : le routeur App
 * de Next injecte son amorce et ses données de flux en scripts en ligne, sans
 * nonce disponible à ce niveau. `'unsafe-eval'` n'est concédé qu'en
 * développement, où le rafraîchissement à chaud en dépend.
 */
const isDev = process.env.NODE_ENV !== "production";

const API_ORIGIN = (() => {
  const url = process.env.NEXT_PUBLIC_API_URL;
  if (!url) return "http://localhost:8000";
  try {
    return new URL(url).origin;
  } catch {
    return "http://localhost:8000";
  }
})();

function contentSecurityPolicy(): string {
  const directives: Record<string, string[]> = {
    "default-src": ["'self'"],
    "base-uri": ["'self'"],
    "object-src": ["'none'"],
    "form-action": ["'self'"],
    "frame-ancestors": ["'none'"],
    "script-src": [
      "'self'",
      "'unsafe-inline'",
      ...(isDev ? ["'unsafe-eval'"] : []),
    ],
    // Tailwind et les styles en ligne de Next.
    "style-src": ["'self'", "'unsafe-inline'"],
    // Les polices sont auto-hébergées par `next/font` : rien d'externe.
    "font-src": ["'self'", "data:"],
    // `https:` pour les photos de session servies par le domaine public R2, et
    // `blob:` pour l'aperçu local avant envoi. Jamais `http:`.
    // `API_ORIGIN` pour les photos servies en local pendant le dev ; en
    // production elles viennent du domaine public R2, donc de `https:`.
    "img-src": ["'self'", "data:", "blob:", "https:", API_ORIGIN],
    "connect-src": ["'self'", API_ORIGIN, ...(isDev ? ["ws:"] : [])],
    // Les iframes de webcam, et elles seules.
    "frame-src": frameSrcSources(),
    "worker-src": ["'self'"],
    "manifest-src": ["'self'"],
  };

  const rendered = Object.entries(directives).map(
    ([name, values]) => `${name} ${values.join(" ")}`,
  );
  // Le filet : une ressource `http:` oubliée est re-demandée en `https:` au
  // lieu d'être bloquée sans un mot.
  rendered.push("upgrade-insecure-requests");
  return rendered.join("; ");
}

const SECURITY_HEADERS = [
  {
    key: "Strict-Transport-Security",
    value: "max-age=31536000; includeSubDomains",
  },
  { key: "Content-Security-Policy", value: contentSecurityPolicy() },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "geolocation=(self), camera=(), microphone=(), payment=()",
  },
  { key: "X-Frame-Options", value: "DENY" },
];

const nextConfig: NextConfig = {
  async headers() {
    return [
      { source: "/:path*", headers: SECURITY_HEADERS },
      {
        // Le service worker doit pouvoir être remplacé sans purge de cache
        // navigateur.
        source: "/sw.js",
        headers: [
          ...SECURITY_HEADERS,
          { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
          { key: "Service-Worker-Allowed", value: "/" },
        ],
      },
    ];
  },
};

export default nextConfig;
