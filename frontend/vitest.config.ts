import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

/**
 * Les tests du front couvrent ce qui **ne se vérifie pas à l'œil**.
 *
 * Trois familles, et aucune n'est là par habitude :
 *
 * 1. **La file hors ligne.** C'est la seule pièce du front qui porte un risque
 *    de perte de données : une notation mise en attente sur le parking et
 *    jamais renvoyée est une session perdue, et une session perdue ne laisse
 *    aucune trace.
 * 2. **Les règles de calcul** — demi-points, heures entamées, échelle de
 *    couleur, âge d'un cache. Des fonctions pures dont une erreur d'un cran ne
 *    se remarque pas à la lecture.
 * 3. **Le cache de prévision**, et lui seul parmi les hooks : c'est lui qui
 *    décide si une requête part ou non, et se tromper veut dire soit un écran
 *    vide sur un réseau de parking, soit une prévision d'hier affichée comme
 *    celle du matin. Les deux sont invisibles en développement.
 *
 * `fake-indexeddb/auto` pose un IndexedDB complet dans Node : le cache et la
 * file sont testés pour de vrai — transactions, clés, persistance — et pas
 * contre un bouchon qui dirait oui à tout.
 *
 * L'environnement est `node` par défaut, parce que c'est plus rapide et que la
 * plupart de ces tests n'ont pas besoin de DOM. Les rares qui en ont un le
 * demandent en tête de fichier, par `@vitest-environment jsdom`.
 */
export default defineConfig({
  // Le même alias que `tsconfig.json` (`@/*` → `./*`). Les tests de `lib`
  // s'en passaient en important en relatif, mais un composant, lui, importe
  // ses voisins en `@/` : sans cet alias, vitest ne sait pas charger le
  // fichier qu'on lui demande de tester.
  resolve: {
    alias: { "@": fileURLToPath(new URL(".", import.meta.url)) },
  },
  test: {
    environment: "node",
    // `components` s'ajoute à `lib` depuis le 14/09 : les pictogrammes maison
    // mettent une clé `pictogram:…` dans `image_url`, et il faut un test qui
    // garantisse qu'elle ne part jamais dans une balise `img`. Cette
    // vérification-là ne se fait qu'en rendant le composant.
    include: [
      "lib/**/*.test.ts",
      "lib/**/*.test.tsx",
      "components/**/*.test.tsx",
    ],
    setupFiles: ["./vitest.setup.ts"],
  },
});
