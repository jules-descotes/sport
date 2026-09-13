import { expect, test } from "@playwright/test";

import { mockApi, relaxCspForWebkit } from "./fixtures";

/**
 * **Le minuteur de séance.** Constaté en production sur iPhone le 13/09 :
 * il ne démarrait pas.
 *
 * Ces tests reproduisent le geste exact — ouvrir le mode séance, lancer un
 * maintien, laisser tourner — avec l'horloge du navigateur sous contrôle
 * (`page.clock`). C'est la seule façon de vérifier un compte à rebours sans
 * attendre quarante secondes par assertion, et c'est aussi ce qui permet de
 * simuler un passage en arrière-plan : on avance l'horloge d'un coup, sans
 * qu'aucun battement d'intervalle n'ait eu lieu.
 */

async function openSessionMode(
  page: import("@playwright/test").Page,
  browserName: string,
) {
  if (browserName === "webkit") await relaxCspForWebkit(page);
  await mockApi(page);
  // L'horloge est posée **avant** le chargement : un `setInterval` armé
  // pendant l'hydratation doit lui aussi être sous contrôle.
  await page.clock.install({ time: new Date("2026-09-13T07:00:00Z") });
  await page.goto("/training");

  await expect(page.getByRole("heading", { name: "Training" })).toBeVisible();
  await page
    .getByRole("region", { name: "Séance du jour" })
    .getByRole("button", { name: "Commencer" })
    .click();

  await expect(
    page.getByRole("heading", { name: "Gainage ventral" }),
  ).toBeVisible();
}

test("le minuteur de maintien décompte", async ({ page, browserName }) => {
  await openSessionMode(page, browserName);

  await page.getByRole("button", { name: "Lancer le minuteur" }).click();

  const countdown = page.getByTestId("hold-countdown");
  await expect(countdown).toHaveText("40");

  await page.clock.runFor(5_000);
  await expect(countdown).toHaveText("35");

  await page.clock.runFor(10_000);
  await expect(countdown).toHaveText("25");
});

test("le minuteur de maintien va jusqu'au bout et s'efface", async ({
  page,
  browserName,
}) => {
  await openSessionMode(page, browserName);

  await page.getByRole("button", { name: "Lancer le minuteur" }).click();
  await expect(page.getByTestId("hold-countdown")).toBeVisible();

  await page.clock.runFor(41_000);

  await expect(page.getByTestId("hold-countdown")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Lancer le minuteur" }),
  ).toBeVisible();
});

test("le repos décompte et rend la main à l'exercice suivant", async ({
  page,
  browserName,
}) => {
  await openSessionMode(page, browserName);

  await page.getByRole("button", { name: "Fait" }).click();

  const rest = page.getByTestId("rest-countdown");
  await expect(rest).toHaveText("30");
  await expect(page.getByText("Ensuite : Rotation thoracique")).toBeVisible();

  await page.clock.runFor(10_000);
  await expect(rest).toHaveText("20");

  await page.clock.runFor(21_000);

  // Fin du repos : l'exercice suivant reprend l'écran.
  await expect(rest).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "Rotation thoracique" }),
  ).toBeVisible();
  await expect(page.getByText("10 répétitions")).toBeVisible();
});

test("le minuteur survit à un passage en arrière-plan", async ({ page, browserName }) => {
  await openSessionMode(page, browserName);

  await page.getByRole("button", { name: "Fait" }).click();
  await expect(page.getByTestId("rest-countdown")).toHaveText("30");

  // L'onglet passe derrière : plus aucun battement, l'horloge avance quand
  // même. Au retour, le reste doit être recalculé depuis l'échéance — pas
  // depuis les battements perdus.
  await page.clock.pauseAt(new Date("2026-09-13T07:00:20Z"));
  await page.clock.resume();

  await expect(page.getByTestId("rest-countdown")).toHaveText("10");
});

test("+30 s rallonge le repos en cours", async ({ page, browserName }) => {
  await openSessionMode(page, browserName);

  await page.getByRole("button", { name: "Fait" }).click();
  await page.clock.runFor(10_000);
  await expect(page.getByTestId("rest-countdown")).toHaveText("20");

  await page.getByRole("button", { name: /30 s/ }).click();
  await expect(page.getByTestId("rest-countdown")).toHaveText("50");
});

test("passer le repos rend la main tout de suite", async ({ page, browserName }) => {
  await openSessionMode(page, browserName);

  await page.getByRole("button", { name: "Fait" }).click();
  await expect(page.getByTestId("rest-countdown")).toBeVisible();

  await page.getByRole("button", { name: "Passer le repos" }).click();

  await expect(page.getByTestId("rest-countdown")).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "Rotation thoracique" }),
  ).toBeVisible();
});

test("un navigateur qui refuse le son et l'écran allumé laisse le minuteur tourner", async ({
  page,
  browserName,
}) => {
  // La règle du 13/09, mot pour mot : « s'ils échouent, le minuteur tourne
  // quand même, sans son — jamais l'inverse. »
  await page.addInitScript(() => {
    class RefusingAudioContext {
      constructor() {
        throw new Error("NotAllowedError: gesture required");
      }
    }
    Object.defineProperty(window, "AudioContext", {
      value: RefusingAudioContext,
      configurable: true,
    });
    Object.defineProperty(window, "webkitAudioContext", {
      value: RefusingAudioContext,
      configurable: true,
    });
    Object.defineProperty(navigator, "wakeLock", {
      value: {
        request: () => Promise.reject(new Error("NotAllowedError")),
      },
      configurable: true,
    });
  });

  await openSessionMode(page, browserName);

  await page.getByRole("button", { name: "Fait" }).click();

  const rest = page.getByTestId("rest-countdown");
  await expect(rest).toHaveText("30");
  await page.clock.runFor(12_000);
  await expect(rest).toHaveText("18");

  await page.clock.runFor(19_000);
  await expect(
    page.getByRole("heading", { name: "Rotation thoracique" }),
  ).toBeVisible();
});

test("le minuteur reprend depuis son échéance après un passage en arrière-plan", async ({
  page,
  browserName,
}) => {
  await openSessionMode(page, browserName);

  await page.getByRole("button", { name: "Fait" }).click();
  await expect(page.getByTestId("rest-countdown")).toHaveText("30");

  // iOS **suspend** `setInterval` quand la page passe derrière — il ne le
  // ralentit pas. On simule exactement ça : `setSystemTime` avance l'horloge
  // sans déclencher un seul battement.
  await page.evaluate(() => {
    Object.defineProperty(document, "visibilityState", {
      value: "hidden",
      configurable: true,
    });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await page.clock.setSystemTime(new Date("2026-09-13T07:00:18Z"));

  // Aucun battement n'a eu lieu : l'affichage est resté sur sa dernière
  // valeur connue. C'est le chiffre figé qu'on lit comme un minuteur arrêté.
  await expect(page.getByTestId("rest-countdown")).toHaveText("30");

  await page.evaluate(() => {
    Object.defineProperty(document, "visibilityState", {
      value: "visible",
      configurable: true,
    });
    document.dispatchEvent(new Event("visibilitychange"));
  });

  // Recalculé depuis l'échéance — 12, et pas « 30 moins les quelques
  // battements qui ont vraiment eu lieu ». C'est la règle du 13/09 : à la
  // reprise, on relit l'horloge, on ne compte pas les ticks.
  await expect(page.getByTestId("rest-countdown")).toHaveText("12");
});
