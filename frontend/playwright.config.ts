import { defineConfig, devices } from "@playwright/test";

/**
 * Tests navigateur — ce qui ne se vérifie ni en vitest ni à l'œil.
 *
 * Ils existent pour une raison précise : le 13/09, le **minuteur de séance ne
 * démarrait pas sur iPhone en production**, et rien dans les tests unitaires
 * n'aurait pu le dire. Un minuteur est un objet du navigateur — un intervalle,
 * une horloge, une hydratation, un geste utilisateur. Il se teste dans un
 * navigateur ou il ne se teste pas.
 *
 * L'API est bouchonnée par `page.route` (cf. `e2e/fixtures.ts`) : ces tests
 * portent sur le front, et un back qui tombe ne doit pas les faire rougir.
 *
 * Le serveur est la **vraie construction de production** (`next start`), pas
 * `next dev` : le bug portait justement sur l'hydratation, et le mode
 * développement ne rend pas le même HTML.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? "line" : "list",
  use: {
    baseURL: "http://localhost:3100",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "mobile",
      use: { ...devices["Pixel 7"] },
    },
    {
      // **Le projet qui a trouvé le bug du minuteur.** WebKit est le moteur de
      // Safari, donc celui de l'iPhone : c'est le seul endroit où les limites
      // d'`AudioContext` et le refus du Wake Lock hors geste utilisateur se
      // comportent comme en production.
      //
      // Il n'est pas dans le lot de la CI (`npm run test:e2e`) : WebKit y est
      // plus lent et plus capricieux que Chromium, et une CI qui rougit une
      // fois sur cinq ne se lit plus. Il se lance à la main —
      // `npm run test:e2e:iphone` — et c'est là qu'on va voir avant de croire
      // qu'un bug d'iPhone est corrigé.
      name: "iphone",
      use: { ...devices["iPhone 14"] },
    },
  ],
  webServer: {
    command: "npm run start -- --port 3100",
    url: "http://localhost:3100/login",
    // **Jamais réutilisé, même en local.** `next start` sert la construction
    // qu'il avait au démarrage : un `npm run build` joué pendant qu'il tourne
    // lui laisse un manifeste qui pointe vers des fragments disparus, et les
    // tests échouent alors sur des écrans à moitié rendus — un symptôme qui
    // ressemble à s'y méprendre au bug de minuteur qu'ils sont là pour
    // surveiller. Deux secondes de démarrage valent mieux que cette
    // demi-heure-là.
    reuseExistingServer: false,
    timeout: 180_000,
    env: {
      NEXT_PUBLIC_API_URL: "http://127.0.0.1:8999/api/v1",
      NEXT_PUBLIC_SITE_URL: "http://localhost:3100",
      NEXT_PUBLIC_APP_NAME: "Sport",
    },
  },
});
