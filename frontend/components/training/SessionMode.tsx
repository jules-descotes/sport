"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { IconCheck, IconPlus } from "@/components/ui/Icons";
import { api } from "@/lib/api";
import type { Formula, FormulaItem } from "@/lib/types";

/**
 * **Mode séance** — plein écran, zéro clavier, une seule chose à faire.
 *
 * L'exercice en cours en très grand, son image, le minuteur de repos géant,
 * et trois boutons : Fait, Passer, +30 s. C'est tout. Pendant l'effort on a
 * les mains occupées et l'écran à un mètre : la règle « zéro saisie clavier »
 * (`PROJET.md` §1, règle 5) s'applique ici plus qu'ailleurs.
 *
 * Trois détails qui décident si la séance se fait vraiment :
 *
 * - **Screen Wake Lock** : un écran qui s'éteint au milieu d'une planche
 *   oblige à le rallumer avec les mains au sol. L'API n'existe pas partout —
 *   elle est demandée, jamais exigée.
 * - **Vibration et son en fin de repos** : on ne regarde pas l'écran pendant
 *   quarante-cinq secondes de repos. Le son est synthétisé à la volée, sans
 *   fichier à charger — donc sans réseau, et sans octet de plus dans le bundle.
 * - **Écourter est un geste explicite**, et il est enregistré comme tel. Le
 *   serveur tranche à partir des séries réellement faites : une séance de
 *   28 minutes arrêtée à la sixième est un renseignement, pas un échec à
 *   cacher.
 */

/** Une série à faire, dépliée depuis les `sets` de chaque ligne de formule. */
interface Step {
  key: string;
  item: FormulaItem;
  setIndex: number;
  setCount: number;
}

interface Done {
  position: number;
  exercise_id: number;
  formula_item_id: number;
  exercise_name: string;
  reps: number | null;
  duration_s: number | null;
  skipped: boolean;
}

function buildSteps(formula: Formula): Step[] {
  const steps: Step[] = [];
  for (const item of formula.items) {
    for (let index = 0; index < item.sets; index += 1) {
      steps.push({
        key: `${item.id}-${index}`,
        item,
        setIndex: index + 1,
        setCount: item.sets,
      });
    }
  }
  return steps;
}

/** « 1:05 », « 45 s ». Le chiffre qu'on lit à un mètre. */
function clock(seconds: number): string {
  if (seconds < 60) return `${seconds}`;
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

/**
 * Bip de fin de repos, synthétisé.
 *
 * Pas de fichier audio : un `<audio>` demande un octet de réseau au pire
 * moment, et le bundle n'a pas à grossir pour deux dixièmes de seconde de
 * sinusoïde. L'appel est enveloppé : un navigateur qui refuse l'audio ne doit
 * pas interrompre la séance.
 */
function beep(): void {
  try {
    const Ctor =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext;
    if (!Ctor) return;
    const context = new Ctor();
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.type = "sine";
    oscillator.frequency.value = 880;
    gain.gain.setValueAtTime(0.0001, context.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.25, context.currentTime + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 0.35);
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.start();
    oscillator.stop(context.currentTime + 0.36);
    oscillator.onended = () => context.close();
  } catch {
    // Audio refusé : la séance continue, silencieuse.
  }
}

function vibrate(pattern: number | number[]): void {
  try {
    navigator.vibrate?.(pattern);
  } catch {
    // Pas de vibreur : tant pis.
  }
}

export function SessionMode({
  formula,
  workoutId,
  onFinished,
  onAbandon,
}: {
  formula: Formula;
  workoutId: number;
  onFinished: (cutShort: boolean) => void;
  onAbandon: () => void;
}) {
  const steps = useMemo(() => buildSteps(formula), [formula]);

  const [index, setIndex] = useState(0);
  const [done, setDone] = useState<Done[]>([]);
  const [restLeft, setRestLeft] = useState<number | null>(null);
  const [holdLeft, setHoldLeft] = useState<number | null>(null);
  const [asking, setAsking] = useState(false);
  const [feeling, setFeeling] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  const step = steps[index] ?? null;
  const progress = steps.length ? index / steps.length : 0;

  // ── Écran allumé ────────────────────────────────────────────────────────
  //
  // Un écran qui s'éteint au milieu d'une planche oblige à le rallumer les
  // mains au sol. Le verrou se reprend au retour d'onglet : iOS le relâche dès
  // qu'on masque la page.
  useEffect(() => {
    let lock: WakeLockSentinel | null = null;
    let cancelled = false;

    const acquire = async () => {
      try {
        lock = (await navigator.wakeLock?.request("screen")) ?? null;
      } catch {
        // Refusé ou indisponible : la séance marche quand même.
      }
    };

    const onVisibility = () => {
      if (document.visibilityState === "visible" && !cancelled) void acquire();
    };

    void acquire();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisibility);
      void lock?.release().catch(() => undefined);
    };
  }, []);

  // ── Minuteurs ───────────────────────────────────────────────────────────
  //
  // Les comptes à rebours sont des **échéances**, pas des compteurs qu'on
  // décrémente : un onglet en arrière-plan ralentit `setInterval`, et un repos
  // de quarante-cinq secondes finirait par en durer soixante-dix. On relit
  // l'horloge à chaque battement, et le temps reste juste même si l'écran
  // s'est mis en veille.
  //
  // Le bip et la vibration partent depuis le **callback de l'intervalle**, pas
  // depuis le corps d'un effet : c'est un système externe qui nous réveille,
  // et c'est le seul endroit où ces effets de bord ne déclenchent pas de
  // rendus en cascade.
  const restDeadline = useRef<number | null>(null);
  const holdDeadline = useRef<number | null>(null);
  const [ticking, setTicking] = useState(false);

  const startRest = useCallback((seconds: number) => {
    restDeadline.current = Date.now() + seconds * 1000;
    setRestLeft(seconds);
    setTicking(true);
  }, []);

  const stopRest = useCallback(() => {
    restDeadline.current = null;
    setRestLeft(null);
  }, []);

  const startHold = useCallback((seconds: number) => {
    holdDeadline.current = Date.now() + seconds * 1000;
    setHoldLeft(seconds);
    setTicking(true);
  }, []);

  const stopHold = useCallback(() => {
    holdDeadline.current = null;
    setHoldLeft(null);
  }, []);

  useEffect(() => {
    if (!ticking) return;

    const timer = window.setInterval(() => {
      const now = Date.now();
      let alive = false;

      if (restDeadline.current !== null) {
        const left = Math.max(
          0,
          Math.round((restDeadline.current - now) / 1000),
        );
        if (left <= 0) {
          restDeadline.current = null;
          setRestLeft(null);
          // Fin de repos : on ne regarde pas l'écran pendant quarante-cinq
          // secondes, il faut que ça s'entende et que ça se sente.
          beep();
          vibrate([120, 60, 120]);
        } else {
          alive = true;
          setRestLeft(left);
        }
      }

      if (holdDeadline.current !== null) {
        const left = Math.max(
          0,
          Math.round((holdDeadline.current - now) / 1000),
        );
        if (left <= 0) {
          holdDeadline.current = null;
          setHoldLeft(null);
          beep();
          vibrate(200);
        } else {
          alive = true;
          setHoldLeft(left);
        }
      }

      if (!alive) setTicking(false);
    }, 250);

    return () => window.clearInterval(timer);
  }, [ticking]);

  const advance = useCallback(
    (entry: Done) => {
      setDone((current) => [...current, entry]);
      stopHold();

      const next = index + 1;
      if (next >= steps.length) {
        stopRest();
        setAsking(true);
        return;
      }

      // Le repos de la série qu'on vient de finir, pas de la suivante.
      const rest = entry.skipped ? 0 : (steps[index]?.item.rest_s ?? 0);
      if (rest > 0) startRest(rest);
      else stopRest();
      setIndex(next);
    },
    [index, steps, startRest, stopRest, stopHold],
  );

  const complete = () => {
    if (!step) return;
    advance({
      position: done.length,
      exercise_id: step.item.exercise.id,
      formula_item_id: step.item.id,
      exercise_name: step.item.exercise.name,
      reps: step.item.reps,
      duration_s: step.item.duration_s,
      skipped: false,
    });
  };

  const skip = () => {
    if (!step) return;
    advance({
      position: done.length,
      exercise_id: step.item.exercise.id,
      formula_item_id: step.item.id,
      exercise_name: step.item.exercise.name,
      reps: null,
      duration_s: null,
      skipped: true,
    });
  };

  const finish = async (entries: Done[], value: number | null) => {
    setSaving(true);
    try {
      const workout = await api.finishWorkout(workoutId, {
        ...(value !== null ? { feeling: value } : {}),
        sets: entries,
      });
      onFinished(workout.cut_short);
    } catch {
      // Le réseau manque : la séance a eu lieu, et c'est ce qui compte. On
      // sort sans bloquer l'écran — une séance non enregistrée est moins grave
      // qu'une séance non faite.
      onFinished(false);
    }
  };

  // ── Écran de fin : un ressenti, un tap ──────────────────────────────────
  if (asking) {
    const cutShort = done.filter((entry) => !entry.skipped).length < steps.length;
    return (
      <div className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-6 bg-bg px-6 text-center">
        <p className="font-display text-[38px] font-bold uppercase leading-none tracking-tight text-ink">
          {cutShort ? "Séance écourtée" : "Séance faite"}
        </p>
        <p className="max-w-[320px] text-[15px] leading-snug text-ink-2">
          {cutShort
            ? "Elle est enregistrée comme écourtée — c'est une information sur la formule, pas sur toi."
            : `${formula.name}, ${formula.duration_min} min.`}
        </p>

        <fieldset className="w-full max-w-[360px]">
          <legend className="pb-3 text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
            Comment c&apos;était ?
          </legend>
          <div className="flex gap-2" role="radiogroup" aria-label="Ressenti">
            {[1, 2, 3, 4, 5].map((level) => (
              <button
                key={level}
                type="button"
                role="radio"
                aria-checked={feeling === level}
                aria-label={`Ressenti : ${level} sur 5`}
                onClick={() => setFeeling(level)}
                className={`tabular flex h-[58px] flex-1 items-center justify-center rounded-cell font-display text-[26px] font-bold leading-none ${
                  feeling === level
                    ? `score-${level} ring-2 ring-ink`
                    : "border border-line bg-card text-mute"
                }`}
              >
                {level}
              </button>
            ))}
          </div>
        </fieldset>

        <button
          type="button"
          disabled={saving}
          onClick={() => finish(done, feeling)}
          className="flex min-h-[56px] w-full max-w-[360px] items-center justify-center rounded-button bg-accent px-5 text-[17px] font-semibold text-on-accent disabled:opacity-50"
        >
          {saving ? "Enregistrement…" : "Terminer"}
        </button>
      </div>
    );
  }

  if (!step) return null;

  const { item } = step;
  const target = item.duration_s
    ? `${item.duration_s} s`
    : `${item.reps} répétitions`;

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-bg">
      {/* Progression en tête : un trait, pas un pourcentage. */}
      <div className="h-1.5 w-full shrink-0 bg-line">
        <div
          className="h-full bg-accent transition-[width] duration-300"
          style={{ width: `${Math.round(progress * 100)}%` }}
          role="progressbar"
          aria-valuenow={index}
          aria-valuemin={0}
          aria-valuemax={steps.length}
          aria-label="Progression de la séance"
        />
      </div>

      <header className="flex shrink-0 items-center justify-between gap-3 px-5 pt-3">
        <p className="tabular text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
          {formula.name} · {index + 1} / {steps.length}
        </p>
        <button
          type="button"
          onClick={() => (done.length ? setAsking(true) : onAbandon())}
          className="min-h-touch rounded-button px-3 text-[14px] font-semibold text-mute"
        >
          {done.length ? "Arrêter" : "Quitter"}
        </button>
      </header>

      {/* Le repos couvre tout : pendant quarante-cinq secondes, la seule
          information utile est le compte à rebours. */}
      {restLeft !== null ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-6 px-6">
          <p className="text-[13px] font-semibold uppercase tracking-[0.16em] text-mute">
            Repos
          </p>
          <p
            aria-live="off"
            className="tabular font-display text-[128px] font-bold leading-none text-accent"
          >
            {clock(restLeft)}
          </p>
          <p className="max-w-[320px] text-center text-[16px] leading-snug text-ink-2">
            Ensuite : {step.item.exercise.name}
          </p>
          <div className="flex w-full max-w-[360px] gap-3">
            <button
              type="button"
              onClick={() => startRest((restLeft ?? 0) + 30)}
              className="flex min-h-touch flex-1 items-center justify-center gap-2 rounded-button border border-line bg-card text-[16px] font-semibold text-ink"
            >
              <IconPlus className="h-5 w-5" />
              30 s
            </button>
            <button
              type="button"
              onClick={stopRest}
              className="min-h-touch flex-1 rounded-button bg-accent text-[16px] font-semibold text-on-accent"
            >
              Passer le repos
            </button>
          </div>
        </div>
      ) : (
        <>
          <main className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
            {item.exercise.image_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={item.exercise.image_url}
                alt=""
                className="max-h-[30vh] w-auto rounded-card border border-line bg-card object-contain"
              />
            ) : null}

            <h1 className="font-display text-[40px] font-bold uppercase leading-[0.95] tracking-tight text-ink">
              {item.exercise.name}
            </h1>

            <p className="tabular font-display text-[30px] font-bold leading-none text-accent">
              {target}
            </p>

            <p className="text-[15px] text-ink-2">
              {step.setCount > 1
                ? `Série ${step.setIndex} sur ${step.setCount}`
                : "Une seule série"}
              {item.note ? ` · ${item.note}` : ""}
              {item.tempo ? ` · tempo ${item.tempo}` : ""}
            </p>

            {item.exercise.instructions ? (
              <p className="max-w-[420px] text-[15px] leading-snug text-ink-2">
                {item.exercise.instructions}
              </p>
            ) : null}

            {/* Minuteur de maintien, pour les exercices tenus. */}
            {item.duration_s ? (
              holdLeft !== null ? (
                <p
                  aria-live="off"
                  className="tabular font-display text-[88px] font-bold leading-none text-ink"
                >
                  {clock(holdLeft)}
                </p>
              ) : (
                <button
                  type="button"
                  onClick={() => startHold(item.duration_s as number)}
                  className="min-h-touch rounded-button border border-line bg-card px-5 text-[16px] font-semibold text-ink"
                >
                  Lancer le minuteur
                </button>
              )
            ) : null}
          </main>

          <footer
            className="flex shrink-0 gap-3 px-5 pb-6 pt-3"
            style={{ paddingBottom: "calc(24px + env(safe-area-inset-bottom))" }}
          >
            <button
              type="button"
              onClick={skip}
              className="min-h-[56px] flex-1 rounded-button border border-line bg-card text-[16px] font-semibold text-ink-2"
            >
              Passer
            </button>
            <button
              type="button"
              onClick={complete}
              className="flex min-h-[56px] flex-[2] items-center justify-center gap-2 rounded-button bg-accent text-[18px] font-semibold text-on-accent"
            >
              <IconCheck className="h-6 w-6" />
              Fait
            </button>
          </footer>
        </>
      )}
    </div>
  );
}
