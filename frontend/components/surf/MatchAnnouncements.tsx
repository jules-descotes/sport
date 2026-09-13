"use client";

import Link from "next/link";

import { DirectionArrow } from "@/components/surf/DirectionArrow";
import { num, scoreClass } from "@/lib/format";
import type { MatchWindow } from "@/lib/types";

/**
 * « Parlementia devrait marcher — dim. 10 h à 13 h ».
 *
 * Sous le bloc de mer, et seulement quand il y a quelque chose à dire. Jour
 * montre la prévision du **favori principal** et rien d'autre : c'est ce qui
 * garde l'écran lisible. Mais un spot qui ne marche que trois fois par mois
 * n'a aucune raison d'occuper l'écran les vingt-sept autres jours, et toutes
 * les raisons d'être annoncé ces trois jours-là.
 *
 * Trois au maximum, les plus proches en premier : ce qui se décide ce soir
 * passe devant ce qui se décide dimanche. La quatrième ne serait plus lue.
 *
 * Le tap ouvre Surf **sur ce spot et sur cette heure** — la même mécanique que
 * la bande des huit créneaux. Une annonce qu'il faudrait ensuite chercher à la
 * main dans un tableau de cent vingt colonnes ne servirait à rien.
 */
export function MatchAnnouncements({ matches }: { matches: MatchWindow[] }) {
  if (matches.length === 0) return null;

  return (
    <section className="px-5" aria-label="Tes autres spots">
      <h2 className="pb-2 text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
        Tes critères
      </h2>
      <ul className="overflow-hidden rounded-card border border-line bg-card">
        {matches.map((match) => (
          <li key={`${match.spot.id}-${match.start}`} className="border-b border-line last:border-0">
            <Link
              href={`/surf?spot=${match.spot.slug}&ts=${encodeURIComponent(
                match.best_ts,
              )}`}
              className="flex min-h-touch items-center gap-3 px-4 py-3"
            >
              <span
                className={`tabular flex h-10 w-10 shrink-0 items-center justify-center rounded-chip font-display text-[19px] font-bold leading-none ${scoreClass(
                  Math.round(match.best_score),
                )}`}
              >
                {num(match.best_score, 1)}
              </span>

              <span className="min-w-0 flex-1">
                <span className="block truncate text-[15px] font-semibold text-ink">
                  {match.sentence}
                </span>
                <span className="tabular block truncate text-[12px] text-mute">
                  {match.details}
                </span>
              </span>

              {/* La flèche de houle, comme partout ailleurs : à bout de bras,
                  « 292° » ne se lit pas. */}
              <span className="shrink-0 text-ink-2">
                <DirectionArrow direction={match.wave_direction_deg} size={18} />
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
