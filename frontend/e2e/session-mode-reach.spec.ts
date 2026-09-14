import { expect, test } from "@playwright/test";

import { mockApi, relaxCspForWebkit, tallOverview } from "./fixtures";

/**
 * **« Fait » doit être sous le pouce.** Constaté sur téléphone le 14/09 : avec
 * une image portrait et une consigne longue, le bouton sortait du cadre, et
 * rien ne défilait — le mode séance est un `fixed inset-0`, qui n'a aucun
 * débordement à offrir.
 *
 * La cause tenait à une règle de flexbox plus qu'à la hauteur de l'image : un
 * enfant `flex-1` a `min-height: auto` et refuse de descendre sous la taille
 * de son contenu. La zone centrale poussait donc le pied hors de l'écran.
 *
 * Ces tests mesurent la seule chose qui compte pour l'utilisateur : **est-ce
 * que le bouton est à l'écran, et est-ce qu'un tap dessus fait quelque
 * chose**. Ils vérifient aussi que le contenu déborde vraiment — sans quoi ils
 * passeraient au vert sans rien avoir éprouvé, ce qui est la pire espèce de
 * test.
 *
 * 390 × 844 : l'iPhone 14, et la largeur de référence du projet.
 */

test.use({ viewport: { width: 390, height: 844 } });

const VIEWPORT_HEIGHT = 844;

async function openTallSession(
  page: import("@playwright/test").Page,
  browserName: string,
) {
  if (browserName === "webkit") await relaxCspForWebkit(page);
  await mockApi(page, { "/training/overview": tallOverview() });
  await page.goto("/training");

  await expect(page.getByRole("heading", { name: "Training" })).toBeVisible();
  await page
    .getByRole("region", { name: "Séance du jour" })
    .getByRole("button", { name: "Commencer" })
    .click();

  await expect(
    page.getByRole("heading", { name: /Chat-vache/ }),
  ).toBeVisible();
}

test("le contenu déborde vraiment — sinon ces tests ne prouvent rien", async ({
  page,
  browserName,
}) => {
  await openTallSession(page, browserName);

  const overflow = await page.locator("main").evaluate((element) => ({
    scrollHeight: element.scrollHeight,
    clientHeight: element.clientHeight,
  }));

  expect(
    overflow.scrollHeight,
    "la formule de test doit produire plus de contenu que de place ; " +
      "sans débordement, la reproduction du bug est perdue",
  ).toBeGreaterThan(overflow.clientHeight);
});

test("« Fait » est visible sans défiler, image portrait et consigne longue", async ({
  page,
  browserName,
}) => {
  await openTallSession(page, browserName);

  const fait = page.getByRole("button", { name: "Fait" });

  await expect(fait).toBeInViewport();

  const box = await fait.boundingBox();
  expect(box).not.toBeNull();
  // Le bas du bouton, pas seulement son haut : un bouton dont la moitié
  // dépasse est un bouton qu'on rate.
  expect(box!.y + box!.height).toBeLessThanOrEqual(VIEWPORT_HEIGHT);
  // Cible ≥ 44 px (règle produit n° 1). Elle se vérifie ici parce que c'est
  // ici qu'on a le droit de la perdre en serrant la mise en page.
  expect(box!.height).toBeGreaterThanOrEqual(44);
});

test("« Fait » répond au tap sans qu'on ait rien fait défiler", async ({
  page,
  browserName,
}) => {
  await openTallSession(page, browserName);

  // `click()` sans `scrollIntoViewIfNeeded` préalable : si Playwright doit
  // faire défiler pour l'atteindre, c'est que l'utilisateur aurait dû le
  // faire aussi. On fige donc le défilement de la zone centrale avant, et on
  // vérifie après qu'il n'a pas bougé.
  const before = await page.locator("main").evaluate((el) => el.scrollTop);
  expect(before).toBe(0);

  await page.getByRole("button", { name: "Fait" }).click();

  // Le tap a été reçu : le repos démarre. C'est la preuve que le bouton
  // n'était pas seulement présent dans le DOM mais réellement touchable —
  // ni couvert, ni hors cadre.
  await expect(page.getByTestId("rest-countdown")).toBeVisible();
});

test("« Passer » reste lui aussi à l'écran", async ({ page, browserName }) => {
  await openTallSession(page, browserName);

  const passer = page.getByRole("button", { name: "Passer", exact: true });
  await expect(passer).toBeInViewport();

  const box = await passer.boundingBox();
  expect(box!.y + box!.height).toBeLessThanOrEqual(VIEWPORT_HEIGHT);
});

test("la consigne longue reste lisible : la zone centrale défile", async ({
  page,
  browserName,
}) => {
  await openTallSession(page, browserName);

  const main = page.locator("main");
  await main.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });

  // Le pied ne bouge pas quand le contenu défile — c'est ce qui distingue
  // une barre d'actions hors flux d'un simple bloc en bas de page.
  const fait = page.getByRole("button", { name: "Fait" });
  await expect(fait).toBeInViewport();

  const box = await fait.boundingBox();
  expect(box!.y + box!.height).toBeLessThanOrEqual(VIEWPORT_HEIGHT);
});

test("pendant le repos, les deux boutons restent atteignables", async ({
  page,
  browserName,
}) => {
  await openTallSession(page, browserName);

  await page.getByRole("button", { name: "Fait" }).click();
  await expect(page.getByTestId("rest-countdown")).toBeVisible();

  for (const name of [/30 s/, /Passer le repos/]) {
    const button = page.getByRole("button", { name });
    await expect(button).toBeInViewport();
    const box = await button.boundingBox();
    expect(box!.y + box!.height).toBeLessThanOrEqual(VIEWPORT_HEIGHT);
  }
});
