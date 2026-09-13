"use client";

import { DirectionArrow } from "@/components/surf/DirectionArrow";
import { num, ratingLabel, scoreClass } from "@/lib/format";
import type { ConditionsSnapshot, SessionSegmentValue } from "@/lib/types";

/**
 * **La frise horaire d'une session détaillée** (décidé le 13/09).
 *
 * Chaque heure notée, avec — juste en dessous — la houle, le vent et la marée
 * de **cette** heure-là. C'est là que le détail horaire prend son sens : on
 * voit, sur une seule ligne, que la note est tombée quand le vent s'est levé.
 *
 * L'appariement se fait sur l'heure pleine, qui est la clé posée côté serveur.
 * Une heure sans ligne correspondante s'affiche quand même, avec des tirets :
 * la frise est une matrice, et une colonne manquante décalerait la lecture —
 * la même règle que la grille de l'écran Surf.
 *
 * Ne s'affiche que si des segments existent. Le cas courant est une session
 * notée en deux taps, et cet écran ne doit pas s'allonger pour elle.
 */
interface SegmentTimelineProps {
  segments: SessionSegmentValue[];
  snapshot: ConditionsSnapshot | null;
}

function sameHour(a: string, b: string): boolean {
  return new Date(a).getTime() === new Date(b).getTime();
}

export function SegmentTimeline({ segments, snapshot }: SegmentTimelineProps) {
  if (segments.length === 0) return null;

  // Le volet constaté d'abord : c'est ce qui s'est passé, et c'est la grandeur
  // sur laquelle le modèle de goût s'entraîne (PROJET.md §7.3).
  const rows = snapshot
    ? snapshot.observed.length > 0
      ? snapshot.observed
      : snapshot.forecast
    : [];

  return (
    <section className="px-5 pt-5" aria-label="Notes heure par heure">
      <div className="flex items-baseline justify-between gap-3 pb-2">
        <h2 className="text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
          Heure par heure
        </h2>
        <span className="text-[12px] text-mute">
          {segments.length} heures notées
        </span>
      </div>

      <div className="overflow-x-auto rounded-card border border-line bg-card">
        <table className="tabular w-full border-collapse">
          <thead>
            <tr className="bg-soft">
              <th className="px-3 py-2 text-left text-[12px] font-semibold text-mute">
                Heure
              </th>
              <th className="px-2 py-2 text-center text-[12px] font-semibold text-mute">
                Cond.
              </th>
              <th className="px-2 py-2 text-center text-[12px] font-semibold text-mute">
                Perso
              </th>
              <th className="px-2 py-2 text-center text-[12px] font-semibold text-mute">
                Houle
              </th>
              <th className="px-2 py-2 text-center text-[12px] font-semibold text-mute">
                Vent
              </th>
              <th className="px-2 py-2 text-center text-[12px] font-semibold text-mute">
                Niveau
              </th>
            </tr>
          </thead>
          <tbody>
            {segments.map((segment) => {
              const hour = new Date(segment.started_at);
              const entry = rows.find((row) => sameHour(row.ts, segment.started_at));
              return (
                <tr
                  key={segment.started_at}
                  className="border-t border-line"
                >
                  <th
                    scope="row"
                    className="whitespace-nowrap px-3 py-2 text-left text-[14px] font-semibold text-ink"
                  >
                    {hour.getHours()} h
                  </th>
                  <td className="px-1 py-1.5">
                    <span
                      className={`flex h-8 items-center justify-center rounded-chip font-display text-[15px] font-bold leading-none ${
                        segment.rating_conditions === null
                          ? "border border-line bg-soft text-mute"
                          : scoreClass(segment.rating_conditions)
                      }`}
                    >
                      {ratingLabel(segment.rating_conditions)}
                    </span>
                  </td>
                  <td className="px-1 py-1.5">
                    <span
                      className={`flex h-8 items-center justify-center rounded-chip font-display text-[15px] font-bold leading-none ${
                        segment.rating_personal === null
                          ? "border border-line bg-soft text-mute"
                          : scoreClass(segment.rating_personal)
                      }`}
                    >
                      {ratingLabel(segment.rating_personal)}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-2 py-2 text-center text-[13px] text-ink-2">
                    {entry ? (
                      <span className="flex items-center justify-center gap-1">
                        {num(entry.wave_height_m)} m
                        <DirectionArrow
                          direction={entry.wave_direction_deg}
                          size={14}
                        />
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="whitespace-nowrap px-2 py-2 text-center text-[13px] text-ink-2">
                    {entry ? (
                      <span className="flex items-center justify-center gap-1">
                        {num(entry.wind_speed_kt, 0)} kt
                        <DirectionArrow
                          direction={entry.wind_direction_deg}
                          size={14}
                        />
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-2 py-2 text-center text-[13px] text-ink-2">
                    {entry ? `${num(entry.sea_level_m, 2)} m` : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="pt-2 text-[12px] leading-snug text-mute">
        Chaque heure est appariée à ses propres conditions. Ce sont des points
        d&apos;apprentissage à part entière ; la note globale reste celle qui
        s&apos;affiche partout ailleurs.
      </p>
    </section>
  );
}
