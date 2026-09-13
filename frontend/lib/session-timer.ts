/**
 * Le son, la vibration et l'écran allumé du mode séance — et la règle qui les
 * gouverne.
 *
 * **Un minuteur qui se tait vaut mieux qu'un minuteur qui ne tourne pas.**
 * Tout ce qui est ici est optionnel, faillible, et posé à côté du minuteur,
 * jamais devant lui : aucune de ces fonctions ne rend de promesse que le
 * minuteur devrait attendre, et aucune ne peut lever.
 *
 * Pourquoi un module à part plutôt que trois fonctions dans le composant :
 * sur iOS, **le son exige un geste de l'utilisateur**, et un `AudioContext`
 * créé hors geste démarre `suspended`. Or un contexte suspendu ne termine
 * jamais son oscillateur, donc ne se referme jamais — et Safari n'en tolère
 * que quatre par page. Au cinquième repos, `new AudioContext()` lève, le bip
 * disparaît sans un mot, et on cherche le bug dans le minuteur.
 *
 * D'où **un seul contexte pour toute la séance**, ouvert et réveillé au
 * premier geste, réutilisé ensuite.
 */

type AudioCtor = typeof AudioContext;

function audioCtor(): AudioCtor | null {
  if (typeof window === "undefined") return null;
  return (
    window.AudioContext ??
    (window as unknown as { webkitAudioContext?: AudioCtor })
      .webkitAudioContext ??
    null
  );
}

/**
 * Le son de la séance. Un seul contexte, réveillé au premier geste.
 *
 * `prime()` se appelle depuis un gestionnaire de clic **réel** : c'est le seul
 * moment où iOS accepte de démarrer l'audio. Tout échec est avalé — la séance
 * continue en silence.
 */
export class SessionAudio {
  private context: AudioContext | null = null;
  private primed = false;

  /** À appeler dans le gestionnaire du premier tap. Jamais `await`é. */
  prime(): void {
    if (this.primed) return;
    this.primed = true;
    try {
      const Ctor = audioCtor();
      if (!Ctor) return;
      this.context = new Ctor();
      // Un contexte créé sous geste est déjà `running` ; hors geste il est
      // `suspended` et `resume()` échoue — silencieusement, et c'est voulu.
      void this.context.resume?.().catch(() => undefined);
      // Un souffle inaudible : sur iOS, c'est ce qui « débloque » vraiment la
      // sortie audio. Sans lui, le premier bip utile part dans le vide.
      this.tone(0.0001, 0.01);
    } catch {
      this.context = null;
    }
  }

  /** Le bip de fin de repos. Sans contexte réveillé : rien, et c'est tout. */
  beep(): void {
    this.tone(0.25, 0.35);
  }

  private tone(volume: number, seconds: number): void {
    const context = this.context;
    if (!context) return;
    try {
      if (context.state === "suspended") {
        void context.resume?.().catch(() => undefined);
      }
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      oscillator.type = "sine";
      oscillator.frequency.value = 880;
      const now = context.currentTime;
      gain.gain.setValueAtTime(0.0001, now);
      gain.gain.exponentialRampToValueAtTime(volume, now + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + seconds);
      oscillator.connect(gain);
      gain.connect(context.destination);
      oscillator.start(now);
      oscillator.stop(now + seconds + 0.01);
      // Le contexte est celui de la séance : on ne le ferme pas ici. Le
      // refermer à chaque bip est exactement ce qui épuisait les quatre
      // emplacements d'iOS quand la fermeture n'arrivait pas.
      oscillator.onended = () => {
        try {
          oscillator.disconnect();
          gain.disconnect();
        } catch {
          // Déjà détaché.
        }
      };
    } catch {
      // Sortie audio indisponible : la séance continue, silencieuse.
    }
  }

  /** Fin de séance : on rend l'emplacement audio au navigateur. */
  release(): void {
    try {
      void this.context?.close?.().catch(() => undefined);
    } catch {
      // Déjà fermé.
    }
    this.context = null;
  }
}

/** Vibration. Absente sur iOS, et ce n'est pas un problème. */
export function vibrate(pattern: number | number[]): void {
  try {
    navigator.vibrate?.(pattern);
  } catch {
    // Pas de vibreur : tant pis.
  }
}

/**
 * Le verrou d'écran, demandé sous geste et repris au retour d'onglet.
 *
 * Sur iOS le verrou est relâché dès que la page passe derrière, et une demande
 * hors geste utilisateur est refusée. Les deux échecs sont normaux : un écran
 * qui s'éteint est agaçant, un minuteur qui s'arrête est un bug — on ne troque
 * jamais le second contre le premier.
 */
export class ScreenLock {
  private sentinel: WakeLockSentinel | null = null;
  private released = false;

  /** Ne rend jamais de promesse rejetée. Ne bloque jamais l'appelant. */
  acquire(): void {
    if (this.released) return;
    try {
      const request = navigator.wakeLock?.request("screen");
      if (!request) return;
      void request
        .then((sentinel) => {
          if (this.released) {
            void sentinel.release().catch(() => undefined);
            return;
          }
          this.sentinel = sentinel;
        })
        .catch(() => undefined);
    } catch {
      // API absente ou refusée : la séance marche quand même.
    }
  }

  release(): void {
    this.released = true;
    try {
      void this.sentinel?.release().catch(() => undefined);
    } catch {
      // Déjà relâché.
    }
    this.sentinel = null;
  }
}
