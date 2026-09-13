"use client";

import { useQuery } from "@tanstack/react-query";

import { Sparkline } from "@/components/habits/Sparkline";
import { api } from "@/lib/api";
import { num, ratingLabel, shortDate } from "@/lib/format";
import { HabitIcon } from "@/lib/habit-icons";

/**
 * **Les quatre cartes du profil** — surf, nutrition, training, habitudes.
 *
 * Ce ne sont pas encore les statistiques du lot 6 (« tes meilleures sessions :
 * houle 1,2–1,8 m, période 11–14 s, marée montante »), qui demandent une
 * analyse des corrélations. Ce sont les chiffres qu'on a déjà et qu'on n'a
 * jamais montrés.
 *
 * **Des chiffres grands et sobres, et rien d'autre.** Aucun pourcentage de
 * réussite, aucune série perdue, aucun rouge. Une absence s'affiche « — » et
 * jamais zéro : un zéro se lirait comme une mauvaise note, alors qu'il veut
 * dire « on ne sait pas encore ».
 *
 * **Desktop** : les quatre cartes côte à côte, avec de vraies courbes — trait
 * fin, une seule teinte, grille discrète.
 */

function Card({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <article className="overflow-hidden rounded-card border border-line bg-card px-4 py-4">
      <h3 className="pb-3 text-[12px] font-semibold uppercase tracking-[0.14em] text-mute">
        {title}
      </h3>
      {children}
    </article>
  );
}

function Figure({
  value,
  unit,
  label,
}: {
  value: string;
  unit?: string;
  label: string;
}) {
  return (
    <div className="min-w-0">
      <p className="tabular font-display text-[30px] font-bold leading-none text-ink">
        {value}
        {unit ? (
          <span className="pl-1 text-[15px] font-semibold text-mute">
            {unit}
          </span>
        ) : null}
      </p>
      <p className="pt-1 text-[12px] leading-tight text-mute">{label}</p>
    </div>
  );
}

export function ProfileStatsCards() {
  const stats = useQuery({
    queryKey: ["profile-stats"],
    queryFn: api.profileStats,
  });

  if (stats.isPending) {
    return (
      <section className="px-5 pb-6">
        <p className="text-[14px] text-mute">Lecture des statistiques…</p>
      </section>
    );
  }
  if (stats.error || !stats.data) return null;

  const { surf, nutrition, training, habits } = stats.data;

  return (
    <section className="px-5 pb-6" aria-label="Statistiques">
      <h2 className="pb-2 text-[12px] font-semibold uppercase tracking-wide text-mute">
        Où j&apos;en suis
      </h2>

      <div className="flex flex-col gap-3 lg:grid lg:grid-cols-2 xl:grid-cols-4">
        {/* ── Surf ─────────────────────────────────────────────────────── */}
        <Card title="Surf">
          <div className="flex gap-5">
            <Figure
              value={String(surf.sessions_30d)}
              label="sessions sur 30 j"
            />
            <Figure
              value={num(surf.hours_30d, 1)}
              unit="h"
              label="à l'eau sur 30 j"
            />
          </div>

          <dl className="tabular pt-3">
            {[
              [
                "Cette saison",
                `${surf.sessions_season} sessions · ${num(surf.hours_season, 0)} h`,
              ],
              ["Note moyenne", ratingLabel(surf.average_rating)],
              [
                "Spot n°1",
                surf.top_spot
                  ? `${surf.top_spot} · ${surf.top_spot_sessions}`
                  : "—",
              ],
              [
                "Série en cours",
                surf.streak_days > 0 ? `${surf.streak_days} jours` : "—",
              ],
              [
                "Meilleure session",
                surf.best_rating !== null && surf.best_day
                  ? `${ratingLabel(surf.best_rating)} · ${surf.best_spot ?? ""} · ${shortDate(
                      `${surf.best_day}T12:00:00`,
                    )}`
                  : "—",
              ],
            ].map(([label, value]) => (
              <div
                key={label}
                className="flex items-baseline justify-between gap-3 border-t border-line py-1.5"
              >
                <dt className="shrink-0 text-[12px] uppercase tracking-wide text-mute">
                  {label}
                </dt>
                <dd className="truncate text-right text-[14px] font-medium text-ink-2">
                  {value}
                </dd>
              </div>
            ))}
          </dl>
        </Card>

        {/* ── Nutrition ────────────────────────────────────────────────── */}
        <Card title="Nutrition">
          <div className="flex gap-5">
            <Figure
              value={String(nutrition.on_target_days_30d)}
              label="jours dans la cible sur 30"
            />
            <Figure
              value={
                nutrition.average_protein_g === null
                  ? "—"
                  : num(nutrition.average_protein_g, 0)
              }
              unit="g"
              label="protéines par jour"
            />
          </div>

          <dl className="tabular pt-3">
            {[
              ["Jours journalisés", `${nutrition.logged_days_30d} / 30`],
              [
                "Poids",
                nutrition.weight_kg === null
                  ? "—"
                  : `${num(nutrition.weight_kg)} kg`,
              ],
              [
                "Sur 30 jours",
                nutrition.weight_change_30d === null
                  ? "—"
                  : `${nutrition.weight_change_30d > 0 ? "+" : "−"}${num(
                      Math.abs(nutrition.weight_change_30d),
                    )} kg`,
              ],
            ].map(([label, value]) => (
              <div
                key={label}
                className="flex items-baseline justify-between gap-3 border-t border-line py-1.5"
              >
                <dt className="text-[12px] uppercase tracking-wide text-mute">
                  {label}
                </dt>
                <dd className="text-[14px] font-medium text-ink-2">{value}</dd>
              </div>
            ))}
          </dl>
        </Card>

        {/* ── Training ─────────────────────────────────────────────────── */}
        <Card title="Training">
          <div className="flex gap-5">
            <Figure
              value={String(training.done_8w)}
              label={`séances sur 8 semaines · ${training.planned_8w} prévues`}
            />
          </div>

          {/* Barres et non ligne : pour des comptes hebdomadaires, une barre
              est plus juste qu'un trait qui interpolerait entre deux semaines.
              Le pointillé est ce qui était prévu. */}
          <div className="pt-3">
            <Sparkline
              bars
              values={training.weeks.map((week) => week.done)}
              reference={training.weeks.map((week) => week.planned)}
              label="Séances faites par semaine sur huit semaines"
            />
            <p className="pt-1 text-[11px] text-mute">
              Huit semaines · le pointillé est ce qui était proposé
            </p>
          </div>

          <dl className="tabular pt-2">
            <div className="flex items-baseline justify-between gap-3 border-t border-line py-1.5">
              <dt className="text-[12px] uppercase tracking-wide text-mute">
                Objectif le plus avancé
              </dt>
              <dd className="truncate text-right text-[14px] font-medium text-ink-2">
                {training.best_objective
                  ? `${training.best_objective} · ${Math.round(
                      (training.best_ratio ?? 0) * 100,
                    )} %`
                  : "—"}
              </dd>
            </div>
          </dl>
        </Card>

        {/* ── Habitudes ────────────────────────────────────────────────── */}
        <Card title="Habitudes">
          {habits.length === 0 ? (
            <p className="text-[13px] leading-snug text-ink-2">
              Aucune habitude suivie. Elles se définissent plus bas, et se
              comptent en un tap depuis Jour.
            </p>
          ) : (
            <ul className="flex flex-col gap-3">
              {habits.map((trend) => {
                return (
                  <li key={trend.habit_id}>
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="flex min-w-0 items-center gap-1.5 text-[13px] font-semibold text-ink">
                        <HabitIcon name={trend.icon} className="h-4 w-4 shrink-0 text-mute" />
                        <span className="truncate">{trend.name}</span>
                      </span>
                      <span className="tabular shrink-0 text-[12px] text-mute">
                        {num(trend.total_30d, trend.total_30d % 1 ? 1 : 0)}
                        {trend.unit ? ` ${trend.unit}` : ""} · {""}
                        {trend.days_with_activity} j
                      </span>
                    </div>
                    <Sparkline
                      values={trend.daily}
                      height={32}
                      label={`${trend.name}, trente derniers jours`}
                    />
                  </li>
                );
              })}
            </ul>
          )}
          <p className="pt-2 text-[11px] leading-snug text-mute">
            Trente jours, sans jugement. Ce sont des compteurs, pas des devoirs.
          </p>
        </Card>
      </div>
    </section>
  );
}
