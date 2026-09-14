import type { Page, Route } from "@playwright/test";

/**
 * Un back bouchonné, juste assez riche pour l'écran Training.
 *
 * Les tests navigateur portent sur le front. Brancher un vrai back ferait
 * dépendre le rouge ou le vert d'une migration, d'un semis et d'un réseau —
 * trois choses que `pytest` couvre déjà et beaucoup mieux.
 */

function exercise(id: number, name: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    slug: `ex-${id}`,
    name,
    category: "core",
    muscle_group: "abdos",
    instructions: "Dos plat, respiration lente.",
    image_url: null,
    source: "builtin",
    license: null,
    source_url: null,
    ...extra,
  };
}

function item(
  id: number,
  position: number,
  name: string,
  extra: Record<string, unknown> = {},
) {
  return {
    id,
    position,
    sets: 1,
    reps: null,
    duration_s: null,
    tempo: null,
    rest_s: 0,
    note: null,
    exercise: exercise(id * 10, name),
    ...extra,
  };
}

/**
 * Une formule à trois lignes qui couvre les trois cas du mode séance :
 * un maintien chronométré, un repos entre deux séries, et un exercice compté.
 */
export const FORMULA = {
  id: 1,
  slug: "reveil",
  name: "Réveil",
  duration_min: 8,
  weekly_target: 5,
  principle: "Ouvrir les hanches avant tout le reste.",
  objective_slugs: ["mains-sol"],
  tags: [],
  variant_of: null,
  family: "reveil",
  done_this_week: 0,
  items: [
    item(1, 1, "Gainage ventral", { duration_s: 40, rest_s: 30 }),
    item(2, 2, "Rotation thoracique", { reps: 10, rest_s: 45 }),
    item(3, 3, "Fente avant", { reps: 8, rest_s: 0 }),
  ],
};

/**
 * Une image **portrait**, celle qui cassait l'écran.
 *
 * SVG en `data:` plutôt qu'un fichier : la CSP du site autorise déjà `data:`
 * pour les images, le test ne dépend d'aucun réseau, et le rapport de forme
 * — deux fois plus haut que large — est écrit noir sur blanc plutôt que caché
 * dans un binaire qu'on ne relira jamais.
 */
const PORTRAIT_IMAGE =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="1200">' +
      '<rect width="600" height="1200" fill="#5A8FAB"/>' +
      "</svg>",
  );

/** Une consigne longue — pas un cas tordu : wger en produit de cette taille. */
const LONG_INSTRUCTIONS =
  "Place-toi à quatre pattes, mains sous les épaules et genoux sous les " +
  "hanches, le dos en position neutre. Inspire en creusant légèrement le bas " +
  "du dos et en ouvrant la poitrine vers l'avant, regard à l'horizontale. " +
  "Expire en enroulant la colonne vertèbre par vertèbre, menton vers le " +
  "sternum, en poussant le sol avec les mains. Garde le mouvement lent et " +
  "continu, sans forcer sur les extrêmes, et laisse la respiration donner le " +
  "tempo plutôt que l'inverse.";

/**
 * L'écran Training tel qu'il était quand « Fait » sortait du cadre : une
 * image portrait, un nom long, une consigne longue, et un maintien à lancer.
 *
 * Chaque pièce ajoute de la hauteur, et c'est leur addition qui débordait —
 * pas l'image seule. Un test qui n'en garderait qu'une passerait sans rien
 * prouver.
 */
export function tallOverview() {
  const exercise = {
    id: 10,
    slug: "ex-10",
    name: "Cat Cow Thoracic Mobilisation With Controlled Breathing",
    name_fr: "Chat-vache avec respiration contrôlée et ouverture thoracique",
    category: "mobility",
    muscle_group: "dos",
    group_key: "dos",
    instructions: LONG_INSTRUCTIONS,
    description_fr: LONG_INSTRUCTIONS,
    image_url: PORTRAIT_IMAGE,
    images: [PORTRAIT_IMAGE],
    source: "wger",
    license: "CC BY-SA 4.0",
    source_url: "https://wger.de/",
  };

  const formula = {
    ...FORMULA,
    items: [
      {
        id: 1,
        position: 1,
        sets: 1,
        reps: null,
        duration_s: 40,
        tempo: "3-1-3",
        rest_s: 30,
        note: "Sans forcer sur les extrêmes",
        exercise,
      },
      { ...FORMULA.items[1] },
    ],
  };

  return {
    ...OVERVIEW,
    formulas: [formula],
    proposal: { ...OVERVIEW.proposal, formula, alternatives: [] },
  };
}

export const OVERVIEW = {
  objectives: [
    {
      id: 1,
      slug: "mains-sol",
      name: "Mains au sol",
      measure: "Distance doigts-sol",
      unit: "cm",
      direction: "up" as const,
      target_value: 0,
      start_value: -14,
      current_value: -9,
      ratio: 0.36,
      last_measured_on: "2026-09-10",
      measure_every_days: 21,
      needs_measurement: false,
      measurements: [],
    },
  ],
  formulas: [FORMULA],
  proposal: {
    formula: FORMULA,
    reason: "Trois jours de surf d'affilée : on ouvre, on ne charge pas.",
    alternatives: [],
    surf_streak: 3,
  },
  recent: [],
};

const WORKOUT = {
  id: 42,
  formula_id: 1,
  formula_name: "Réveil",
  formula_family: "reveil",
  started_at: "2026-09-13T07:00:00+00:00",
  ended_at: null,
  completed: false,
  cut_short: false,
  feeling: null,
  notes: null,
  duration_min: null,
  sets: [],
};

const USER = {
  id: 1,
  email: "jules@example.com",
  is_active: true,
  profile: { disciplines: ["surf"], home_spot_id: null },
};

/**
 * Le bouchon parle **la même langue CORS que le vrai back**.
 *
 * Ce n'est pas du zèle : le front appelle l'API en `credentials: "include"`
 * (le jeton vit dans un cookie httpOnly), et dans ce mode le navigateur refuse
 * un `Access-Control-Allow-Origin: *`. Une réponse bouchonnée sans l'origine
 * exacte et sans `allow-credentials` est rejetée exactement comme en
 * production — l'écran reste sur « Chargement… » et le test rougit pour une
 * raison qui n'a rien à voir avec ce qu'il mesure.
 */
function json(route: Route, body: unknown, status = 200) {
  const origin = route.request().headers()["origin"] ?? "*";
  return route.fulfill({
    status,
    contentType: "application/json",
    headers: {
      "access-control-allow-origin": origin,
      "access-control-allow-credentials": "true",
    },
    body: JSON.stringify(body),
  });
}

/** Préflight : le POST d'ouverture de séance en déclenche un. */
function preflight(route: Route) {
  const origin = route.request().headers()["origin"] ?? "*";
  return route.fulfill({
    status: 204,
    headers: {
      "access-control-allow-origin": origin,
      "access-control-allow-credentials": "true",
      "access-control-allow-methods": "GET,POST,PATCH,PUT,DELETE,OPTIONS",
      "access-control-allow-headers": "content-type,authorization",
      "access-control-max-age": "600",
    },
    body: "",
  });
}

/**
 * Retire `upgrade-insecure-requests` de la CSP du document — **pour WebKit
 * seulement**.
 *
 * Chromium exempte les origines de bouclage de la montée en https ; WebKit
 * non, pas même `localhost`. Contre un `next start` en clair, tous les scripts
 * de la page repartent donc en `https://localhost:3100` et échouent en
 * `SSL connect error` : l'écran reste sur « Chargement… » et aucun test ne
 * peut rien mesurer.
 *
 * Ce n'est pas un contournement d'un problème de production — en production
 * tout est déjà en https, la directive n'y a rien à monter. C'est le prix d'un
 * serveur de test en clair, et il se paie ici plutôt qu'en affaiblissant la
 * configuration réelle du site.
 */
export async function relaxCspForWebkit(page: Page): Promise<void> {
  await page.route("**/*", async (route) => {
    if (route.request().resourceType() !== "document") return route.fallback();
    const response = await route.fetch();
    const headers = { ...response.headers() };
    delete headers["content-security-policy"];
    return route.fulfill({ response, headers });
  });
}

/**
 * Branche le bouchon. Tout ce qui n'est pas prévu répond `{}` plutôt que de
 * partir sur le réseau : un test ne doit jamais dépendre d'une API tierce.
 */
export async function mockApi(
  page: Page,
  overrides: Record<string, unknown> = {},
): Promise<void> {
  await page.route("**/api/v1/**", async (route) => {
    if (route.request().method() === "OPTIONS") return preflight(route);

    const url = new URL(route.request().url());
    const path = url.pathname.replace("/api/v1", "");

    if (path in overrides) return json(route, overrides[path]);
    if (path === "/auth/me") return json(route, USER);
    if (path === "/training/overview") return json(route, OVERVIEW);
    if (path === "/training/workouts") return json(route, WORKOUT);
    if (path.startsWith("/training/workouts/")) return json(route, WORKOUT);
    return json(route, {});
  });
}
