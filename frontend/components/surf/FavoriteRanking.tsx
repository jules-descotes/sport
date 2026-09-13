"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { api } from "@/lib/api";
import { dayLabel, num, ratingLabel, scoreClass } from "@/lib/format";
import type { FavoriteRankingEntry } from "@/lib/types";

/**
 * **Tes favoris, du meilleur au moins bon** — aujourd'hui et demain.
 *
 * Décidé le 13/09 (retours n° 4), règle B.2. Ça remplace les annonces
 * (« Parlementia devrait marcher dim. 10 h ») qui deviennent **la première
 * ligne de cette liste** : une annonce disait qu'un spot correspondait, elle
 * ne disait pas lequel des quatre est le meilleur ce matin — ce qui est
 * exactement la question qu'on se pose en ouvrant l'app.
 *
 * La note de journée est le **produit** de la part d'heures qui correspondent
 * aux critères du spot et de la qualité moyenne sur ces heures. Un spot
 * excellent une heure par jour et un spot correct toute la journée ne se
 * départagent pas par addition : le premier demande d'être là à 8 h, le second
 * se décide au réveil. C'est ce que la ligne dit — « 3 h sur 11 » à côté de la
 * note moyenne.
 *
 * Deux mentions comptent autant que le classement :
 *
 * - **« sans critères »** — le spot est classé sur le seul score. Sans règles,
 *   « correspond » ne veut rien dire, et le taire ferait croire à un
 *   classement qu'il n'est pas.
 * - **« pas de prévision »** — le spot n'a jamais été ingéré. Il est en bas et
 *   sans note : lui en inventer une serait pire que de n'en donner aucune.
 *
 * Le tap ouvre Surf **sur ce spot et sur cette heure**, comme la bande des
 * huit créneaux. Un classement qu'il faudrait ensuite chercher à la main dans
 * un tableau de cent vingt colonnes ne servirait à rien.
 */

function Row({ entry }: { entry: FavoriteRankingEntry }) {
  // Le meilleur des jours rendus : c'est lui qui a classé la ligne, c'est donc
  // lui qu'on montre.
  const best = entry.days.reduce<(typeof entry.days)[number] | null>(
    (kept, day) =>
      kept === null || day.day_score > kept.day_score ? day : kept,
    null,
  );

  const href =
    best?.best_ts != null
      ? `/surf?spot=${entry.spot.slug}&ts=${encodeURIComponent(best.best_ts)}`
      : `/surf?spot=${entry.spot.slug}`;

  return (
    <li className="border-b border-line last:border-0">
      <Link href={href} className="flex min-h-touch items-center gap-3 px-4 py-2.5">
        <span
          className={`tabular flex h-10 w-10 shrink-0 items-center justify-center rounded-cell font-display text-[18px] font-bold ${
            entry.has_forecast && best?.best_score != null
              ? scoreClass(best.best_score)
              : "border border-line bg-soft text-mute"
          }`}
        >
          {entry.has_forecast && best?.best_score != null
            ? ratingLabel(best.best_score)
            : "—"}
        </span>

        <span className="min-w-0 flex-1">
          <span className="flex items-baseline gap-1.5">
            <span className="truncate text-[15px] font-semibold text-ink">
              {entry.spot.name}
            </span>
            {entry.is_home ? (
              <span className="shrink-0 text-[11px] text-mute">principal</span>
            ) : null}
          </span>
          <span className="tabular block truncate text-[12px] text-mute">
            {!entry.has_forecast ? (
              "pas de prévision"
            ) : !entry.has_rules ? (
              <>
                sans critères · note moyenne{" "}
                {num(best?.average_score ?? 0, 1)}
              </>
            ) : best && best.matching_hours > 0 ? (
              <>
                {dayLabel(best.day)} · {best.matching_hours} h sur{" "}
                {best.daylight_hours} · moyenne{" "}
                {num(best.average_score, 1)}
              </>
            ) : (
              "aucune heure ne correspond"
            )}
          </span>
        </span>

        {best?.window_start != null && best.window_end != null ? (
          <span className="tabular shrink-0 text-[13px] font-semibold text-ink-2">
            {new Date(best.window_start).getHours()} h –{" "}
            {new Date(best.window_end).getHours()} h
          </span>
        ) : null}
      </Link>
    </li>
  );
}

export function FavoriteRanking({
  title = "Tes favoris",
  className = "",
}: {
  title?: string;
  className?: string;
}) {
  const { data } = useQuery({
    queryKey: ["favorites-ranking"],
    queryFn: () => api.favoritesRanking(),
  });

  // Un seul favori n'a personne avec qui être comparé : la liste occuperait
  // de la hauteur pour répéter ce que le bloc de mer dit déjà en grand.
  if (!data || data.length < 2) return null;

  return (
    <section className={`px-5 ${className}`} aria-label="Classement des favoris">
      <h2 className="pb-2 text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
        {title}
      </h2>
      <ul className="overflow-hidden rounded-card border border-line bg-card">
        {data.map((entry) => (
          <Row key={entry.spot.id} entry={entry} />
        ))}
      </ul>
      <p className="pt-1.5 text-[11px] leading-snug text-mute">
        Classés sur la part des heures de jour qui correspondent à tes critères,
        multipliée par la note moyenne de ces heures-là.
      </p>
    </section>
  );
}
