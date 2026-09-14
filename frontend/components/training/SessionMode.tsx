"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  ExerciseCredit,
  ExerciseImage,
} from "@/components/training/ExerciseImage";
import { IconCheck, IconPlus } from "@/components/ui/Icons";
import { api } from "@/lib/api";
import { ScreenLock, SessionAudio, vibrate } from "@/lib/session-timer";
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

/**
 * La barre d'actions — **hors de la zone qui défile**, donc toujours
 * atteignable.
 *
 * Constaté sur téléphone le 14/09 : avec une image portrait et une consigne
 * longue, « Fait » sortait du cadre et rien ne défilait. La cause n'était pas
 * la hauteur de l'image mais une règle de flexbox : un enfant `flex-1` a
 * `min-height: auto`, donc il **refuse de descendre sous la taille de son
 * contenu**. La zone centrale poussait alors le pied hors d'un conteneur
 * `fixed inset-0`, qui n'a par définition aucun débordement à faire défiler.
 *
 * D'où les trois pièces, et elles vont ensemble : `min-h-0` sur la zone
 * centrale pour qu'elle accepte de rétrécir, `overflow-y-auto` pour que son
 * contenu reste lisible quand elle rétrécit, et `shrink-0` ici pour que le
 * pied garde sa place quoi qu'il arrive.
 *
 * C'est plus sûr qu'un `position: sticky` : un pied collant vit **dans** la
 * zone qui défile et suit le contenu jusqu'à venir se coller ; celui-ci n'y
 * entre jamais.
 */
const ACTION_BAR = "flex shrink-0 gap-3 border-t border-line bg-bg px-5 pt-3";

/**
 * `env(safe-area-inset-bottom)` : sur iPhone, les 34 px du bas appartiennent
 * à l'indicateur d'accueil. Un bouton posé dessous se touche deux fois sur
 * trois — et le geste raté, c'est le système qui le récupère.
 */
const ACTION_BAR_STYLE = {
  paddingBottom: "calc(24px + env(safe-area-inset-bottom))",
};

/**
 * La zone centrale : elle rétrécit d'abord, elle défile ensuite.
 *
 * `min-h-full` sur l'enveloppe intérieure et non `justify-center` sur le
 * conteneur qui défile : un contenu centré **puis** débordant déborde des deux
 * côtés, et le haut devient inatteignable — on ne peut pas remonter avant le
 * début. Avec `min-h-full`, l'enveloppe fait au moins la hauteur visible, donc
 * elle centre tant que ça tient, et s'allonge vers le bas dès que ça ne tient
 * plus.
 */
const SCROLL_AREA = "min-h-0 flex-1 overflow-y-auto px-6";
const SCROLL_INNER = "flex min-h-full flex-col items-center justify-center";

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

  // ── Le geste : son et écran allumé ──────────────────────────────────────
  //
  // **Sur iOS, le son exige un geste de l'utilisateur**, et le verrou d'écran
  // aussi. Les demander au montage — c'est-à-dire hors du gestionnaire de
  // clic — les fait refuser en silence : l'`AudioContext` reste `suspended`,
  // ne se referme jamais, et Safari n'en tolère que quatre par page. Au
  // cinquième repos, la fin de séance est muette.
  //
  // On les réclame donc au **premier tap posé dans le mode séance**, en phase
  // de capture pour être sûr de le voir quel que soit le bouton touché. Et
  // l'ordre compte : rien ici n'est attendu, rien ici ne peut lever, rien ici
  // n'est sur le chemin du minuteur. **S'ils échouent, le minuteur tourne
  // quand même, sans son — jamais l'inverse.**
  const audio = useRef<SessionAudio | null>(null);
  const screenLock = useRef<ScreenLock | null>(null);

  if (audio.current === null) audio.current = new SessionAudio();
  if (screenLock.current === null) screenLock.current = new ScreenLock();

  const primeOnGesture = useCallback(() => {
    audio.current?.prime();
    screenLock.current?.acquire();
  }, []);

  useEffect(() => {
    const lock = screenLock.current;
    const sound = audio.current;

    // Tentative au montage : sur les navigateurs qui l'acceptent (Chrome de
    // bureau), l'écran reste allumé sans attendre le premier bouton.
    lock?.acquire();

    const onVisibility = () => {
      // iOS relâche le verrou dès que la page passe derrière.
      if (document.visibilityState === "visible") lock?.acquire();
    };

    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      lock?.release();
      sound?.release();
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

  /**
   * Un battement : relit l'horloge, met l'affichage à jour, sonne à l'échéance.
   *
   * Extrait de l'intervalle pour être **rejouable** : c'est lui qu'on rappelle
   * au retour d'onglet. Sur iOS un `setInterval` d'une page en arrière-plan est
   * suspendu, pas ralenti ; sans ce rappel immédiat, le compte à rebours reste
   * figé sur sa dernière valeur connue le temps que le battement suivant
   * arrive — et un chiffre figé se lit exactement comme un minuteur arrêté.
   */
  const sweep = useCallback(() => {
    const now = Date.now();
    let alive = false;

    if (restDeadline.current !== null) {
      const left = Math.max(0, Math.round((restDeadline.current - now) / 1000));
      if (left <= 0) {
        restDeadline.current = null;
        setRestLeft(null);
        // Fin de repos : on ne regarde pas l'écran pendant quarante-cinq
        // secondes, il faut que ça s'entende et que ça se sente.
        audio.current?.beep();
        vibrate([120, 60, 120]);
      } else {
        alive = true;
        setRestLeft(left);
      }
    }

    if (holdDeadline.current !== null) {
      const left = Math.max(0, Math.round((holdDeadline.current - now) / 1000));
      if (left <= 0) {
        holdDeadline.current = null;
        setHoldLeft(null);
        audio.current?.beep();
        vibrate(200);
      } else {
        alive = true;
        setHoldLeft(left);
      }
    }

    if (!alive) setTicking(false);
  }, []);

  useEffect(() => {
    if (!ticking) return;

    const timer = window.setInterval(sweep, 250);
    // Le retour d'arrière-plan ne rattrape pas les battements perdus : il
    // recalcule depuis l'échéance, une fois, tout de suite.
    // Le retour d'arrière-plan ne rattrape pas les battements perdus : il
    // recalcule depuis l'échéance, une fois, tout de suite. Sur iOS un
    // `setInterval` de page masquée est suspendu, pas ralenti, et le premier
    // battement d'après peut se faire attendre — un chiffre figé se lit
    // exactement comme un minuteur arrêté.
    const onVisibility = () => {
      if (document.visibilityState === "visible") sweep();
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [ticking, sweep]);

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
      // Même structure que l'écran d'exercice, pour la même raison : cinq
      // boutons de ressenti et un titre tiennent partout, mais un téléphone
      // en mode paysage ou une police système agrandie ne laissent pas plus
      // de place ici qu'ailleurs — et « Terminer » est le bouton qui
      // enregistre la séance.
      <div className="fixed inset-0 z-50 flex h-[100dvh] flex-col bg-bg">
        <div className={SCROLL_AREA}>
          <div className={`${SCROLL_INNER} gap-6 py-6 text-center`}>
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
          </div>
        </div>

        <footer className={ACTION_BAR} style={ACTION_BAR_STYLE}>
          <button
            type="button"
            disabled={saving}
            onClick={() => finish(done, feeling)}
            className="flex min-h-[56px] flex-1 items-center justify-center rounded-button bg-accent px-5 text-[17px] font-semibold text-on-accent disabled:opacity-50"
          >
            {saving ? "Enregistrement…" : "Terminer"}
          </button>
        </footer>
      </div>
    );
  }

  if (!step) return null;

  const { item } = step;
  const target = item.duration_s
    ? `${item.duration_s} s`
    : `${item.reps} répétitions`;

  return (
    <div
      // `h-[100dvh]` et non la seule hauteur d'un `inset-0` : sur iPhone, la
      // barre d'adresse de Safari se rétracte au défilement, et `vh` reste
      // figé sur la **grande** hauteur — celle qu'on n'a pas quand la barre
      // est déployée. `dvh` suit la hauteur réellement visible, ce qui est
      // exactement ce qu'il faut pour garantir qu'un pied de page tient à
      // l'écran.
      className="fixed inset-0 z-50 flex h-[100dvh] flex-col bg-bg"
      // Capture : le premier tap **de la séance**, quel que soit le bouton
      // touché, réveille le son et demande l'écran allumé. C'est le seul
      // instant où iOS l'accepte, et il ne se répète pas.
      onPointerDownCapture={primeOnGesture}
    >
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
        <>
          <div className={SCROLL_AREA}>
            <div className={`${SCROLL_INNER} gap-6 py-4`}>
              <p className="text-[13px] font-semibold uppercase tracking-[0.16em] text-mute">
                Repos
              </p>
              <p
                aria-live="off"
                data-testid="rest-countdown"
                className="tabular font-display text-[128px] font-bold leading-none text-accent"
              >
                {clock(restLeft)}
              </p>
              <p className="max-w-[320px] text-center text-[16px] leading-snug text-ink-2">
                Ensuite : {step.item.exercise.name_fr ?? step.item.exercise.name}
              </p>
            </div>
          </div>

          {/* Les deux boutons du repos sont la barre d'actions de cet écran :
              ils sortent donc de la zone qui défile, comme Fait et Passer. */}
          <footer className={ACTION_BAR} style={ACTION_BAR_STYLE}>
            <button
              type="button"
              onClick={() => startRest((restLeft ?? 0) + 30)}
              className="flex min-h-[56px] flex-1 items-center justify-center gap-2 rounded-button border border-line bg-card text-[16px] font-semibold text-ink"
            >
              <IconPlus className="h-5 w-5" />
              30 s
            </button>
            <button
              type="button"
              onClick={stopRest}
              className="min-h-[56px] flex-1 rounded-button bg-accent text-[16px] font-semibold text-on-accent"
            >
              Passer le repos
            </button>
          </footer>
        </>
      ) : (
        <>
          <main className={SCROLL_AREA}>
            <div className={`${SCROLL_INNER} gap-4 py-4 text-center`}>
              {/* L'image en grand, **sous le nom**, et les deux photos en
                  alternance quand elles existent : c'est leur va-et-vient qui
                  montre le mouvement, et c'est ce qu'on cherche à un mètre, les
                  mains au sol. Sans image, un pictogramme du groupe — jamais un
                  cadre vide, qui fait attendre un chargement qui ne vient pas
                  (décidé le 13/09).

                  Plafond en **dvh** et non en vh : une image portrait calée sur
                  la grande hauteur du viewport iOS mange la place du pied de
                  page dès que la barre d'adresse se déploie. `object-contain`
                  est déjà porté par `ExerciseImage` — l'image se loge dans le
                  plafond, elle n'est jamais rognée. */}
              <ExerciseImage
                exercise={item.exercise}
                animate
                className="max-h-[40dvh] w-auto"
              />

              <h1 className="font-display text-[40px] font-bold uppercase leading-[0.95] tracking-tight text-ink">
                {item.exercise.name_fr ?? item.exercise.name}
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

              {item.exercise.description_fr ?? item.exercise.instructions ? (
                <p className="max-w-[420px] text-[15px] leading-snug text-ink-2">
                  {item.exercise.description_fr ?? item.exercise.instructions}
                </p>
              ) : null}

              {/* L'attribution, discrète mais présente : wger est en CC BY-SA,
                  et la licence exige de citer la source. */}
              <ExerciseCredit exercise={item.exercise} />

              {/* Minuteur de maintien, pour les exercices tenus. */}
              {item.duration_s ? (
                holdLeft !== null ? (
                  <p
                    aria-live="off"
                    data-testid="hold-countdown"
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
            </div>
          </main>

          <footer className={ACTION_BAR} style={ACTION_BAR_STYLE}>
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
