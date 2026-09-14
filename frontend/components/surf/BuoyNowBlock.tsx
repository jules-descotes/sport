"use client";

import { DirectionArrow } from "@/components/surf/DirectionArrow";
import { clockLabel, compass, num } from "@/lib/format";
import type { BuoyNow } from "@/lib/types";

/**
 * « Maintenant » — ce que la bouée mesure, à côté de ce qui était prévu.
 *
 * C'est le premier endroit du produit où une **mesure** et une **prévision**
 * se regardent en face. Elles ne se moyennent pas et ne se remplacent pas :
 * elles sont côte à côte, la mesure en grand, la prévision en petit dessous.
 * Une bouée ne prévoit rien, un modèle ne mesure rien — les confondre ferait
 * perdre exactement ce que ce bloc existe pour montrer.
 *
 * **Jamais de rouge sur l'écart.** Vingt centimètres entre une prévision et
 * une mesure, c'est une mer normale, pas une faute du modèle. Le jugement, s'il
 * vient un jour, viendra de la calibration sur trente jours — pas d'un point.
 *
 * Le composant ne décide pas de sa propre disparition : l'API ne renvoie rien
 * au-delà de trois heures d'âge. Une bouée muette depuis ce matin ne décrit
 * plus « maintenant », et un bloc qui afficherait la houle de 6 h serait pire
 * qu'un écran sans bloc.
 */

interface BuoyNowBlockProps {
  now: BuoyNow;
  className?: string;
}

function ageLabel(minutes: number): string {
  if (minutes < 1) return "à l'instant";
  if (minutes < 60) return `il y a ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `il y a ${hours} h ${rest} min` : `il y a ${hours} h`;
}

function distanceLabel(metres: number | null): string | null {
  if (metres === null) return null;
  const km = metres / 1000;
  return km < 10 ? `${num(km, 1)} km` : `${Math.round(km)} km`;
}

export function BuoyNowBlock({ now, className }: BuoyNowBlockProps) {
  const distance = distanceLabel(now.distance_m);

  return (
    <section
      className={`rounded-card border border-line bg-card p-4 ${className ?? ""}`}
      aria-label="Mesure de la bouée"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 className="font-display text-lg font-semibold uppercase tracking-wide text-ink">
          Maintenant
        </h2>
        <p className="text-xs text-mute">
          {/* La provenance est nommée, pas sous-entendue : ce n'est pas le
              modèle qui parle ici, c'est un instrument dans l'eau. */}
          bouée {now.station_name}
          {distance ? `, ${distance}` : ""} · {clockLabel(now.ts)} ·{" "}
          {ageLabel(now.age_minutes)}
        </p>
      </header>

      <dl className="mt-3 grid grid-cols-3 gap-3">
        <div>
          <dt className="text-xs uppercase tracking-wide text-mute">Hauteur</dt>
          <dd className="font-display text-3xl font-semibold tabular-nums text-ink">
            {num(now.hm0_m, 1)}
            <span className="ml-1 text-base font-medium text-ink-2">m</span>
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-mute">Période</dt>
          <dd className="font-display text-3xl font-semibold tabular-nums text-ink">
            {num(now.peak_period_s, 0)}
            <span className="ml-1 text-base font-medium text-ink-2">s</span>
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-mute">
            Direction
          </dt>
          <dd className="flex items-center gap-2 font-display text-2xl font-semibold tabular-nums text-ink">
            <DirectionArrow
              direction={now.wave_direction_deg}
              size={20}
              label={
                now.wave_direction_deg === null
                  ? undefined
                  : `houle de ${compass(now.wave_direction_deg)}`
              }
            />
            <span>{compass(now.wave_direction_deg)}</span>
          </dd>
        </div>
      </dl>

      {now.sentence ? (
        <p className="mt-3 border-t border-line pt-3 text-sm text-ink-2">
          {now.sentence}
          {now.water_temperature_c !== null ? (
            <span className="text-mute"> · eau {num(now.water_temperature_c, 1)} °C</span>
          ) : null}
        </p>
      ) : now.water_temperature_c !== null ? (
        <p className="mt-3 border-t border-line pt-3 text-sm text-mute">
          eau {num(now.water_temperature_c, 1)} °C
        </p>
      ) : null}
    </section>
  );
}
