import { defineConfig } from "vitest/config";

/**
 * Les tests du front couvrent **la file hors ligne**, et elle seule.
 *
 * C'est la seule pièce du front qui porte un risque de perte de données : une
 * notation mise en attente sur le parking et jamais renvoyée est une session
 * perdue, et une session perdue ne laisse aucune trace. Le reste de l'écran se
 * vérifie à l'œil, pas cette file.
 *
 * `fake-indexeddb/auto` pose un IndexedDB complet dans Node : la file est
 * testée pour de vrai — transactions, clés, persistance — et pas contre un
 * bouchon qui dirait oui à tout.
 */
export default defineConfig({
  test: {
    environment: "node",
    include: ["lib/**/*.test.ts"],
    setupFiles: ["./vitest.setup.ts"],
  },
});
