"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { IconMinus, IconPlus } from "@/components/ui/Icons";

/**
 * Compteur de vagues — pas de 1 au tap, pas de 5 à l'appui long.
 *
 * Le nombre de vagues d'une session va de trois à quarante. À un par tap, une
 * bonne session c'est trente-cinq appuis ; à cinq en appui long, c'est deux
 * secondes de doigt posé. Le clavier numérique, lui, est exclu : il occupe la
 * moitié de l'écran, demande de viser une touche et de le refermer, pour un
 * nombre qu'on donne de toute façon à la louche.
 *
 * L'appui long **remplace** l'incrément simple, il ne s'y ajoute pas : sans
 * cette bascule, relâcher après une répétition ajouterait une vague de plus et
 * le compteur dériverait d'une unité à chaque appui long.
 */
const HOLD_DELAY_MS = 450;
const HOLD_INTERVAL_MS = 180;
const HOLD_STEP = 5;

interface WaveStepperProps {
  value: number;
  onChange: (next: number) => void;
  max?: number;
}

export function WaveStepper({ value, onChange, max = 200 }: WaveStepperProps) {
  const [holding, setHolding] = useState(false);
  const timers = useRef<{ delay?: number; repeat?: number }>({});
  // Vrai dès que la répétition a commencé : le relâchement ne doit alors plus
  // compter comme un tap simple.
  const repeated = useRef(false);
  // La valeur courante, lue par la répétition : un `setInterval` capture son
  // environnement au moment où il est posé, et rendrait sinon toujours le même
  // résultat à partir de la valeur de départ.
  const latest = useRef(value);
  latest.current = value;

  const clamp = useCallback(
    (next: number) => Math.min(max, Math.max(0, next)),
    [max],
  );

  const stop = useCallback(() => {
    window.clearTimeout(timers.current.delay);
    window.clearInterval(timers.current.repeat);
    timers.current = {};
    setHolding(false);
  }, []);

  // Un doigt qui glisse hors du bouton, un appel entrant, un changement
  // d'onglet : la répétition doit s'arrêter avec le composant, sinon elle
  // continue de compter dans le vide.
  useEffect(() => stop, [stop]);

  const press = (direction: 1 | -1) => {
    repeated.current = false;
    timers.current.delay = window.setTimeout(() => {
      repeated.current = true;
      setHolding(true);
      timers.current.repeat = window.setInterval(() => {
        onChange(clamp(latest.current + direction * HOLD_STEP));
      }, HOLD_INTERVAL_MS);
    }, HOLD_DELAY_MS);
  };

  const release = (direction: 1 | -1) => {
    const wasRepeating = repeated.current;
    stop();
    if (!wasRepeating) onChange(clamp(latest.current + direction));
  };

  const button = (direction: 1 | -1, label: string) => (
    <button
      type="button"
      aria-label={label}
      onPointerDown={(event) => {
        // Le pointeur reste capté même si le doigt glisse : sans ça, sortir du
        // bouton en appui long ne déclencherait jamais `pointerup`, et la
        // répétition tournerait indéfiniment.
        event.currentTarget.setPointerCapture(event.pointerId);
        press(direction);
      }}
      onPointerUp={() => release(direction)}
      onPointerCancel={stop}
      // Un appui long sur iOS ouvre le menu de sélection : il n'a rien à faire
      // sur un bouton dont l'appui long est justement la fonction.
      onContextMenu={(event) => event.preventDefault()}
      className="flex h-[58px] w-[58px] shrink-0 touch-none select-none items-center justify-center text-ink-2 active:bg-soft"
    >
      {direction === 1 ? (
        <IconPlus className="h-6 w-6" />
      ) : (
        <IconMinus className="h-6 w-6" />
      )}
    </button>
  );

  return (
    <div className="min-w-0">
      <div className="flex items-baseline justify-between gap-3 pb-2">
        <span className="text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
          Vagues
        </span>
        <span className="text-[12px] text-mute">appui long : par 5</span>
      </div>

      <div
        className={`flex items-stretch overflow-hidden rounded-button border bg-card ${
          holding ? "border-accent" : "border-line"
        }`}
      >
        {button(-1, "Une vague de moins")}
        <span
          aria-live="polite"
          aria-label={`${value} vagues`}
          className="tabular flex flex-1 items-center justify-center font-display text-[34px] font-bold leading-none text-ink"
        >
          {value}
        </span>
        {button(1, "Une vague de plus")}
      </div>
    </div>
  );
}
