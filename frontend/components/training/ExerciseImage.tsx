"use client";

import { useEffect, useState } from "react";

import {
  ExercisePictogram,
  pictogramKey,
} from "@/components/training/ExercisePictogram";
import type { Exercise } from "@/lib/types";

/**
 * L'image d'un exercice — **et un repli qui n'est pas un cadre vide**.
 *
 * Décidé le 13/09 (retours n° 3). Trois choses, et chacune a sa raison :
 *
 * 1. **L'alternance des deux photos.** free-exercise-db en donne deux par
 *    exercice : la position de départ et la position d'arrivée. C'est leur
 *    alternance qui montre le **mouvement** — une seule image ne dit pas ce
 *    qui bouge, et c'est justement ce qu'on cherche à un mètre, les mains au
 *    sol. Deux secondes : assez lent pour se lire, assez rapide pour se
 *    comprendre.
 * 2. **Un pictogramme du groupe musculaire** quand il n'y a pas d'image. Pas
 *    un cadre vide, pas un point d'interrogation : un cadre vide fait croire
 *    à un chargement qui ne vient jamais, et on attend devant.
 * 3. **La dimension est réservée** (`aspect-ratio`) et le chargement est
 *    paresseux. Sans la réserve, l'arrivée de l'image pousse le nom de
 *    l'exercice hors de l'écran au moment exact où on le lit.
 *
 * L'attribution est portée par `ExerciseCredit`, à côté : une image CC BY-SA
 * ne s'affiche pas comme une image du domaine public.
 */

const SWAP_MS = 2000;

/** Les huit groupes, en pictogrammes de trait — jamais d'emoji (CLAUDE.md). */
function GroupGlyph({ group }: { group: string }) {
  const common = {
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.75,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };

  return (
    <svg viewBox="0 0 48 48" className="h-12 w-12" aria-hidden {...common}>
      {group === "abdos" ? (
        <>
          <rect x="16" y="10" width="16" height="28" rx="4" />
          <path d="M16 19h16M16 28h16M24 10v28" />
        </>
      ) : group === "dos" ? (
        <>
          <path d="M24 8v32" />
          <path d="M24 14l-9 6M24 14l9 6M24 26l-9 6M24 26l9 6" />
        </>
      ) : group === "epaules" ? (
        <>
          <circle cx="24" cy="16" r="6" />
          <path d="M10 34c0-7 6-11 14-11s14 4 14 11" />
        </>
      ) : group === "jambes" ? (
        <>
          <path d="M18 8v14l-4 18M30 8v14l4 18" />
          <path d="M16 22h16" />
        </>
      ) : group === "hanches" ? (
        <>
          <path d="M12 16h24" />
          <path d="M14 16c0 8 4 12 10 12s10-4 10-12" />
          <path d="M20 28l-3 12M28 28l3 12" />
        </>
      ) : group === "poitrine" ? (
        <>
          <path d="M10 16c5-4 9-4 14 0 5-4 9-4 14 0" />
          <path d="M10 16v8c0 8 6 14 14 16 8-2 14-8 14-16v-8" />
        </>
      ) : group === "bras" ? (
        <>
          <path d="M14 34V20a6 6 0 0 1 12 0v6" />
          <path d="M26 26h6a4 4 0 0 1 0 8h-6" />
        </>
      ) : (
        <>
          <circle cx="24" cy="12" r="4" />
          <path d="M24 16v14M24 30l-6 10M24 30l6 10M12 22l12-4 12 4" />
        </>
      )}
    </svg>
  );
}

export function ExerciseImage({
  exercise,
  className = "",
  animate = false,
}: {
  exercise: Pick<Exercise, "image_url" | "images" | "group_key" | "name_fr" | "name">;
  className?: string;
  /** Alterne les deux photos. Réservé au mode séance : ailleurs, une image
   *  qui bouge attire l'œil pour rien. */
  animate?: boolean;
}) {
  const frames = exercise.images?.length
    ? exercise.images
    : exercise.image_url
      ? [exercise.image_url]
      : [];
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (!animate || frames.length < 2) return;
    const timer = window.setInterval(
      () => setIndex((value) => (value + 1) % frames.length),
      SWAP_MS,
    );
    return () => window.clearInterval(timer);
  }, [animate, frames.length]);

  // Un pictogramme maison : dessiné en ligne, donc il suit le thème — clair
  // sur téléphone, sombre sur bureau — là où un fichier SVG dans une balise
  // `img` resterait figé sur une seule palette.
  const pictogram = pictogramKey(frames[0] ?? exercise.image_url);
  if (pictogram) {
    return (
      <div
        className={`flex aspect-[4/3] items-center justify-center rounded-card border border-line bg-card p-3 ${className}`}
      >
        <ExercisePictogram name={pictogram} />
      </div>
    );
  }

  if (frames.length === 0) {
    return (
      <div
        className={`flex aspect-[4/3] items-center justify-center rounded-card border border-line bg-soft text-mute ${className}`}
        role="img"
        aria-label={`Pas d'image pour ${exercise.name_fr ?? exercise.name}`}
      >
        <GroupGlyph group={exercise.group_key} />
      </div>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={frames[Math.min(index, frames.length - 1)]}
      alt=""
      loading="lazy"
      // La dimension est réservée : sans elle, l'arrivée de l'image pousse le
      // nom de l'exercice hors de l'écran au moment où on le lit.
      className={`aspect-[4/3] w-full rounded-card border border-line bg-card object-contain ${className}`}
    />
  );
}

/**
 * L'attribution — **obligatoire dès qu'il y a un CC BY**, pas seulement un
 * CC BY-SA.
 *
 * wger est sous CC BY-SA 4.0 : la licence exige de citer la source.
 * free-exercise-db est dans le domaine public et n'exige rien — on garde
 * quand même la source, parce qu'un projet perso d'aujourd'hui peut devenir
 * autre chose demain, et que retrouver l'origine d'une image après coup est
 * impossible.
 *
 * Les photos de Wikimedia Commons (14/09) sont en CC BY 3.0 et CC BY-SA 3.0,
 * et **ces licences-là nomment l'auteur** : « attribuer l'œuvre à son auteur »
 * n'est pas satisfait par un lien vers la page du fichier. D'où `image_author`
 * sur la ligne, affiché ici. Une photo prise par quelqu'un et donnée sous
 * CC BY se paie d'un nom ; c'est le prix, et il est très bas.
 */
export function ExerciseCredit({
  exercise,
  className = "",
}: {
  exercise: Pick<
    Exercise,
    "source" | "license" | "source_url" | "image_url" | "image_author"
  >;
  className?: string;
}) {
  if (!exercise.image_url) return null;

  // Un dessin fait ici : rien à attribuer à personne, mais on le dit quand
  // même — pour qu'on sache, dans six mois, lesquels sont à nous.
  if (pictogramKey(exercise.image_url)) {
    return (
      <p className={`text-[11px] text-mute ${className}`}>
        Pictogramme : Sport — licence personnelle
      </p>
    );
  }

  const origin =
    exercise.source === "wger"
      ? `wger.de — ${exercise.license ?? "CC BY-SA 4.0"}`
      : exercise.source === "free-exercise-db"
        ? "free-exercise-db — domaine public"
        : exercise.license
          ? `${exercise.source} — ${exercise.license}`
          : exercise.source;

  const label = exercise.image_author
    ? `${exercise.image_author} — ${origin}`
    : origin;

  return (
    <p className={`text-[11px] text-mute ${className}`}>
      {exercise.source_url ? (
        <a
          href={exercise.source_url}
          target="_blank"
          rel="noreferrer noopener"
          className="underline underline-offset-2"
        >
          {label}
        </a>
      ) : (
        label
      )}
    </p>
  );
}
