/**
 * @vitest-environment jsdom
 *
 * Le contrat de `session-timer` tient en une phrase : **rien de ce qui est là
 * ne peut faire tomber le minuteur**. Pas d'exception qui sorte, pas de
 * promesse rejetée qui remonte, pas d'appel bloquant.
 *
 * C'est testé ici et pas seulement dans le navigateur parce que c'est une
 * garantie de code, pas une garantie d'écran : elle doit tenir sur un
 * navigateur qu'on n'a pas, avec une API qu'on n'a pas prévue.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { ScreenLock, SessionAudio, vibrate } from "./session-timer";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SessionAudio", () => {
  it("n'explose pas quand le navigateur refuse l'audio", () => {
    vi.stubGlobal(
      "AudioContext",
      class {
        constructor() {
          throw new Error("NotAllowedError");
        }
      },
    );
    const audio = new SessionAudio();

    expect(() => audio.prime()).not.toThrow();
    expect(() => audio.beep()).not.toThrow();
    expect(() => audio.release()).not.toThrow();
  });

  it("n'explose pas quand l'API n'existe pas du tout", () => {
    vi.stubGlobal("AudioContext", undefined);
    vi.stubGlobal("webkitAudioContext", undefined);
    const audio = new SessionAudio();

    expect(() => audio.prime()).not.toThrow();
    expect(() => audio.beep()).not.toThrow();
  });

  it("n'ouvre qu'un seul contexte pour toute la séance", () => {
    // Safari n'en tolère que quatre par page, et un contexte créé hors geste
    // ne se referme jamais tout seul. En ouvrir un par bip était exactement
    // la façon d'épuiser les quatre au milieu d'une séance.
    const created = vi.fn();
    vi.stubGlobal("AudioContext", fakeContextClass(created));

    const audio = new SessionAudio();
    audio.prime();
    audio.prime();
    audio.beep();
    audio.beep();
    audio.beep();
    audio.beep();
    audio.beep();

    expect(created).toHaveBeenCalledTimes(1);
  });

  it("ne sonne pas tant que le geste n'a pas eu lieu", () => {
    const created = vi.fn();
    vi.stubGlobal("AudioContext", fakeContextClass(created));

    const audio = new SessionAudio();
    audio.beep();

    // Pas de contexte ouvert au débotté : sur iOS il serait `suspended`, donc
    // muet et non refermable.
    expect(created).not.toHaveBeenCalled();
  });
});

describe("ScreenLock", () => {
  it("avale un refus du verrou d'écran", async () => {
    vi.stubGlobal("navigator", {
      wakeLock: { request: () => Promise.reject(new Error("NotAllowedError")) },
    });
    const lock = new ScreenLock();

    expect(() => lock.acquire()).not.toThrow();
    await Promise.resolve();
    expect(() => lock.release()).not.toThrow();
  });

  it("avale une API absente", () => {
    vi.stubGlobal("navigator", {});
    const lock = new ScreenLock();

    expect(() => lock.acquire()).not.toThrow();
    expect(() => lock.release()).not.toThrow();
  });

  it("relâche un verrou arrivé après la fin de la séance", async () => {
    const release = vi.fn().mockResolvedValue(undefined);
    let resolve: (value: unknown) => void = () => undefined;
    vi.stubGlobal("navigator", {
      wakeLock: {
        request: () =>
          new Promise((r) => {
            resolve = r;
          }),
      },
    });

    const lock = new ScreenLock();
    lock.acquire();
    lock.release();
    // Le verrou arrive après coup : sans ce rattrapage, l'écran de Jules
    // resterait allumé jusqu'au rechargement de la page.
    resolve({ release });
    await Promise.resolve();
    await Promise.resolve();

    expect(release).toHaveBeenCalled();
  });
});

describe("vibrate", () => {
  it("ne fait rien là où il n'y a pas de vibreur", () => {
    vi.stubGlobal("navigator", {});
    expect(() => vibrate(200)).not.toThrow();
  });

  it("avale une exception du vibreur", () => {
    vi.stubGlobal("navigator", {
      vibrate: () => {
        throw new Error("nope");
      },
    });
    expect(() => vibrate([120, 60, 120])).not.toThrow();
  });
});

function fakeContextClass(created: () => void) {
  return class {
    state = "running";
    currentTime = 0;
    destination = {};
    constructor() {
      created();
    }
    resume() {
      return Promise.resolve();
    }
    close() {
      return Promise.resolve();
    }
    createOscillator() {
      return {
        type: "",
        frequency: { value: 0 },
        connect: () => undefined,
        disconnect: () => undefined,
        start: () => undefined,
        stop: () => undefined,
        onended: null,
      };
    }
    createGain() {
      return {
        gain: {
          setValueAtTime: () => undefined,
          exponentialRampToValueAtTime: () => undefined,
        },
        connect: () => undefined,
        disconnect: () => undefined,
      };
    }
  };
}
