"use client";

import { useMemo, useState } from "react";

import { RatingScale } from "@/components/session/RatingScale";
import { IconChevronDown } from "@/components/ui/Icons";
import { startedHours } from "@/lib/rating";
import type { SessionSegmentValue } from "@/lib/types";

/**
 * **Noter heure par heure** — la frise optionnelle (décidé le 13/09).
 *
 * Une session de deux heures et demie n'est pas une note : la houle monte, le
 * vent se lève, la marée tourne. Noter 3 en moyenne quand la première heure
 * valait 5 et la dernière 2, c'est effacer le seul signal que ces trois heures
 * portaient — et c'est précisément ce que le modèle cherche à apprendre.
 *
 * Trois décisions d'écran, toutes issues de la même règle — **le chemin normal
 * ne doit pas s'allonger d'un pouce** :
 *
 * 1. **Un lien discret, replié.** Pas une section, pas un bouton d'action. La
 *    notation en quinze secondes reste deux taps ; ceci est pour les jours où
 *    la session mérite d'être racontée.
 * 2. **Seulement au-delà d'une heure.** En dessous, il n'y a qu'un segment, et
 *    ce serait la note globale écrite deux fois.
 * 3. **Préremplies avec la note globale.** Détailler veut presque toujours dire
 *    « sauf la dernière heure » : partir de zéro obligerait à ressaisir ce
 *    qu'on vient de poser.
 *
 * Chaque ligne porte une **heure pleine** : c'est la clé d'appariement avec la
 * ligne horaire du `conditions_snapshot`, côté serveur.
 */
interface SegmentRatingProps {
  start: Date;
  end: Date;
  /** Les notes globales, qui servent de préremplissage. */
  conditions: number | null;
  personal: number | null;
  segments: SessionSegmentValue[];
  onChange: (segments: SessionSegmentValue[]) => void;
}

/** En deçà, la frise n'aurait qu'une ligne : ce serait la note globale, deux fois. */
const MIN_MINUTES = 60;

function hourLabel(hour: Date): string {
  const next = new Date(hour);
  next.setHours(next.getHours() + 1);
  return `${hour.getHours()} h – ${next.getHours()} h`;
}

export function SegmentRating({
  start,
  end,
  conditions,
  personal,
  segments,
  onChange,
}: SegmentRatingProps) {
  const [open, setOpen] = useState(segments.length > 0);

  const hours = useMemo(() => startedHours(start, end), [start, end]);
  const minutes = Math.round((end.getTime() - start.getTime()) / 60_000);

  if (minutes <= MIN_MINUTES || hours.length < 2) return null;

  const byHour = new Map(
    segments.map((segment) => [segment.started_at, segment]),
  );

  const valueFor = (hour: Date, field: "conditions" | "personal") => {
    const existing = byHour.get(hour.toISOString());
    if (existing) {
      return field === "conditions"
        ? existing.rating_conditions
        : existing.rating_personal;
    }
    // Préremplissage : la note globale. Détailler veut presque toujours dire
    // « sauf une heure », pas « tout reprendre ».
    return field === "conditions" ? conditions : personal;
  };

  const set = (hour: Date, field: "conditions" | "personal", value: number) => {
    const key = hour.toISOString();
    const existing = byHour.get(key) ?? {
      started_at: key,
      rating_conditions: conditions,
      rating_personal: personal,
      // Une heure créée ici ne décrit rien : le type de vagues se saisit au
      // niveau de la session (« décrire les vagues »). Les axes d'une heure
      // déjà décrite, eux, sont conservés par l'étalement ci-dessous — noter
      // une heure ne doit pas effacer ce qu'on en avait dit.
      wave_size: null,
      wave_length: null,
      wave_shape: null,
    };
    const next: SessionSegmentValue = {
      ...existing,
      [field === "conditions" ? "rating_conditions" : "rating_personal"]: value,
    };
    onChange([
      ...segments.filter((segment) => segment.started_at !== key),
      next,
    ].sort((a, b) => a.started_at.localeCompare(b.started_at)));
  };

  return (
    <div className="border-t border-line px-5 py-3">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex min-h-touch w-full items-center justify-between gap-3 text-left"
      >
        <span className="text-[14px] font-semibold text-ink-2">
          Noter heure par heure
          {segments.length > 0 ? (
            <span className="text-mute"> · {segments.length} heures</span>
          ) : null}
        </span>
        <IconChevronDown
          className={`h-5 w-5 shrink-0 text-mute transition-transform ${
            open ? "rotate-180" : ""
          }`}
        />
      </button>

      {open ? (
        <>
          <p className="pb-1 pt-1 text-[12px] leading-snug text-mute">
            La note globale reste celle qui s&apos;affiche. Ces heures-là
            servent au modèle : chacune est appariée à ses propres conditions.
          </p>

          <ul className="flex flex-col gap-3 pt-2">
            {hours.map((hour) => (
              <li key={hour.toISOString()} className="rounded-card border border-line bg-card p-3">
                <p className="tabular pb-2 text-[13px] font-semibold text-ink">
                  {hourLabel(hour)}
                </p>
                <div className="flex flex-col gap-2">
                  <RatingScale
                    compact
                    name={`Conditions ${hourLabel(hour)}`}
                    label="Conditions"
                    value={valueFor(hour, "conditions")}
                    onChange={(value) => set(hour, "conditions", value)}
                  />
                  <RatingScale
                    compact
                    name={`Ressenti ${hourLabel(hour)}`}
                    label="Ressenti"
                    value={valueFor(hour, "personal")}
                    onChange={(value) => set(hour, "personal", value)}
                  />
                </div>
              </li>
            ))}
          </ul>

          {segments.length > 0 ? (
            <button
              type="button"
              onClick={() => onChange([])}
              className="mt-3 min-h-touch text-[13px] font-semibold text-mute"
            >
              Effacer le détail horaire
            </button>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
