import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { MOVED_ROUTES, TABS, activeTab } from "./navigation";
import { WEBCAM_FRAME_HOSTS, canEmbedWebcam, frameSrcSources } from "./webcam-hosts";

/**
 * La navigation est une **règle produit**, pas une préférence d'écran : cinq
 * entrées, et jamais une sixième (`CLAUDE.md`, règle produit 1). Elle mérite
 * donc un test qui échoue le jour où quelqu'un en ajoute une — moi compris.
 *
 * Les routes sont vérifiées sur le disque plutôt qu'en montant un routeur :
 * ce qui compte est qu'un fichier `page.tsx` existe là où la barre pointe, et
 * que les anciennes adresses redirigent au lieu de rendre un 404.
 */
const APP_DIR = join(__dirname, "..", "app", "(app)");

function pageFor(route: string): string {
  const segments = route === "/" ? [] : route.slice(1).split("/");
  return join(APP_DIR, ...segments, "page.tsx");
}

describe("barre basse", () => {
  it("compte exactement cinq entrées, dans l'ordre décidé le 13/09", () => {
    expect(TABS.map((tab) => tab.label)).toEqual([
      "Jour",
      "Surf",
      "Training",
      "Nutrition",
      "Profil",
    ]);
  });

  it("pointe vers cinq pages qui existent", () => {
    for (const tab of TABS) {
      expect(existsSync(pageFor(tab.href)), `${tab.href} manquante`).toBe(true);
    }
  });

  it("n'expose plus Mer ni Corps comme destination", () => {
    const hrefs = TABS.map((tab) => tab.href);
    expect(hrefs).not.toContain("/mer");
    expect(hrefs).not.toContain("/corps");
  });

  it("souligne l'onglet du chemin courant, et lui seul", () => {
    expect(activeTab("/")).toBe("/");
    expect(activeTab("/surf")).toBe("/surf");
    expect(activeTab("/surf/sessions")).toBe("/surf");
    expect(activeTab("/training")).toBe("/training");
    // Jour ne s'allume pas sous prétexte que tout chemin commence par « / ».
    expect(activeTab("/nutrition")).not.toBe("/");
  });
});

describe("anciennes routes", () => {
  it("redirigent, et vers une page qui existe", () => {
    // Redirections **HTTP**, déclarées dans `next.config.ts` : une page qui
    // appellerait `redirect()` rendrait un 200 de douze kilo-octets qui ne
    // redirige qu'une fois React hydraté.
    const config = readFileSync(join(__dirname, "..", "next.config.ts"), "utf-8");
    expect(config).toContain("MOVED_ROUTES");
    expect(config).toContain("async redirects()");

    for (const [from, to] of Object.entries(MOVED_ROUTES)) {
      // L'ancien chemin n'a plus de page : c'est l'edge qui répond.
      expect(existsSync(pageFor(from)), `${from} ne devrait plus être une page`).toBe(
        false,
      );
      expect(existsSync(pageFor(to)), `${to} devrait exister`).toBe(true);
    }
  });

  it("laisse le lien profond du raccourci iPhone en place", () => {
    // `POST /sessions/quick` rend `/sessions/{id}/noter` : ce chemin est dans
    // les Raccourcis iOS du téléphone, il ne se déplace pas.
    expect(
      existsSync(join(APP_DIR, "sessions", "[id]", "noter", "page.tsx")),
    ).toBe(true);
    expect(existsSync(join(APP_DIR, "sessions", "[id]", "page.tsx"))).toBe(true);
  });
});

describe("hôtes de webcam", () => {
  it("ne déclare que du https dans la frame-src", () => {
    for (const source of frameSrcSources()) {
      expect(source.startsWith("https://")).toBe(true);
    }
    expect(frameSrcSources()).toHaveLength(WEBCAM_FRAME_HOSTS.length);
  });

  it("encadre un hôte autorisé en https", () => {
    expect(canEmbedWebcam("https://www.youtube.com/embed/abc")).toBe(true);
    expect(canEmbedWebcam("https://player.vimeo.com/video/1")).toBe(true);
  });

  it("refuse le clair, l'inconnu et l'illisible", () => {
    // Contenu mixte : le navigateur le bloquerait sans un mot.
    expect(canEmbedWebcam("http://www.youtube.com/embed/abc")).toBe(false);
    expect(canEmbedWebcam("https://webcam.mairie-du-coin.fr/plage")).toBe(false);
    expect(canEmbedWebcam("javascript:alert(1)")).toBe(false);
    expect(canEmbedWebcam("pas une url")).toBe(false);
    expect(canEmbedWebcam(null)).toBe(false);
  });

  it("ne se laisse pas avoir par un domaine qui finit pareil", () => {
    expect(canEmbedWebcam("https://evil-windy.com/cam")).toBe(false);
    expect(canEmbedWebcam("https://windy.com.attaquant.fr/cam")).toBe(false);
  });
});
